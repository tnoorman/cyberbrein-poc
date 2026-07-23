import json
import os
from pathlib import Path

import pytest

from cyberbrein.pipeline.runtime_config import (
    RuntimeConfigurationError,
    load_approved_zones,
    load_secret,
)


def _feature(zone_id: str, x_offset: float = 0.0) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {"zone_id": zone_id},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [x_offset, 0],
                    [x_offset + 1, 0],
                    [x_offset + 1, 1],
                    [x_offset, 1],
                    [x_offset, 0],
                ]
            ],
        },
    }


def _write_geojson(path: Path, features: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


def test_loads_valid_non_overlapping_zones(tmp_path: Path) -> None:
    path = tmp_path / "zones.geojson"
    _write_geojson(path, [_feature("zone-a"), _feature("zone-b", 2)])

    zones = load_approved_zones(path)

    assert [zone.zone_id for zone in zones] == ["zone-a", "zone-b"]
    assert all(zone.geometry.geom_type == "Polygon" for zone in zones)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"type": "FeatureCollection", "features": []},
        {"type": "FeatureCollection", "features": [_feature("")]},
        {"type": "FeatureCollection", "features": [_feature("zone-a")], "crs": {}},
    ],
)
def test_rejects_invalid_geojson_documents(tmp_path: Path, document: object) -> None:
    path = tmp_path / "zones.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RuntimeConfigurationError, match="invalid_zone_file"):
        load_approved_zones(path)


def test_rejects_duplicate_zone_ids(tmp_path: Path) -> None:
    path = tmp_path / "zones.geojson"
    _write_geojson(path, [_feature("zone-a"), _feature("zone-a", 2)])

    with pytest.raises(RuntimeConfigurationError, match="invalid_zone_file"):
        load_approved_zones(path)


@pytest.mark.parametrize("second_offset", [0.5, 1.0])
def test_rejects_overlapping_or_touching_zones(
    tmp_path: Path,
    second_offset: float,
) -> None:
    path = tmp_path / "zones.geojson"
    _write_geojson(path, [_feature("zone-a"), _feature("zone-b", second_offset)])

    with pytest.raises(RuntimeConfigurationError, match="invalid_zone_file"):
        load_approved_zones(path)


def test_rejects_zone_file_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.geojson"
    link = tmp_path / "zones.geojson"
    _write_geojson(target, [_feature("zone-a")])
    link.symlink_to(target)

    with pytest.raises(RuntimeConfigurationError, match="invalid_zone_file"):
        load_approved_zones(link)


def test_loads_secret_from_mode_600_file(tmp_path: Path) -> None:
    path = tmp_path / "round.secret"
    expected = "a" * 64
    path.write_text(f"{expected}\n", encoding="utf-8")
    path.chmod(0o600)

    assert load_secret(path) == expected


@pytest.mark.parametrize("mode", [0o400, 0o640, 0o644])
def test_rejects_secret_with_wrong_permissions(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "round.secret"
    path.write_text("a" * 64, encoding="utf-8")
    path.chmod(mode)

    with pytest.raises(RuntimeConfigurationError, match="invalid_secret_file"):
        load_secret(path)


@pytest.mark.parametrize("value", ["short", f"{'a' * 32}\n{'b' * 32}", "a" * 31])
def test_rejects_invalid_secret_content(tmp_path: Path, value: str) -> None:
    path = tmp_path / "round.secret"
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(RuntimeConfigurationError, match="invalid_secret_file"):
        load_secret(path)


def test_rejects_secret_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.secret"
    link = tmp_path / "round.secret"
    target.write_text("a" * 64, encoding="utf-8")
    target.chmod(0o600)
    link.symlink_to(target)

    with pytest.raises(RuntimeConfigurationError, match="invalid_secret_file"):
        load_secret(link)


def test_secret_loader_does_not_change_permissions(tmp_path: Path) -> None:
    path = tmp_path / "round.secret"
    path.write_text("a" * 64, encoding="utf-8")
    path.chmod(0o600)

    load_secret(path)

    assert os.stat(path).st_mode & 0o777 == 0o600
