"""Scheduler runners — the daemon's "HPC-native execution" layer.

JUDGE-6 (docs/ROADMAP.md §8): real computational science runs on shared
clusters, not just the login node. A researcher's work is ``sbatch
train.sh`` — submitted to a queue, run minutes-to-hours later on a compute
node, with output landing in files. If Research-OS can only spawn local
subprocesses it abandons the user exactly when the work gets serious.

This module gives scheduler jobs the SAME treatment as local runs: they
flow through the identical ``TaskQueue.submit(callable)`` seam, stream
state transitions as ``job.log`` events, capture artifacts via the same
cwd-diff, and land in the durable run journal — so ``daemon runs``,
``daemon logs`` and even ``daemon reproduce`` work on a SLURM job exactly
as they do on a bash one.

The design mirrors SubprocessRunner: a runner is a callable the queue
schedules; it accepts ``cancel_event`` (→ ``scancel``) and ``emit`` (→
state-transition log lines) and returns a RunResult-shaped dict (a
*handle*: scheduler job id, final state, exit code, artifacts). The worker
thread blocks polling the scheduler until the cluster job is terminal —
the daemon owns the wait so the chat client doesn't have to.

stdlib only (subprocess, shlex, re, time). SLURM first (sbatch/sacct/
scancel); the SchedulerAdapter protocol lets snakemake/nextflow/PBS slot
in behind the same interface later. Absent scheduler → a clear, actionable
error, never a crash.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

EmitFn = Callable[[str, dict], None]

# SLURM states that mean "still going" — anything else is terminal.
_SLURM_ACTIVE = {
    "PENDING", "RUNNING", "REQUEUED", "RESIZING", "SUSPENDED", "CONFIGURING",
    "COMPLETING", "SIGNALING", "STAGE_OUT", "PREEMPTED",
}
# SLURM terminal states that count as success vs failure.
_SLURM_SUCCESS = {"COMPLETED"}
_SLURM_FAILURE = {
    "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY",
    "BOOT_FAIL", "DEADLINE", "REVOKED", "SPECIAL_EXIT",
}


@dataclass
class SchedulerResult:
    """Outcome of a scheduler job — a handle, not a payload dump.

    Shaped to be a superset of runners.RunResult so it flows through the
    same journal/artifact/reproduce machinery unchanged.
    """

    returncode: int
    cmd: list[str]
    cwd: str | None
    duration_s: float
    scheduler: str
    scheduler_job_id: str | None
    final_state: str | None
    submitted: bool = False
    cancelled: bool = False
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)
    truncated: bool = False
    artifacts: list[dict] = field(default_factory=list)
    artifacts_truncated: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.cancelled and self.error is None

    def to_dict(self) -> dict:
        return {
            "returncode": self.returncode,
            "ok": self.ok,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "duration_s": round(self.duration_s, 3),
            "scheduler": self.scheduler,
            "scheduler_job_id": self.scheduler_job_id,
            "final_state": self.final_state,
            "submitted": self.submitted,
            "cancelled": self.cancelled,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "truncated": self.truncated,
            "artifacts": self.artifacts,
            "artifacts_truncated": self.artifacts_truncated,
            "error": self.error,
        }


class SchedulerAdapter(Protocol):
    """The contract every scheduler backend implements.

    Keeps SLURM/PBS/LSF interchangeable behind SchedulerRunner. Each method
    shells out to the scheduler's CLI and returns parsed primitives.
    """

    name: str

    def available(self) -> bool: ...
    def submit(self, script: str, *, cwd: str | None, env: dict | None) -> str: ...
    def poll(self, job_id: str) -> tuple[str, int | None]: ...
    def cancel(self, job_id: str) -> None: ...


class SlurmAdapter:
    """SLURM backend: sbatch to submit, sacct/squeue to poll, scancel to kill."""

    name = "slurm"

    def __init__(
        self,
        *,
        sbatch: str = "sbatch",
        sacct: str = "sacct",
        squeue: str = "squeue",
        scancel: str = "scancel",
    ) -> None:
        self._sbatch = sbatch
        self._sacct = sacct
        self._squeue = squeue
        self._scancel = scancel

    def available(self) -> bool:
        return shutil.which(self._sbatch) is not None

    def submit(self, script: str, *, cwd: str | None, env: dict | None) -> str:
        """Submit a batch script (path or inline) and return the SLURM job id.

        Uses ``--parsable`` so stdout is exactly ``<jobid>`` (or
        ``<jobid>;<cluster>``). If ``script`` is an existing file it's passed
        as the batch script; otherwise it's piped to sbatch as stdin (so a
        bare command string works without the user writing a .sh file).
        """
        run_env = None
        if env is not None:
            run_env = {**os.environ, **{str(k): str(v) for k, v in env.items()}}
        is_file = os.path.isfile(script)
        argv = [self._sbatch, "--parsable"]
        if is_file:
            argv.append(script)
            proc = subprocess.run(
                argv, cwd=cwd, env=run_env, capture_output=True, text=True,
            )
        else:
            # Inline: wrap the command in a minimal sbatch script via stdin.
            wrapped = script if script.lstrip().startswith("#!") else f"#!/bin/bash\n{script}\n"
            proc = subprocess.run(
                argv, cwd=cwd, env=run_env, input=wrapped,
                capture_output=True, text=True,
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"sbatch failed (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            )
        out = proc.stdout.strip()
        job_id = out.split(";")[0].strip()
        if not re.fullmatch(r"\d+", job_id):
            raise RuntimeError(f"could not parse sbatch job id from: {out!r}")
        return job_id

    def poll(self, job_id: str) -> tuple[str, int | None]:
        """Return (state, exit_code). exit_code is None until terminal.

        Prefers sacct (authoritative, has exit codes + post-completion
        records); falls back to squeue for the brief window before the
        accounting record exists.
        """
        state, code = self._poll_sacct(job_id)
        if state is not None:
            return state, code
        # Fallback: job too fresh for sacct, or accounting disabled.
        sq = self._poll_squeue(job_id)
        if sq is not None:
            return sq, None
        # No record anywhere: assume it finished and accounting is off.
        return "COMPLETED", 0

    def _poll_sacct(self, job_id: str) -> tuple[str | None, int | None]:
        proc = subprocess.run(
            [self._sacct, "-j", f"{job_id}.batch,{job_id}",
             "--format=State,ExitCode", "--noheader", "--parsable2"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None, None
        # Take the primary job line (first non-empty). State may carry a
        # suffix like "CANCELLED by 12345" — keep the leading token.
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            state = parts[0].strip().split()[0] if parts[0].strip() else ""
            if not state:
                continue
            code: int | None = None
            if len(parts) > 1 and ":" in parts[1]:
                try:
                    code = int(parts[1].split(":")[0])
                except ValueError:
                    code = None
            return state, code
        return None, None

    def _poll_squeue(self, job_id: str) -> str | None:
        proc = subprocess.run(
            [self._squeue, "-j", job_id, "-h", "-o", "%T"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None
        out = proc.stdout.strip()
        return out.split()[0] if out else None

    def cancel(self, job_id: str) -> None:
        subprocess.run([self._scancel, job_id], capture_output=True, text=True)


# Registry of known schedulers, by name.
_ADAPTERS: dict[str, Callable[[], SchedulerAdapter]] = {
    "slurm": SlurmAdapter,
}


def get_adapter(name: str) -> SchedulerAdapter:
    factory = _ADAPTERS.get(name.lower())
    if factory is None:
        known = ", ".join(sorted(_ADAPTERS)) or "(none)"
        raise ValueError(f"unknown scheduler {name!r}; known: {known}")
    return factory()


class SchedulerRunner:
    """Submit a job to an HPC scheduler and own the wait for it.

    Fits the TaskQueue callable seam: the worker thread submits, then blocks
    polling the scheduler until the cluster job reaches a terminal state,
    emitting a ``job.log`` line on every state transition so live tailing
    shows PENDING → RUNNING → COMPLETED. On ``cancel_event`` it issues
    ``scancel`` and waits for the cancellation to take.

    Returns a RunResult-shaped dict so the durable journal, artifact diff
    and reproduce verdict all work on scheduler jobs unchanged.
    """

    def __init__(
        self,
        script: str,
        *,
        scheduler: str = "slurm",
        cwd: str | None = None,
        env: dict | None = None,
        poll_interval: float = 5.0,
        cancel_grace_s: float = 30.0,
        track_artifacts: bool = True,
        adapter: SchedulerAdapter | None = None,
    ) -> None:
        self.script = script
        self.scheduler = scheduler
        self.cwd = cwd
        self.env = env
        self.poll_interval = max(0.05, poll_interval)
        self.cancel_grace_s = cancel_grace_s
        self.track_artifacts = track_artifacts
        self._adapter = adapter or get_adapter(scheduler)

    def __call__(
        self,
        *,
        cancel_event: threading.Event | None = None,
        emit: EmitFn | None = None,
    ) -> dict:
        cancel_event = cancel_event or threading.Event()
        start = time.time()

        def _log(line: str, channel: str = "scheduler") -> None:
            if emit is not None:
                try:
                    emit("job.log", {"channel": channel, "line": line})
                except Exception:  # noqa: BLE001 - telemetry never breaks a run
                    pass

        if not self._adapter.available():
            msg = (
                f"scheduler {self.scheduler!r} not available on this host "
                f"(is it a login/compute node with the CLI installed?)"
            )
            _log(msg, "stderr")
            return SchedulerResult(
                returncode=127, cmd=[self.script], cwd=self.cwd,
                duration_s=time.time() - start, scheduler=self.scheduler,
                scheduler_job_id=None, final_state=None, submitted=False,
                error=msg,
            ).to_dict()

        # Artifact fingerprint of the working dir before submission.
        art_root = self.cwd or os.getcwd()
        art_before: dict = {}
        if self.track_artifacts:
            from . import artifacts as _artifacts

            art_before = _artifacts.snapshot(art_root)

        # Submit.
        try:
            job_id = self._adapter.submit(self.script, cwd=self.cwd, env=self.env)
        except Exception as exc:  # noqa: BLE001 - report submission failure cleanly
            msg = f"submission failed: {exc}"
            _log(msg, "stderr")
            return SchedulerResult(
                returncode=1, cmd=[self.script], cwd=self.cwd,
                duration_s=time.time() - start, scheduler=self.scheduler,
                scheduler_job_id=None, final_state=None, submitted=False,
                error=msg,
            ).to_dict()

        _log(f"submitted {self.scheduler} job {job_id}")

        # Poll until terminal or cancelled.
        last_state: str | None = None
        exit_code: int | None = None
        cancelled = False
        final_state: str | None = None
        while True:
            if cancel_event.is_set():
                _log(f"cancelling {self.scheduler} job {job_id} (scancel)")
                self._adapter.cancel(job_id)
                cancelled = True
                # Give the scheduler a moment to register the cancel.
                grace_deadline = time.time() + self.cancel_grace_s
                while time.time() < grace_deadline:
                    state, code = self._adapter.poll(job_id)
                    if state not in _SLURM_ACTIVE:
                        final_state, exit_code = state, code
                        break
                    time.sleep(self.poll_interval)
                final_state = final_state or "CANCELLED"
                break

            try:
                state, code = self._adapter.poll(job_id)
            except Exception as exc:  # noqa: BLE001 - transient sacct hiccup
                _log(f"poll error (retrying): {exc}", "stderr")
                time.sleep(self.poll_interval)
                continue

            if state != last_state:
                _log(f"state: {state}")
                last_state = state

            if state not in _SLURM_ACTIVE:
                final_state, exit_code = state, code
                break
            time.sleep(self.poll_interval)

        # Map the scheduler's terminal state to a returncode.
        if cancelled:
            rc = exit_code if exit_code is not None else 130
        elif final_state in _SLURM_SUCCESS:
            rc = exit_code if exit_code is not None else 0
        elif final_state in _SLURM_FAILURE:
            rc = exit_code if (exit_code is not None and exit_code != 0) else 1
        else:
            rc = exit_code if exit_code is not None else 0

        # Diff the working dir for artifacts the cluster job produced.
        art_list: list[dict] = []
        art_trunc = False
        if self.track_artifacts:
            from . import artifacts as _artifacts

            art = _artifacts.diff(art_root, art_before)
            art_list = art.get("artifacts", [])
            art_trunc = art.get("truncated", False)

        return SchedulerResult(
            returncode=rc,
            cmd=[self.script],
            cwd=self.cwd,
            duration_s=time.time() - start,
            scheduler=self.scheduler,
            scheduler_job_id=job_id,
            final_state=final_state,
            submitted=True,
            cancelled=cancelled,
            artifacts=art_list,
            artifacts_truncated=art_trunc,
        ).to_dict()
