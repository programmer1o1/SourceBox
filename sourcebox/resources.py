"""Resource lookup shared by the UI, scenes, and packaged builds."""

from pathlib import Path
import sys
from typing import Iterable, Optional, Union


PathInput = Union[str, Path]


def application_root() -> Path:
    """Return the source tree or PyInstaller extraction root."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def resource_path(filename: PathInput) -> str:
    return str(application_root() / filename)


def find_resource(filenames: Union[PathInput, Iterable[PathInput]]) -> Optional[str]:
    if isinstance(filenames, (str, Path)):
        filenames = [filenames]

    for filename in filenames:
        candidate = application_root() / filename
        if candidate.exists():
            return str(candidate)
    return None


def load_text_resource(filename: PathInput) -> str:
    """Load a UTF-8 text resource without altering its line endings."""
    return (application_root() / filename).read_text(encoding="utf-8")
