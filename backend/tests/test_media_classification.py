from pathlib import Path

import pytest

from app.domain.filename_parser import FilenameParser
from app.domain.media_classification import classify_media


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("Season 1/SPs/Show [01(NC Ver.)].mkv", "special"),
        ("Season 1/SPs/Nested/Show [Menu01].mkv", "special"),
        ("Season 1/Show S01EOVA.mkv", "special"),
        ("Season 1/Show S01E01.mkv", "regular"),
    ],
)
def test_classifies_plural_special_folders_and_unnumbered_ova(
    relative_path: str, expected: str
) -> None:
    path = Path(relative_path)
    parsed = FilenameParser().parse(path.name, parent_directory="Show")

    assert classify_media(path, parsed) == expected
