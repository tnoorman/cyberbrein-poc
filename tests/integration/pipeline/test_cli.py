import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cyberbrein.collection.models import RawObservation
from cyberbrein.collection.sqlite_writer import SQLiteObservationWriter
from cyberbrein.pipeline.cli import main
from cyberbrein.pipeline.models import PipelineRuntimeError
from cyberbrein.pipeline.runtime_inputs import cleanup_runtime_inputs

SYNTHETIC_BSSID = "02:00:00:00:00:99"
SYNTHETIC_SSID = "SYNTHETIC-PRIVATE-NETWORK"
SYNTHETIC_SECRET = "s" * 64


def _write_source(path: Path) -> None:
    SQLiteObservationWriter(path).write(
        RawObservation(
            measurement_round_id="synthetic-round",
            observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            bssid=SYNTHETIC_BSSID,
            ssid=SYNTHETIC_SSID,
            rssi_dbm=-50,
            channel=36,
            frequency_mhz=5180,
            band="5GHz",
            encryption="WPA2/PSK",
            frame_type="BEACON",
            latitude=0.5,
            longitude=0.5,
            gps_mode=3,
            gps_accuracy_m=3.0,
        )
    )


def _write_zones(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"zone_id": "zone-a"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_secret(path: Path, mode: int = 0o600) -> None:
    path.write_text(SYNTHETIC_SECRET, encoding="utf-8")
    path.chmod(mode)


def _arguments(source: Path, zones: Path, secret: Path) -> list[str]:
    return [
        "--source-db",
        str(source),
        "--measurement-round-id",
        "synthetic-round",
        "--zones",
        str(zones),
        "--secret-file",
        str(secret),
    ]


def test_cli_processes_without_deleting_inputs_by_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clean_postgis: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    zones = tmp_path / "zones.geojson"
    secret = tmp_path / "round.secret"
    _write_source(source)
    _write_zones(zones)
    _write_secret(secret)

    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", clean_postgis)
    exit_code = main(_arguments(source, zones, secret))

    assert exit_code == 0
    assert source.exists()
    assert secret.exists()
    captured = capsys.readouterr()
    assert "Ingestion geaccepteerd: 1" in captured.out
    assert "Netwerkvondsten opgeslagen: 1" in captured.out
    assert "Ruwe invoer verwijderd: nee" in captured.out
    for private_value in (SYNTHETIC_BSSID, SYNTHETIC_SSID, SYNTHETIC_SECRET, "0.5"):
        assert private_value not in captured.out
        assert private_value not in captured.err


def test_cli_cleanup_removes_source_sidecars_and_secret(
    tmp_path: Path,
    clean_postgis: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    zones = tmp_path / "zones.geojson"
    secret = tmp_path / "round.secret"
    _write_source(source)
    _write_zones(zones)
    _write_secret(secret)
    sidecars = [source.with_name(f"{source.name}{suffix}") for suffix in ("-wal", "-shm")]
    for sidecar in sidecars:
        sidecar.touch()

    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", clean_postgis)
    exit_code = main([*_arguments(source, zones, secret), "--delete-source-on-success"])

    assert exit_code == 0
    assert not source.exists()
    assert not secret.exists()
    assert all(not sidecar.exists() for sidecar in sidecars)


def test_invalid_secret_permissions_fail_without_sensitive_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.sqlite"
    zones = tmp_path / "zones.geojson"
    secret = tmp_path / "round.secret"
    _write_source(source)
    _write_zones(zones)
    _write_secret(secret, mode=0o644)

    exit_code = main(_arguments(source, zones, secret))

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "Pipeline mislukt: invalid_secret_file"
    assert source.exists()
    assert secret.exists()


def test_pipeline_failure_keeps_source_and_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    zones = tmp_path / "zones.geojson"
    secret = tmp_path / "round.secret"
    _write_source(source)
    _write_zones(zones)
    _write_secret(secret)

    monkeypatch.setenv(
        "CYBERBREIN_DATABASE_URL",
        "postgresql+psycopg2:///database_that_does_not_exist",
    )
    exit_code = main([*_arguments(source, zones, secret), "--delete-source-on-success"])

    assert exit_code == 3
    assert source.exists()
    assert secret.exists()


def test_source_buffer_must_have_restricted_permissions(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    zones = tmp_path / "zones.geojson"
    secret = tmp_path / "round.secret"
    _write_source(source)
    source.chmod(0o644)
    _write_zones(zones)
    _write_secret(secret)

    assert main(_arguments(source, zones, secret)) == 2
    assert source.exists()
    assert secret.exists()


def test_cleanup_rejects_a_swapped_secret_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    secret_target = tmp_path / "target.secret"
    secret_link = tmp_path / "round.secret"
    source.touch()
    secret_target.write_text(SYNTHETIC_SECRET, encoding="utf-8")
    secret_link.symlink_to(secret_target)

    with pytest.raises(PipelineRuntimeError, match="cleanup_failed"):
        cleanup_runtime_inputs(source, secret_link)

    assert source.exists()
    assert secret_target.exists()


@pytest.mark.parametrize("missing", ("source", "secret"))
def test_discard_cleanup_tolerates_one_already_missing_input(
    missing: str,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite"
    secret = tmp_path / "round.secret"
    source.touch()
    _write_secret(secret)
    (source if missing == "source" else secret).unlink()

    cleanup_runtime_inputs(source, secret, missing_ok=True)

    assert not source.exists()
    assert not secret.exists()


def test_normal_cleanup_rejects_a_missing_required_input(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    secret = tmp_path / "round.secret"
    source.touch()

    with pytest.raises(PipelineRuntimeError, match="cleanup_failed"):
        cleanup_runtime_inputs(source, secret)

    assert source.exists()
