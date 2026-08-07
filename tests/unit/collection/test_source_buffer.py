import sqlite3
from pathlib import Path

from cyberbrein.collection.buffer import is_empty_source_buffer


def test_zero_length_source_buffer_is_empty(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    source.touch()

    assert is_empty_source_buffer(source) is True


def test_collection_schema_reports_empty_and_nonempty_buffers(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE raw_observation (value TEXT)")
    assert is_empty_source_buffer(source) is True

    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO raw_observation VALUES ('observation')")
    assert is_empty_source_buffer(source) is False


def test_unreadable_or_unsafe_source_buffer_is_unknown(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    corrupt = tmp_path / "corrupt.sqlite"
    target = tmp_path / "target.sqlite"
    link = tmp_path / "source.sqlite"
    corrupt.write_bytes(b"not-sqlite")
    target.touch()
    link.symlink_to(target)

    assert is_empty_source_buffer(missing) is None
    assert is_empty_source_buffer(corrupt) is None
    assert is_empty_source_buffer(link) is None
