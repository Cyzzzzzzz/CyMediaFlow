from __future__ import annotations

import os
from pathlib import Path


def path_is_within(path: Path, root: Path) -> bool:
    """Return whether path is inside root, including equivalent Windows path aliases."""

    candidate = path.resolve(strict=False)
    allowed = root.resolve(strict=False)
    try:
        candidate.relative_to(allowed)
        return True
    except ValueError:
        pass

    if not candidate.exists() or not allowed.exists():
        return False
    for ancestor in (candidate, *candidate.parents):
        try:
            if os.path.samefile(ancestor, allowed):
                return True
        except OSError:
            continue
    return False
