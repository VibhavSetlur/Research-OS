"""Execution runners — the daemon's "any language, any work" layer.

JUDGE-1 gap #2 (docs/v4/ROADMAP.md §8): the task queue only ran in-process
Python callables, which silently fails the "any language" bar. Real
research runs R, Julia, bash, Snakemake, Nextflow, and scheduler
submissions. This package gives the daemon a uniform way to run ALL of
them.

The design keeps the existing `TaskQueue.submit(callable)` seam unchanged:
a runner is just a callable the queue schedules. Each runner accepts a
`cancel_event` (cooperative cancellation) and an optional `emit` callback
so it can stream progress as `job.log` events on the bus. It returns a
JSON-serializable result (exit code, captured output, artifacts) — a
*handle*, never a blob.

stdlib only (subprocess, shlex, threading). Native execution first; the
sandbox (Phase 4) and scheduler adapters (SLURM/snakemake/nextflow) slot
in later as additional runners behind this same interface.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Sequence

# Type of the optional progress callback a runner may call to stream lines.
EmitFn = Callable[[str, dict], None]


@dataclass
class RunResult:
    """The outcome of a subprocess run — a handle, not a payload dump."""

    returncode: int
    cmd: list[str]
    cwd: str | None
    duration_s: float
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)
    truncated: bool = False
    cancelled: bool = False
    artifacts: list[dict] = field(default_factory=list)
    artifacts_truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.cancelled

    def to_dict(self) -> dict:
        return {
            "returncode": self.returncode,
            "ok": self.ok,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "duration_s": round(self.duration_s, 3),
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "truncated": self.truncated,
            "cancelled": self.cancelled,
            "artifacts": self.artifacts,
            "artifacts_truncated": self.artifacts_truncated,
        }


class SubprocessRunner:
    """Run an external command, streaming its output as events.

    This is the universal escape hatch: anything with a CLI (Rscript,
    julia, bash, python, snakemake, nextflow, sbatch, …) runs through here
    with one consistent lifecycle. Output is streamed line-by-line via the
    `emit` callback (as ``job.log`` events) and a bounded tail is retained
    in the result so a status read never returns megabytes.

    Cooperative cancel: when ``cancel_event`` is set we terminate the
    process group (SIGTERM, then SIGKILL after a grace period), so a
    cancelled long-running tool actually stops instead of orphaning.
    """

    def __init__(
        self,
        cmd: str | Sequence[str],
        *,
        cwd: str | None = None,
        env: dict | None = None,
        tail_lines: int = 200,
        kill_grace_s: float = 5.0,
        shell: bool = False,
        track_artifacts: bool = True,
    ) -> None:
        if isinstance(cmd, str) and not shell:
            self.cmd = shlex.split(cmd)
        elif isinstance(cmd, str):
            self.cmd = [cmd]  # passed through to shell
        else:
            self.cmd = list(cmd)
        self._raw_cmd = cmd
        self.cwd = cwd
        self.env = env
        self.tail_lines = max(1, tail_lines)
        self.kill_grace_s = kill_grace_s
        self.shell = shell
        self.track_artifacts = track_artifacts

    def __call__(
        self,
        *,
        cancel_event: threading.Event | None = None,
        emit: EmitFn | None = None,
    ) -> dict:
        import time
        from collections import deque

        cancel_event = cancel_event or threading.Event()
        stdout_tail: deque[str] = deque(maxlen=self.tail_lines)
        stderr_tail: deque[str] = deque(maxlen=self.tail_lines)
        line_count = 0
        start = time.time()

        # Artifact tracking (Phase 1.8): fingerprint the working dir before
        # the run so we can report created/modified files afterwards. The
        # diff is best-effort and never blocks or fails the run.
        art_root = self.cwd or os.getcwd()
        art_before: dict = {}
        if self.track_artifacts:
            from . import artifacts as _artifacts

            art_before = _artifacts.snapshot(art_root)

        run_env = None
        if self.env is not None:
            run_env = {**os.environ, **{str(k): str(v) for k, v in self.env.items()}}

        popen_kwargs: dict = dict(
            cwd=self.cwd,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        # New process group so we can signal the whole tree on cancel
        # (POSIX). On Windows this is a no-op fallback.
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True

        if self.shell and isinstance(self._raw_cmd, str):
            proc = subprocess.Popen(self._raw_cmd, shell=True, **popen_kwargs)
        else:
            proc = subprocess.Popen(self.cmd, **popen_kwargs)

        def _pump(stream, tail: deque, channel: str) -> None:
            nonlocal line_count
            for raw in iter(stream.readline, ""):
                line = raw.rstrip("\n")
                tail.append(line)
                line_count += 1
                if emit is not None:
                    try:
                        emit("job.log", {"channel": channel, "line": line})
                    except Exception:  # noqa: BLE001 - telemetry must not break a run
                        pass
            stream.close()

        t_out = threading.Thread(target=_pump, args=(proc.stdout, stdout_tail, "stdout"))
        t_err = threading.Thread(target=_pump, args=(proc.stderr, stderr_tail, "stderr"))
        t_out.start()
        t_err.start()

        cancelled = False
        # Poll for completion or cancellation without busy-waiting hard.
        while True:
            try:
                proc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if cancel_event.is_set():
                    cancelled = True
                    self._terminate(proc)
                    break

        proc.wait()  # ensure fully reaped after terminate
        t_out.join(timeout=2)
        t_err.join(timeout=2)

        # Diff the working dir to surface artifacts the run produced.
        art_list: list[dict] = []
        art_trunc = False
        if self.track_artifacts:
            from . import artifacts as _artifacts

            art = _artifacts.diff(art_root, art_before)
            art_list = art.get("artifacts", [])
            art_trunc = art.get("truncated", False)

        result = RunResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            cmd=self.cmd,
            cwd=self.cwd,
            duration_s=time.time() - start,
            stdout_tail=list(stdout_tail),
            stderr_tail=list(stderr_tail),
            truncated=line_count > (len(stdout_tail) + len(stderr_tail)),
            cancelled=cancelled,
            artifacts=art_list,
            artifacts_truncated=art_trunc,
        )
        return result.to_dict()

    def _terminate(self, proc: subprocess.Popen) -> None:
        """SIGTERM the process group, then SIGKILL after a grace period."""
        import signal
        import time

        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:  # pragma: no cover - Windows fallback
                proc.terminate()
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.time() + self.kill_grace_s
        while time.time() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:  # pragma: no cover
                proc.kill()
        except (ProcessLookupError, PermissionError):
            pass
