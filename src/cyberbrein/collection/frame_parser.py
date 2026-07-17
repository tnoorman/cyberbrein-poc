from collections.abc import Iterator
from datetime import datetime
from typing import Any

from scapy.layers.dot11 import Dot11, Dot11Beacon, Dot11Elt, Dot11ProbeResp
from scapy.packet import Packet

from cyberbrein.collection.models import WifiFrameMetadata


def _iter_dot11_elements(packet: Packet) -> Iterator[Dot11Elt]:
    layer = packet.getlayer(Dot11Elt)
    while isinstance(layer, Dot11Elt):
        yield layer
        layer = layer.payload.getlayer(Dot11Elt)


def _get_ssid(packet: Packet) -> str | None:
    for element in _iter_dot11_elements(packet):
        if element.ID == 0:
            decoded = bytes(element.info).decode("utf-8", errors="replace").strip()
            return decoded or None
    return None


def _get_channel_from_elements(packet: Packet) -> int | None:
    for element in _iter_dot11_elements(packet):
        if element.ID == 3 and element.info:
            return int(element.info[0])
    return None


def _get_frequency(packet: Packet) -> int | None:
    frequency = getattr(packet, "ChannelFrequency", None)
    return frequency if isinstance(frequency, int) else None


def _channel_from_frequency(frequency: int | None) -> int | None:
    if frequency is None:
        return None
    if 2412 <= frequency <= 2472:
        return int((frequency - 2407) / 5)
    if frequency == 2484:
        return 14
    if 5000 <= frequency <= 5900:
        return int((frequency - 5000) / 5)
    if 5955 <= frequency <= 7115:
        return int((frequency - 5950) / 5)
    return None


def _get_band(channel: int, frequency: int | None) -> str | None:
    if frequency is not None:
        if 2400 <= frequency < 2500:
            return "2.4GHz"
        if 5000 <= frequency < 5900:
            return "5GHz"
        if 5900 <= frequency < 7200:
            return "6GHz"
    if 1 <= channel <= 14:
        return "2.4GHz"
    if 32 <= channel <= 177:
        return "5GHz"
    return None


def _get_network_stats(packet: Packet) -> dict[str, Any]:
    try:
        if packet.haslayer(Dot11Beacon):
            return dict(packet[Dot11Beacon].network_stats())
        if packet.haslayer(Dot11ProbeResp):
            return dict(packet[Dot11ProbeResp].network_stats())
    except Exception:
        return {}
    return {}


def _has_information_element(packet: Packet, element_id: int, prefix: bytes = b"") -> bool:
    for element in _iter_dot11_elements(packet):
        if element.ID == element_id and bytes(element.info).startswith(prefix):
            return True
    return False


def _get_encryption(packet: Packet) -> str:
    stats = _get_network_stats(packet)
    crypto = stats.get("crypto")
    if crypto:
        crypto_text = ",".join(sorted(str(item) for item in crypto))
        if crypto_text:
            return crypto_text

    capability = str(stats.get("capability", "")).lower()
    if "privacy" not in capability:
        return "OPEN"
    if _has_information_element(packet, 48):
        return "RSN_WPA2_OR_WPA3"
    if _has_information_element(packet, 221, b"\x00\x50\xf2\x01"):
        return "WPA"
    return "WEP_OR_UNKNOWN"


def _get_signal_dbm(packet: Packet) -> int | None:
    signal = getattr(packet, "dBm_AntSignal", None)
    return signal if isinstance(signal, int) else None


def parse_wifi_frame(packet: Packet, observed_at_utc: datetime) -> WifiFrameMetadata | None:
    """Extract allowed metadata from a passive beacon or probe-response frame."""
    if not packet.haslayer(Dot11):
        return None

    is_beacon = packet.haslayer(Dot11Beacon)
    is_probe_response = packet.haslayer(Dot11ProbeResp)
    if not is_beacon and not is_probe_response:
        return None

    dot11 = packet[Dot11]
    bssid = dot11.addr3 or dot11.addr2
    if not isinstance(bssid, str) or not bssid.strip():
        return None

    frequency = _get_frequency(packet)
    channel = _channel_from_frequency(frequency)
    if channel is None:
        channel = _get_channel_from_elements(packet)
    if channel is None:
        return None

    band = _get_band(channel, frequency)
    signal = _get_signal_dbm(packet)
    if band is None or signal is None:
        return None

    return WifiFrameMetadata(
        observed_at_utc=observed_at_utc,
        bssid=bssid.strip(),
        ssid=_get_ssid(packet),
        rssi_dbm=signal,
        channel=channel,
        frequency_mhz=frequency,
        band=band,
        encryption=_get_encryption(packet),
        frame_type="BEACON" if is_beacon else "PROBE_RESPONSE",
    )
