"""Single source of truth for host-side filesystem paths.

All entry points (``agentspex``, ``agentspex run``, ``agentspex cli``,
``scripts/run_agent.sh``, benchmarks) route path resolution through here so
output locations do not depend on the current working directory or on whether
``config/host.env`` has been sourced.

Layout::

    <PROJECT_ROOT>/workspace/              # mounted into the container as /workspace
    <PROJECT_ROOT>/workspace_persistent/   # host-only persistent store
    <PROJECT_ROOT>/workspace_persistent/outputs/<task>/   # logs, checkpoints, artifacts

Environment overrides ``HOST_WORKSPACE`` and ``WORKSPACE_PERSISTENT`` are
honored when set (matching ``config/host.env``); otherwise defaults are derived
from the project root.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RUN_TIMESTAMP_FMT = "%Y%m%d-%H%M%S"


def host_workspace() -> Path:
    """Host directory mounted as ``/workspace`` in the sandbox container."""
    env = os.environ.get("HOST_WORKSPACE")
    return Path(env).resolve() if env else PROJECT_ROOT / "workspace"


def workspace_persistent() -> Path:
    """Host-only persistent store for logs, checkpoints, and outputs."""
    env = os.environ.get("WORKSPACE_PERSISTENT")
    return Path(env).resolve() if env else PROJECT_ROOT / "workspace_persistent"


def outputs_root() -> Path:
    """Root directory for all run outputs."""
    return workspace_persistent() / "outputs"


def task_output_dir(task_name: str) -> Path:
    """Host-side output directory for a named task/run.

    Does *not* include a timestamp; use :func:`new_run_dir` for fresh runs and
    :func:`find_latest_run_dir` for resume.
    """
    return outputs_root() / task_name


def new_run_dir(task_name: str, timestamp: Optional[str] = None) -> Path:
    """Return a fresh, timestamped output directory for a run.

    The timestamp suffix ensures repeated runs of the same workflow do not
    overwrite each other. Format: ``<task_name>_YYYYMMDD-HHMMSS``.
    """
    ts = timestamp or datetime.now().strftime(RUN_TIMESTAMP_FMT)
    return outputs_root() / f"{task_name}_{ts}"


def find_latest_run_dir(task_name: str) -> Optional[Path]:
    """Return the most recent output directory for ``task_name``, or None.

    Considers both timestamped runs (``<task>_YYYYMMDD-HHMMSS``) and a legacy
    un-timestamped directory (``<task>``) for backward compatibility. Used by
    resume flows to locate an existing checkpoint.
    """
    root = outputs_root()
    if not root.exists():
        return None
    candidates = [p for p in root.glob(f"{task_name}_*") if p.is_dir()]
    legacy = root / task_name
    if legacy.is_dir():
        candidates.append(legacy)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def peek_task_name(workflow_file: Optional[str]) -> Optional[str]:
    """Read the top-level ``name:`` key from a workflow YAML without full parse.

    We need the task name *before* the harness runs YAML env-var expansion
    (because the injected ``AGENTSPEX_RUN_*`` env vars depend on the task
    name). A lightweight scan avoids the chicken-and-egg problem of needing
    the env vars to parse the YAML that tells us the task name.
    """
    if not workflow_file:
        return None
    try:
        with open(workflow_file, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("name:"):
                    value = line.split(":", 1)[1].strip().strip('"').strip("'")
                    value = os.path.expandvars(value)
                    return value or None
                # ``name:`` is conventionally the first non-comment key. If we
                # encounter any other top-level key first, stop — better to
                # fall back to the filename than misread a nested key.
                if line and not line.startswith((" ", "\t", "-")):
                    break
    except Exception:
        return None
    return None


_RUN_ENV_KEYS = (
    "AGENTSPEX_RUN_ID",
    "AGENTSPEX_RUN_SANDBOX_DIR",
    "AGENTSPEX_RUN_SANDBOX_DIR_ABS",
    "AGENTSPEX_RUN_HOST_DIR",
)


def run_env_keys() -> tuple[str, ...]:
    """Names of env vars the harness injects; callers forward these into the container."""
    return _RUN_ENV_KEYS


def init_run_env(
    task_name: str,
    override_run_id: Optional[str] = None,
    resume: bool = False,
) -> tuple[str, Path]:
    """Populate ``AGENTSPEX_RUN_*`` env vars and return ``(run_id, host_run_dir)``.

    This is the single point where per-run paths are decided. All entry
    points (``agentspex run``, ``agentspex cli``, ``run_agent.sh`` via
    Python) call this before YAML parsing so workflow authors can use
    ``${AGENTSPEX_RUN_SANDBOX_DIR_ABS}`` in their YAML and it resolves to
    a run-scoped directory on both the host and the sandbox.

    Resolution order for the run id:
      1. ``override_run_id`` (caller-provided — used by tests or external schedulers).
      2. Existing ``AGENTSPEX_RUN_ID`` in the environment (idempotent when
         called multiple times in one process, or when a parent shell has
         already decided the id).
      3. On ``resume=True``, the dirname of the most recent matching run dir.
      4. Otherwise, a fresh ``<task_name>_<YYYYMMDD-HHMMSS>`` id.
    """
    ensure_runtime_dirs()

    existing = os.environ.get("AGENTSPEX_RUN_ID")
    if override_run_id:
        run_id = override_run_id
    elif existing:
        run_id = existing
    elif resume:
        latest = find_latest_run_dir(task_name)
        run_id = latest.name if latest is not None else (
            f"{task_name}_{datetime.now().strftime(RUN_TIMESTAMP_FMT)}"
        )
    else:
        run_id = f"{task_name}_{datetime.now().strftime(RUN_TIMESTAMP_FMT)}"

    sandbox_rel = f"outputs/{run_id}"
    sandbox_abs = f"/workspace/{sandbox_rel}"
    host_run = outputs_root() / run_id
    host_run.mkdir(parents=True, exist_ok=True)

    os.environ["AGENTSPEX_RUN_ID"] = run_id
    os.environ["AGENTSPEX_RUN_SANDBOX_DIR"] = sandbox_rel
    os.environ["AGENTSPEX_RUN_SANDBOX_DIR_ABS"] = sandbox_abs
    os.environ["AGENTSPEX_RUN_HOST_DIR"] = str(host_run)

    return run_id, host_run


def ensure_runtime_dirs() -> None:
    """Create the runtime directories and export env vars for subprocesses.

    Idempotent. Safe to call from any entry point before path-dependent work.
    Exports ``HOST_WORKSPACE`` and ``WORKSPACE_PERSISTENT`` so Docker containers
    and shell scripts spawned by the current process see the same absolute
    paths Python is using.
    """
    ws = host_workspace()
    wp = workspace_persistent()
    ws.mkdir(parents=True, exist_ok=True)
    (wp / "outputs").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HOST_WORKSPACE", str(ws))
    os.environ.setdefault("WORKSPACE_PERSISTENT", str(wp))
