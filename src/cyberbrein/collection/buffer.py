import sqlite3
from pathlib import Path


def is_empty_source_buffer(source_path: Path) -> bool | None:
    """Return buffer emptiness, or None when the Collection-owned schema is unreadable."""
    try:
        if source_path.is_symlink() or not source_path.is_file():
            return None
        if source_path.stat().st_size == 0:
            return True
        with sqlite3.connect(f"file:{source_path.absolute()}?mode=ro", uri=True) as connection:
            count = connection.execute("SELECT count(*) FROM raw_observation").fetchone()
        if count is None:
            return None
        return count[0] == 0
    except (OSError, sqlite3.Error):
        return None
