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


def _parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value, 10)
    except ValueError:
        return default


def apply_runtime_umask() -> None:
    """Set process umask for newly created files and directories.

    Default is 0o000 so that files/directories are created with the full
    requested mode bits (e.g. 0o666 / 0o777) and the container user's
    permissions match what Samba/other clients expect. On non-POSIX platforms
    this is a no-op.
    """
    if os.name != "posix":
        return
    os.umask(_parse_octal_env("AVIOR_DEDUP_UMASK", 0o000))


def ensure_output_permissions(path: str, is_dir: bool) -> None:
    """Best-effort chmod/chown for output artifacts.

    Controlled via env vars:
      - AVIOR_DEDUP_OUTPUT_DIR_MODE  (default: 0777)
      - AVIOR_DEDUP_OUTPUT_FILE_MODE (default: 0666)
      - AVIOR_DEDUP_OUTPUT_UID       (default: 99,  -1 to disable)
      - AVIOR_DEDUP_OUTPUT_GID       (default: 100, -1 to disable)

    On non-POSIX (Windows) this is a no-op. Failures are swallowed so the
    job is not aborted by permission-tuning issues (e.g. not running as root
    or on a filesystem that does not support chown).
    """
    if os.name != "posix":
        return

    mode = _parse_octal_env(
        "AVIOR_DEDUP_OUTPUT_DIR_MODE" if is_dir else "AVIOR_DEDUP_OUTPUT_FILE_MODE",
        0o777 if is_dir else 0o666,
    )

    try:
        os.chmod(path, mode)
    except OSError:
        pass

    uid = _parse_int_env("AVIOR_DEDUP_OUTPUT_UID", 99)
    gid = _parse_int_env("AVIOR_DEDUP_OUTPUT_GID", 100)
    if uid == -1 and gid == -1:
        return

    try:
        os.chown(path, uid, gid)  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        # Typical on non-root containers; do not fail the job.
        return


def copy_dir_permissions(src: str, dst: str) -> None:
    """Copy POSIX permissions and ownership from src to dst (best-effort).

    No-op on non-POSIX platforms. Errors are swallowed.
    """
    if os.name != "posix":
        return
    try:
        st = os.stat(src)
        mode = st.st_mode & 0o777
        uid = getattr(st, "st_uid", -1)
        gid = getattr(st, "st_gid", -1)
        try:
            os.chmod(dst, mode)
        except OSError:
            pass
        if uid != -1 or gid != -1:
            try:
                os.chown(dst, uid, gid)  # type: ignore[arg-type]
            except OSError:
                pass
    except Exception:
        return
