"""Execution runners — the daemon's "any language, any work" layer.

JUDGE-1 gap #2 (docs/ROADMAP.md §8): the task queue only ran in-process
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

stdlib only (subprocess, shlex, threading). Native execution with sandbox
tiers + rlimits applied in the preexec; the scheduler adapters
(SLURM/snakemake/nextflow) run behind this same interface as additional
runners.
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
    sandbox: dict | None = None

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
            "sandbox": self.sandbox,
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
        sandbox: str | None = None,
        sandbox_network: bool = False,
        sandbox_limits=None,
        budget_root: str | None = None,
        requested_mem_mb: int | None = None,
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
        # Phase 4 sandbox policy: when requested, the command is wrapped for
        # the strongest isolation tier the host supports (container →
        # namespace → resource) and rlimits are applied via a preexec_fn.
        # ``sandbox=None`` keeps the original native-execution behaviour.
        self.sandbox = sandbox
        self.sandbox_network = sandbox_network
        self.sandbox_limits = sandbox_limits
        # Where to look for the project's resource_budget. Defaults to cwd
        # (back-compat), but the budget actually lives at the PROJECT ROOT —
        # which may differ from a run's cwd (a run in a subdir). core passes
        # the real root so the declared budget binds regardless of cwd.
        self.budget_root = budget_root
        # Optional caller-stated memory size for THIS run (MB). Feeds the
        # dynamic limiter so a run that declares "I need ~40GB" is bounded to
        # the min of that, the project ceiling, and live free-RAM headroom.
        self.requested_mem_mb = requested_mem_mb
        self._sandbox_meta: dict | None = None
        self._preexec = None

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

        # Phase 4: resolve the sandbox policy ONCE per run, before launch.
        # This may rewrite the command (container/namespace wrappers) and/or
        # build a preexec_fn that applies rlimits in the child. Native
        # execution (sandbox=None) leaves cmd/preexec untouched.
        self._resolve_sandbox()

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
            # Phase 4 resource tier: apply rlimits in the forked child.
            if self._preexec is not None:
                popen_kwargs["preexec_fn"] = self._preexec

        if self.shell and isinstance(self._raw_cmd, str):
            proc = subprocess.Popen(self._raw_cmd, shell=True, **popen_kwargs)
        else:
            proc = subprocess.Popen(self.cmd, **popen_kwargs)

        # Record the child PID so crash-recovery can tell a genuinely-dead run
        # from one whose subprocess survived a daemon restart (BLOCK-2 / F-4):
        # resume_run refuses to re-spawn while the recorded PID is still alive.
        if emit is not None:
            try:
                emit("job.pid", {"pid": proc.pid})
            except Exception:  # noqa: BLE001 - telemetry must not break a run
                pass

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
            sandbox=self._sandbox_meta,
        )
        return result.to_dict()

    def _resolve_sandbox(self) -> None:
        """Apply the sandbox policy to self.cmd / self._preexec (Phase 4).

        No-op when ``sandbox is None`` (native execution). Otherwise probes
        the host's isolation tiers, degrades the requested tier to the
        strongest the host supports, wraps the command accordingly, and —
        for the resource tier — builds a preexec_fn that caps rlimits in the
        child. Records what actually happened in ``self._sandbox_meta`` so a
        caller sees the effective tier (which may be weaker than requested).

        Shell mode and the sandbox are mutually exclusive: wrapping a
        ``shell=True`` string would break the argv transform, so in that case
        we apply only the resource tier (preexec + wallclock) and note it.
        """
        if self.sandbox is None:
            return
        from . import sandbox as _sb

        caps = _sb.detect_sandbox()
        # Resolve the effective limits. The static resource_budget is the
        # declared ceiling; the dynamic limiter then scales the memory bound to
        # live free-RAM headroom (min of declared / requested / safe headroom)
        # so a multi-gig batch runs big on an idle node but backs off on a busy
        # one — never starving other users on a shared box. Fail-open: any
        # probe failure returns the static budget unchanged.
        from . import dynamic_limits as _dyn

        budget_root = self.budget_root or self.cwd or "."
        limits, dyn_explain = _dyn.resolve_dynamic_limits(
            budget_root,
            base=self.sandbox_limits,
            requested_mem_mb=self.requested_mem_mb,
        )
        self._dyn_explain = dyn_explain
        effective = caps.resolve_tier(self.sandbox)

        if effective == "none":
            self._sandbox_meta = {
                "requested": self.sandbox,
                "effective": "none",
                "isolated": False,
                "note": "no sandbox tier available on this host",
                "limits": limits.to_dict(),
                "dynamic": dyn_explain,
            }
            return

        # The resource tier always applies its rlimit preexec. Stronger
        # tiers also get it as defense-in-depth (a container with rlimits).
        self._preexec = _sb.make_preexec(limits)

        # "downgraded" = host couldn't honour the requested tier and fell to
        # a weaker one. Only meaningful when a specific tier was requested.
        requested = self.sandbox if self.sandbox in _sb.TIERS else None
        downgraded = bool(
            requested
            and _sb.TIERS.index(effective) > _sb.TIERS.index(requested)
        )
        note = None
        if self.shell and effective in ("container", "namespace"):
            # Can't argv-wrap a shell string; fall back to resource tier.
            effective = "resource"
            note = "shell=True is incompatible with command wrapping; applied resource tier only"

        if effective in ("container", "namespace"):
            self.cmd = _sb.wrap_command(
                self.cmd,
                tier=effective,
                caps=caps,
                limits=limits,
                cwd=self.cwd,
                network=self.sandbox_network,
            )
        else:  # resource tier — argv only gets a wallclock guard
            self.cmd = _sb._with_wall_timeout(self.cmd, limits)

        self._sandbox_meta = {
            "requested": self.sandbox,
            "effective": effective,
            "downgraded": downgraded,
            "isolated": effective in ("container", "namespace"),
            "runtime": caps.container_runtime,
            "namespace_tool": caps.namespace_tool,
            "network": self.sandbox_network,
            "limits": limits.to_dict(),
            "note": note,
            "dynamic": getattr(self, "_dyn_explain", None),
        }

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


def docker_available() -> bool:
    """True if a usable container CLI (docker or podman) is on PATH."""
    import shutil
    return bool(shutil.which("docker") or shutil.which("podman"))


def _container_cli() -> str | None:
    import shutil
    return shutil.which("docker") or shutil.which("podman")


class DockerRunner:
    """Run a command INSIDE a container image, as a tracked daemon job.

    Many labs ship reproducible work as a Docker/Podman image (or run on
    Kubernetes). This runner lets the AI send a long, reproducible job through
    the daemon pinned to an exact image — the image digest becomes part of the
    run's provenance, so the run is recreatable bit-for-bit, not just
    "ran in conda env X".

    It composes a ``docker run`` (or ``podman run``) invocation:
      - mounts the project root read-write at the same path inside the container
        so outputs land back in the workspace (auto-provenanced like any run);
      - sets the working directory to ``cwd`` (defaults to the project root);
      - passes through declared env vars;
      - is removed on exit (``--rm``) so it leaves no container cruft on a
        shared node.
    Execution + cancellation + output capture are delegated to SubprocessRunner,
    so a containerised job behaves exactly like any other tracked run (same
    lifecycle, same bounded log tail, same cancel semantics). On Kubernetes,
    point ``binary`` at a thin ``kubectl run``-style wrapper, or submit via the
    scheduler runner — the daemon contract is identical.
    """

    def __init__(
        self,
        image: str,
        command: str | Sequence[str],
        *,
        cwd: str | None = None,
        mount_root: str | None = None,
        env: dict | None = None,
        gpus: str | None = None,
        network: bool = False,
        extra_args: Sequence[str] | None = None,
        tail_lines: int = 200,
        track_artifacts: bool = True,
        binary: str | None = None,
    ) -> None:
        cli = binary or _container_cli()
        if not cli:
            raise RuntimeError(
                "no container CLI found (docker/podman). Install one, or run the "
                "job natively via run_command."
            )
        self.image = image
        self.cli = cli
        if isinstance(command, str):
            inner = shlex.split(command)
        else:
            inner = list(command)
        mount = mount_root or cwd or os.getcwd()
        workdir = cwd or mount
        argv: list[str] = [cli, "run", "--rm"]
        # Reproducible + isolated by default: no host network unless asked.
        if not network:
            argv += ["--network", "none"]
        argv += ["-v", f"{mount}:{mount}", "-w", workdir]
        for k in sorted((env or {}).keys()):
            argv += ["-e", k]
        if gpus:
            argv += ["--gpus", gpus]
        if extra_args:
            argv += list(extra_args)
        argv += [image, *inner]
        # Delegate the actual run to SubprocessRunner — same lifecycle as any
        # tracked job. Pass env through so -e names resolve in the child shell.
        self._inner = SubprocessRunner(
            argv, cwd=mount, env=env, tail_lines=tail_lines,
            track_artifacts=track_artifacts,
        )
        self.image_digest: str | None = None

    def __call__(
        self,
        *,
        cancel_event: "threading.Event | None" = None,
        emit: "EmitFn | None" = None,
    ) -> dict:
        result = self._inner(cancel_event=cancel_event, emit=emit)
        # Stamp the resolved image reference onto the result so the run journal
        # records WHAT image produced the outputs (provenance).
        result["container"] = {
            "cli": os.path.basename(self.cli),
            "image": self.image,
            "image_digest": self._resolve_digest(),
        }
        return result

    def _resolve_digest(self) -> str | None:
        """Best-effort: the image's content digest, so the run pins the exact
        image, not just a mutable tag. Never raises."""
        if self.image_digest is not None:
            return self.image_digest
        try:
            out = subprocess.run(
                [self.cli, "inspect", "--format", "{{index .RepoDigests 0}}", self.image],
                capture_output=True, text=True, timeout=10,
            )
            digest = (out.stdout or "").strip()
            self.image_digest = digest or None
        except Exception:  # noqa: BLE001 - digest is best-effort provenance
            self.image_digest = None
        return self.image_digest
