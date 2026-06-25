"""Execution sandbox — tiered isolation that degrades to what the host allows.

Phase 4 (docs/ROADMAP.md). Research runs untrusted-ish code: a
downloaded analysis script, an LLM-generated snippet, a collaborator's
pipeline. The daemon should bound the blast radius. But the textbook
answer — "run it in an ephemeral Docker container" — is a fantasy on a
huge fraction of real research hosts: shared HPC login nodes routinely
ship without a usable Docker daemon, without rootless Podman, and with
unprivileged user namespaces locked down (so even `bwrap`/`unshare`
fail). Pretending a container sandbox exists when it doesn't is the same
dishonesty Research-OS refuses elsewhere (no-sbatch, no-snakemake).

So this module DETECTS the strongest isolation the host actually offers
and degrades transparently through three tiers:

  1. ``container`` — a working docker/podman runtime. Full filesystem +
     network + resource isolation via an ephemeral ``--rm`` container.
  2. ``namespace`` — bubblewrap (``bwrap``) or ``unshare`` with usable
     unprivileged user namespaces. Filesystem + network isolation, no
     container runtime needed.
  3. ``resource`` — ALWAYS available on POSIX. No FS/net isolation, but a
     hard cap on memory, CPU time, file size, and process count via
     ``resource.setrlimit`` in a ``preexec_fn``, plus a wallclock kill.
     Bounds the blast radius even when nothing else is permitted.

The detector is cached (capabilities don't change within a daemon's
life) and never raises — a probe failure just means "that tier is
unavailable", which is a legitimate, expected answer.

stdlib only (shutil, subprocess, resource, os).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

# Detection is stable for the life of a process; probe once.
_CACHE: SandboxCapabilities | None = None

# Tier names, strongest first. A caller asking for a tier gets that tier
# OR the strongest weaker one the host supports (never silently stronger).
TIERS = ("container", "namespace", "resource")


@dataclass
class ResourceLimits:
    """Per-run resource caps for the ``resource`` tier (and a hint to others).

    ``None`` means "do not cap this dimension". Defaults are deliberately
    generous — this is a guardrail against runaway jobs, not a tight jail.
    """

    address_space_mb: int | None = 4096  # RLIMIT_AS (virtual memory)
    cpu_seconds: int | None = 900        # RLIMIT_CPU (SIGXCPU then SIGKILL)
    file_size_mb: int | None = 2048      # RLIMIT_FSIZE (max file written)
    open_files: int | None = 1024        # RLIMIT_NOFILE
    # RLIMIT_NPROC counts ALL of the invoking USER's processes, not just this
    # run's tree — so a low cap on a busy shared/HPC host makes the very fork
    # that launches the workload fail with EAGAIN ("fork: Resource temporarily
    # unavailable"). It punishes the wrong thing. Default OFF; opt in only on
    # a dedicated host where this user's process count is yours to bound.
    processes: int | None = None         # RLIMIT_NPROC (opt-in fork-bomb guard)
    wall_seconds: int | None = 1800      # wallclock kill (timeout / watchdog)

    def to_dict(self) -> dict:
        return {
            "address_space_mb": self.address_space_mb,
            "cpu_seconds": self.cpu_seconds,
            "file_size_mb": self.file_size_mb,
            "open_files": self.open_files,
            "processes": self.processes,
            "wall_seconds": self.wall_seconds,
        }


@dataclass
class SandboxCapabilities:
    """What isolation this host can actually provide, probed at runtime."""

    best_tier: str
    container_runtime: str | None  # "docker" | "podman" | None (usable ones only)
    namespace_tool: str | None     # "bwrap" | "unshare" | None (usable ones only)
    resource_limits: bool          # POSIX resource.setrlimit available
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "best_tier": self.best_tier,
            "container_runtime": self.container_runtime,
            "namespace_tool": self.namespace_tool,
            "resource_limits": self.resource_limits,
            "tiers_available": self.tiers_available(),
            "notes": self.notes,
        }

    def tiers_available(self) -> list[str]:
        out = []
        if self.container_runtime:
            out.append("container")
        if self.namespace_tool:
            out.append("namespace")
        if self.resource_limits:
            out.append("resource")
        return out

    def resolve_tier(self, requested: str | None) -> str:
        """Return the strongest tier <= requested that this host supports.

        ``requested=None`` means "use the best available". A requested tier
        the host can't provide degrades DOWN to the next weaker one it can
        (never silently UP to something stronger than asked).
        """
        avail = self.tiers_available()
        if not avail:
            return "none"
        if requested is None or requested not in TIERS:
            return avail[0]  # tiers_available is already strongest-first
        # Walk from the requested tier toward weaker tiers.
        start = TIERS.index(requested)
        for tier in TIERS[start:]:
            if tier in avail:
                return tier
        return avail[0]


def _container_runtime_usable(binary: str) -> bool:
    """A container binary counts only if its daemon actually answers.

    ``docker`` is frequently installed on shared hosts but points at a
    dead/unreachable/permission-denied daemon — exactly this host. Probe
    ``info`` with a short timeout; anything but a clean exit = unusable.
    """
    if shutil.which(binary) is None:
        return False
    try:
        r = subprocess.run(
            [binary, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _userns_usable() -> bool:
    """Can we create an unprivileged user namespace with root-mapping?

    bwrap/unshare both need this to isolate the filesystem. Many hardened
    shared hosts disable it (seccomp/AppArmor/setuid restrictions) even
    when the sysctl flags look permissive. The only reliable test is to
    try and see if the uid_map write is permitted.
    """
    if shutil.which("unshare") is None:
        return False
    try:
        r = subprocess.run(
            ["unshare", "--user", "--map-root-user", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _resource_available() -> bool:
    """POSIX resource limits — available everywhere except Windows."""
    try:
        import resource  # noqa: F401
    except ImportError:  # pragma: no cover - Windows
        return False
    return os.name == "posix"


def detect_sandbox(*, refresh: bool = False) -> SandboxCapabilities:
    """Probe the host once and report the isolation tiers it supports."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    notes: list[str] = []

    container_runtime = None
    for rt in ("docker", "podman"):
        if _container_runtime_usable(rt):
            container_runtime = rt
            break
    if container_runtime is None:
        if shutil.which("docker") or shutil.which("podman"):
            notes.append(
                "container runtime installed but its daemon is unreachable "
                "or permission-denied; container tier unavailable"
            )
        else:
            notes.append("no container runtime (docker/podman) found")

    namespace_tool = None
    if _userns_usable():
        namespace_tool = "bwrap" if shutil.which("bwrap") else "unshare"
    else:
        notes.append(
            "unprivileged user namespaces are blocked on this host; "
            "namespace tier (bwrap/unshare) unavailable"
        )

    resource_limits = _resource_available()
    if resource_limits:
        notes.append(
            "resource tier (rlimits + wallclock) available as the universal "
            "floor — runs are bounded even where isolation is denied"
        )

    if container_runtime:
        best = "container"
    elif namespace_tool:
        best = "namespace"
    elif resource_limits:
        best = "resource"
    else:  # pragma: no cover - non-POSIX with nothing
        best = "none"

    _CACHE = SandboxCapabilities(
        best_tier=best,
        container_runtime=container_runtime,
        namespace_tool=namespace_tool,
        resource_limits=resource_limits,
        notes=notes,
    )
    return _CACHE


def make_preexec(limits: ResourceLimits):
    """Build a ``preexec_fn`` that applies rlimits in the child before exec.

    Returns ``None`` on non-POSIX (no preexec there). Each limit is
    best-effort: a platform that rejects one rlimit must not abort the run,
    so failures per-dimension are swallowed.
    """
    if os.name != "posix":  # pragma: no cover - Windows
        return None

    def _apply() -> None:  # pragma: no cover - runs in forked child
        import resource as _r

        def _set(which, value):
            if value is None:
                return
            try:
                _r.setrlimit(which, (value, value))
            except (ValueError, OSError):
                pass

        mb = 1024 * 1024
        _set(_r.RLIMIT_AS, limits.address_space_mb and limits.address_space_mb * mb)
        _set(_r.RLIMIT_CPU, limits.cpu_seconds)
        _set(_r.RLIMIT_FSIZE, limits.file_size_mb and limits.file_size_mb * mb)
        _set(_r.RLIMIT_NOFILE, limits.open_files)
        try:
            _set(_r.RLIMIT_NPROC, limits.processes)
        except AttributeError:
            pass

    return _apply


def wrap_command(
    cmd: list[str],
    *,
    tier: str,
    caps: SandboxCapabilities,
    limits: ResourceLimits,
    cwd: str | None = None,
    network: bool = False,
    image: str | None = None,
) -> list[str]:
    """Transform ``cmd`` into the sandbox-wrapped command for ``tier``.

    The ``resource`` tier does NOT alter the argv (limits are applied via a
    preexec_fn by the runner) but still prepends a wallclock ``timeout`` so
    a hung run is killed even if RLIMIT_CPU is exhausted by sleeping.
    Returns the (possibly unchanged) command list.

    ``image`` (container tier only) overrides the default container image;
    when ``None`` it falls back to ``$RESEARCH_OS_SANDBOX_IMAGE`` and then a
    minimal ``python:3.12-slim``. Image choice is deliberately a caller/env
    policy — a research run may need an R, Julia, or domain-specific image.
    """
    if tier == "container" and caps.container_runtime:
        rt = caps.container_runtime
        wrapped = [rt, "run", "--rm", "--init"]
        if not network:
            wrapped += ["--network", "none"]
        if limits.address_space_mb:
            wrapped += ["--memory", f"{limits.address_space_mb}m"]
        if cwd:
            wrapped += ["--workdir", "/work", "--volume", f"{cwd}:/work"]
        chosen = image or os.environ.get("RESEARCH_OS_SANDBOX_IMAGE") or "python:3.12-slim"
        wrapped += [chosen]
        wrapped += cmd
        return _with_wall_timeout(wrapped, limits)

    if tier == "namespace" and caps.namespace_tool == "bwrap":
        wrapped = ["bwrap", "--unshare-all", "--die-with-parent"]
        if network:
            wrapped += ["--share-net"]
        if cwd:
            wrapped += ["--bind", cwd, cwd, "--chdir", cwd]
        wrapped += ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib"]
        wrapped += cmd
        return _with_wall_timeout(wrapped, limits)

    if tier == "namespace" and caps.namespace_tool == "unshare":
        wrapped = ["unshare", "--user", "--map-root-user", "--pid", "--fork"]
        if not network:
            wrapped += ["--net"]
        wrapped += cmd
        return _with_wall_timeout(wrapped, limits)

    # resource tier (or unknown): argv unchanged, just a wallclock guard.
    return _with_wall_timeout(cmd, limits)


def _with_wall_timeout(cmd: list[str], limits: ResourceLimits) -> list[str]:
    """Prepend GNU ``timeout`` if a wallclock cap is set and available."""
    if limits.wall_seconds and shutil.which("timeout"):
        # -k 10: SIGKILL 10s after SIGTERM if the run ignores the term.
        return ["timeout", "-k", "10", str(limits.wall_seconds), *cmd]
    return cmd
