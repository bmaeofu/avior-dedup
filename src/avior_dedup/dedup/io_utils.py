from __future__ import annotations

from pathlib import Path
from typing import Optional


def read_text(path: str | Path) -> Optional[str]:
    """Read text content using a small fallback encoding chain."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None
