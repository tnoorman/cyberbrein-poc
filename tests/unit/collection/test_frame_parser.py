from datetime import datetime, timezone

import pytest
from scapy.layers.dot11 import (
    Dot11,
    Dot11Beacon,
    Dot11Elt,
    Dot11EltRSN,
    Dot11ProbeReq,
    Dot11ProbeResp,
    RadioTap,
)
from scapy.packet import Packet

from cyberbrein.collection.frame_parser import parse_wifi_frame

SYNTHETIC_BSSID = "02:00:00:00:00:01"
BROADCAST_ADDRESS = "ff:ff:ff:ff:ff:ff"
OBSERVED_AT_UTC = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _radio_tap(frequency_mhz: int, rssi_dbm: int = -42) -> RadioTap:
    return RadioTap(
        present="Channel+dBm_AntSignal",
        ChannelFrequency=frequency_mhz,
        ChannelFlags=0,
        dBm_AntSignal=rssi_dbm,
    )


def _beacon_frame(
    *,
    frequency_mhz: int = 2412,
    channel: int = 1,
    ssid: bytes = b"SYNTHETIC-BEACON",
    bssid: str | None = SYNTHETIC_BSSID,
) -> Packet:
    return (
        _radio_tap(frequency_mhz)
        / Dot11(
            type=0,
            subtype=8,
            addr1=BROADCAST_ADDRESS,
            addr2=bssid,
            addr3=bssid,
        )
        / Dot11Beacon(cap="ESS")
        / Dot11Elt(ID=0, info=ssid)
        / Dot11Elt(ID=3, info=bytes([channel]))
    )


def _probe_response_frame() -> Packet:
    return (
        _radio_tap(5180, rssi_dbm=-55)
        / Dot11(
            type=0,
            subtype=5,
            addr1=BROADCAST_ADDRESS,
            addr2=SYNTHETIC_BSSID,
            addr3=SYNTHETIC_BSSID,
        )
        / Dot11ProbeResp(cap="ESS+privacy")
        / Dot11Elt(ID=0, info=b"SYNTHETIC-PROBE-RESPONSE")
        / Dot11Elt(ID=3, info=bytes([36]))
        / Dot11EltRSN()
    )


def test_parse_synthetic_beacon_frame() -> None:
    metadata = parse_wifi_frame(_beacon_frame(), OBSERVED_AT_UTC)

    assert metadata is not None
    assert metadata.observed_at_utc == OBSERVED_AT_UTC
    assert metadata.bssid == SYNTHETIC_BSSID
    assert metadata.ssid == "SYNTHETIC-BEACON"
    assert metadata.rssi_dbm == -42
    assert metadata.channel == 1
    assert metadata.frequency_mhz == 2412
    assert metadata.band == "2.4GHz"
    assert metadata.encryption == "OPN"
    assert metadata.frame_type == "BEACON"


def test_parse_synthetic_probe_response_frame() -> None:
    metadata = parse_wifi_frame(_probe_response_frame(), OBSERVED_AT_UTC)

    assert metadata is not None
    assert metadata.bssid == SYNTHETIC_BSSID
    assert metadata.ssid == "SYNTHETIC-PROBE-RESPONSE"
    assert metadata.rssi_dbm == -55
    assert metadata.channel == 36
    assert metadata.frequency_mhz == 5180
    assert metadata.band == "5GHz"
    assert metadata.encryption == "WPA2/802.1X"
    assert metadata.frame_type == "PROBE_RESPONSE"


def test_unsupported_frame_type_returns_none() -> None:
    packet = (
        _radio_tap(2412)
        / Dot11(type=0, subtype=4, addr1=BROADCAST_ADDRESS, addr2=SYNTHETIC_BSSID)
        / Dot11ProbeReq()
        / Dot11Elt(ID=0, info=b"SYNTHETIC-PROBE-REQUEST")
    )

    assert parse_wifi_frame(packet, OBSERVED_AT_UTC) is None


def test_frame_without_bssid_returns_none() -> None:
    assert parse_wifi_frame(_beacon_frame(bssid=None), OBSERVED_AT_UTC) is None


def test_non_utf8_ssid_uses_replacement_characters() -> None:
    metadata = parse_wifi_frame(_beacon_frame(ssid=b"\xff\xfe"), OBSERVED_AT_UTC)

    assert metadata is not None
    assert metadata.ssid == "\ufffd\ufffd"


@pytest.mark.parametrize(
    ("frequency_mhz", "channel", "expected_band"),
    [
        (2412, 1, "2.4GHz"),
        (5180, 36, "5GHz"),
    ],
)
def test_band_is_derived_from_frequency(
    frequency_mhz: int,
    channel: int,
    expected_band: str,
) -> None:
    metadata = parse_wifi_frame(
        _beacon_frame(frequency_mhz=frequency_mhz, channel=channel),
        OBSERVED_AT_UTC,
    )

    assert metadata is not None
    assert metadata.band == expected_band


@pytest.mark.parametrize(
    ("packet", "expected_encryption"),
    [
        (_beacon_frame(), "OPN"),
        (_probe_response_frame(), "WPA2/802.1X"),
    ],
)
def test_encryption_is_recognized(packet: Packet, expected_encryption: str) -> None:
    metadata = parse_wifi_frame(packet, OBSERVED_AT_UTC)

    assert metadata is not None
    assert metadata.encryption == expected_encryption
