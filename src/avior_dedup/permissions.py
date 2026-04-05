from __future__ import annotations

import os


def _parse_octal_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value, 8)
    except ValueError:
        return default


def apply_runtime_umask() -> None:
    """Set process umask for newly created files and directories.

    Default is 0o002 so files become group-writable (e.g. 664) and directories
    become group-writable (e.g. 775). On non-POSIX platforms this is a no-op.
    """
    if os.name != "posix":
        return
    os.umask(_parse_octal_env("AVIOR_DEDUP_UMASK", 0o002))


def ensure_output_permissions(path: str, is_dir: bool) -> None:
    """Best-effort chmod for output artifacts.

    Controlled via env vars:
      - AVIOR_DEDUP_OUTPUT_DIR_MODE (default: 2775)
      - AVIOR_DEDUP_OUTPUT_FILE_MODE (default: 664)
    """
    if os.name != "posix":
        return

    mode = _parse_octal_env(
        "AVIOR_DEDUP_OUTPUT_DIR_MODE" if is_dir else "AVIOR_DEDUP_OUTPUT_FILE_MODE",
        0o2775 if is_dir else 0o664,
    )

    try:
        os.chmod(path, mode)
    except OSError:
        # Do not fail the job on permission-tuning issues.
        return
