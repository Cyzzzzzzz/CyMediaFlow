from __future__ import annotations

import re
from pathlib import Path

from app.domain.filename import ParsedMediaInfo

EXTRA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fonts", re.compile(r"(?:^|[/\\\[\] ._-])fonts?(?:$|[/\\\[\] ._-])", re.I)),
    ("menu", re.compile(r"(?:^|[/\\\[\] ._-])menus?(?:$|[/\\\[\] ._-])", re.I)),
    ("credit", re.compile(r"(?:NCOP|NCED)(?:\s*[&+/-]\s*(?:NCOP|NCED))?", re.I)),
    ("pv", re.compile(r"(?:^|[/\\\[\] ._-])PV\d*(?:$|[/\\\[\] ._-])", re.I)),
    ("dialogue", re.compile(r"对话|對話|dialogue", re.I)),
    ("phone", re.compile(r"电话|電話|phone", re.I)),
    ("bonus", re.compile(r"特典映像|特典|bonus|extras?", re.I)),
)
EXTRA_FOLDER_NAMES = {
    "fonts": "fonts",
    "font": "fonts",
    "menu": "menu",
    "menus": "menu",
    "ncop&nced": "credit",
    "ncop+nced": "credit",
    "ncop": "credit",
    "nced": "credit",
    "pv": "pv",
    "sp": "special",
    "对话": "dialogue",
    "對話": "dialogue",
    "电话": "phone",
    "電話": "phone",
    "特典映像": "bonus",
    "特典": "bonus",
}


def classify_media(relative_path: Path, parsed: ParsedMediaInfo) -> str:
    parent_name = relative_path.parent.name.strip(" []").casefold()
    if parent_name in EXTRA_FOLDER_NAMES:
        return EXTRA_FOLDER_NAMES[parent_name]
    for category, pattern in EXTRA_PATTERNS:
        if pattern.search(relative_path.name):
            return category
    if parsed.special_type:
        return "special"
    return "regular"
