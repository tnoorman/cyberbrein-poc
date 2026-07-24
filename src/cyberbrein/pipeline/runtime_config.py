import json
import os
import stat
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from cyberbrein.processing.models import ApprovedZone


class RuntimeConfigurationError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def load_approved_zones(path: str | Path) -> tuple[ApprovedZone, ...]:
    """Load non-overlapping WGS84 zones without exposing file contents in errors."""
    try:
        zone_path = _regular_file(path)
        document = json.loads(zone_path.read_text(encoding="utf-8"))
        zones = _parse_feature_collection(document)
        _validate_zone_set(zones)
    except RuntimeConfigurationError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        raise RuntimeConfigurationError("invalid_zone_file") from error
    return zones


def load_secret(path: str | Path) -> str:
    """Read one secret line from a regular, non-symlink file with mode 600."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode) or stat.S_IMODE(file_status.st_mode) != 0o600:
            raise RuntimeConfigurationError("invalid_secret_file")
        with os.fdopen(descriptor, "rb") as secret_file:
            descriptor = None
            raw_secret = secret_file.read()
        secret = raw_secret.decode("utf-8")
        if secret.endswith("\n"):
            secret = secret[:-1]
            if secret.endswith("\r"):
                secret = secret[:-1]
        if "\n" in secret or "\r" in secret or len(secret) < 32:
            raise RuntimeConfigurationError("invalid_secret_file")
        return secret
    except RuntimeConfigurationError:
        raise
    except (OSError, UnicodeError) as error:
        raise RuntimeConfigurationError("invalid_secret_file") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _regular_file(path: str | Path) -> Path:
    resolved = Path(path)
    file_status = resolved.lstat()
    if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
        raise RuntimeConfigurationError("invalid_zone_file")
    return resolved


def _parse_feature_collection(document: Any) -> tuple[ApprovedZone, ...]:
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise RuntimeConfigurationError("invalid_zone_file")
    if "crs" in document:
        raise RuntimeConfigurationError("invalid_zone_file")
    features = document.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeConfigurationError("invalid_zone_file")

    zones: list[ApprovedZone] = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise RuntimeConfigurationError("invalid_zone_file")
        properties = feature.get("properties")
        geometry_document = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry_document, dict):
            raise RuntimeConfigurationError("invalid_zone_file")
        zone_id = properties.get("zone_id")
        if not isinstance(zone_id, str) or not zone_id.strip():
            raise RuntimeConfigurationError("invalid_zone_file")
        try:
            geometry = shape(geometry_document)
            zones.append(ApprovedZone(zone_id=zone_id.strip(), geometry=geometry))
        except (ValueError, TypeError) as error:
            raise RuntimeConfigurationError("invalid_zone_file") from error
    return tuple(zones)


def _validate_zone_set(zones: tuple[ApprovedZone, ...]) -> None:
    zone_ids = [zone.zone_id for zone in zones]
    if len(zone_ids) != len(set(zone_ids)):
        raise RuntimeConfigurationError("invalid_zone_file")
    for index, first in enumerate(zones):
        for second in zones[index + 1 :]:
            if first.geometry.intersects(second.geometry):
                raise RuntimeConfigurationError("invalid_zone_file")
