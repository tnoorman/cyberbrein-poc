import json
import math
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

ROUND_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SCHEMA_VERSION = 1


class RoundState(StrEnum):
    PREPARED = "PREPARED"
    COLLECTED = "COLLECTED"
    UNUSABLE = "UNUSABLE"
    STORED_UNCLEANED = "STORED_UNCLEANED"


ALLOWED_TRANSITIONS = frozenset(
    {
        (RoundState.PREPARED, RoundState.COLLECTED),
        (RoundState.COLLECTED, RoundState.UNUSABLE),
        (RoundState.COLLECTED, RoundState.STORED_UNCLEANED),
    }
)


class RoundStateError(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True, slots=True)
class RoundPaths:
    source: Path
    secret: Path
    zones_snapshot: Path
    state_record: Path

    @classmethod
    def for_round(cls, round_id: str) -> "RoundPaths":
        if ROUND_ID_PATTERN.fullmatch(round_id) is None:
            raise RoundStateError("invalid_measurement_round_id")
        return cls(
            source=Path("data/smoke") / f"{round_id}.sqlite",
            secret=Path("data/local") / f"{round_id}.secret",
            zones_snapshot=Path("data/local") / f"{round_id}.zones.geojson",
            state_record=Path("data/local") / f"{round_id}.round.json",
        )


@dataclass(frozen=True, slots=True)
class RoundRecord:
    round_id: str
    state: RoundState
    created_at_utc: datetime
    updated_at_utc: datetime
    max_gps_accuracy_m: float
    zones_sha256: str
    last_exit_code: int | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise RoundStateError("unsupported_round_state")
        if ROUND_ID_PATTERN.fullmatch(self.round_id) is None:
            raise RoundStateError("invalid_round_state")
        if not _is_utc(self.created_at_utc) or not _is_utc(self.updated_at_utc):
            raise RoundStateError("invalid_round_state")
        if self.updated_at_utc < self.created_at_utc:
            raise RoundStateError("invalid_round_state")
        if (
            isinstance(self.max_gps_accuracy_m, bool)
            or not isinstance(self.max_gps_accuracy_m, (int, float))
            or not math.isfinite(self.max_gps_accuracy_m)
            or self.max_gps_accuracy_m < 0
        ):
            raise RoundStateError("invalid_round_state")
        if SHA256_PATTERN.fullmatch(self.zones_sha256) is None:
            raise RoundStateError("invalid_round_state")
        if self.last_exit_code is not None and (
            not isinstance(self.last_exit_code, int) or isinstance(self.last_exit_code, bool)
        ):
            raise RoundStateError("invalid_round_state")


class RoundStateStore:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def create(self, record: RoundRecord) -> None:
        paths = RoundPaths.for_round(record.round_id)
        if paths.state_record.exists() or paths.state_record.is_symlink():
            raise RoundStateError("round_state_exists")
        self._write(record, create=True)

    def load(self, round_id: str) -> RoundRecord | None:
        path = RoundPaths.for_round(round_id).state_record
        try:
            file_status = path.lstat()
        except FileNotFoundError:
            return None
        if (
            stat.S_ISLNK(file_status.st_mode)
            or not stat.S_ISREG(file_status.st_mode)
            or stat.S_IMODE(file_status.st_mode) != 0o600
        ):
            raise RoundStateError("invalid_round_state")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            return _record_from_document(document)
        except RoundStateError:
            raise
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
            raise RoundStateError("invalid_round_state") from error

    def transition(
        self,
        round_id: str,
        to_state: RoundState,
        *,
        last_exit_code: int | None = None,
    ) -> RoundRecord:
        current = self.load(round_id)
        if current is None:
            raise RoundStateError("round_state_missing")
        if (current.state, to_state) not in ALLOWED_TRANSITIONS:
            raise RoundStateError("invalid_round_transition")
        updated = replace(
            current,
            state=to_state,
            updated_at_utc=self._clock().astimezone(timezone.utc),
            last_exit_code=last_exit_code,
        )
        self._write(updated, create=False)
        return updated

    def delete(self, round_id: str, *, missing_ok: bool = False) -> None:
        path = RoundPaths.for_round(round_id).state_record
        try:
            file_status = path.lstat()
            if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
                raise RoundStateError("invalid_round_state")
            path.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise RoundStateError("round_state_missing") from None
        except RoundStateError:
            raise
        except OSError as error:
            raise RoundStateError("round_state_delete_failed") from error

    def _write(self, record: RoundRecord, *, create: bool) -> None:
        path = RoundPaths.for_round(record.round_id).state_record
        temporary = path.with_name(f".{path.name}.tmp")
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            payload = json.dumps(_document_from_record(record), sort_keys=True) + "\n"
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if create and (path.exists() or path.is_symlink()):
                raise RoundStateError("round_state_exists")
            if not create:
                current_status = path.lstat()
                if stat.S_ISLNK(current_status.st_mode) or not stat.S_ISREG(current_status.st_mode):
                    raise RoundStateError("invalid_round_state")
            os.replace(temporary, path)
        except RoundStateError:
            raise
        except OSError as error:
            raise RoundStateError("round_state_write_failed") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)


def _document_from_record(record: RoundRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "round_id": record.round_id,
        "state": record.state.value,
        "created_at_utc": record.created_at_utc.isoformat(),
        "updated_at_utc": record.updated_at_utc.isoformat(),
        "max_gps_accuracy_m": record.max_gps_accuracy_m,
        "zones_sha256": record.zones_sha256,
        "last_exit_code": record.last_exit_code,
    }


def _record_from_document(document: Any) -> RoundRecord:
    if not isinstance(document, dict):
        raise RoundStateError("invalid_round_state")
    expected_keys = {
        "schema_version",
        "round_id",
        "state",
        "created_at_utc",
        "updated_at_utc",
        "max_gps_accuracy_m",
        "zones_sha256",
        "last_exit_code",
    }
    if set(document) != expected_keys:
        raise RoundStateError("invalid_round_state")
    try:
        return RoundRecord(
            schema_version=document["schema_version"],
            round_id=document["round_id"],
            state=RoundState(document["state"]),
            created_at_utc=datetime.fromisoformat(document["created_at_utc"]),
            updated_at_utc=datetime.fromisoformat(document["updated_at_utc"]),
            max_gps_accuracy_m=document["max_gps_accuracy_m"],
            zones_sha256=document["zones_sha256"],
            last_exit_code=document["last_exit_code"],
        )
    except (ValueError, TypeError) as error:
        raise RoundStateError("invalid_round_state") from error


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timezone.utc.utcoffset(value)
