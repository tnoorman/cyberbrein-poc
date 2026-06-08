#!/usr/bin/env python3
import argparse
import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from scapy.all import Dot11, Dot11Beacon, Dot11Elt, Dot11ProbeResp, RadioTap, sniff


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_mac(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.lower().strip()


def hmac_hash(value: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return digest


def safe_decode(raw: bytes) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace").strip()


def iter_dot11_elements(packet):
    layer = packet.getlayer(Dot11Elt)
    while layer is not None:
        yield layer
        layer = layer.payload.getlayer(Dot11Elt)


def get_ssid(packet) -> str:
    for element in iter_dot11_elements(packet):
        if element.ID == 0:
            return safe_decode(bytes(element.info))
    return ""


def get_channel_from_elements(packet) -> Optional[int]:
    for element in iter_dot11_elements(packet):
        if element.ID == 3 and element.info:
            return int(element.info[0])
    return None


def get_frequency(packet) -> Optional[int]:
    freq = getattr(packet, "ChannelFrequency", None)
    if isinstance(freq, int):
        return freq
    return None


def channel_from_frequency(freq: Optional[int]) -> Optional[int]:
    if freq is None:
        return None

    if 2412 <= freq <= 2472:
        return int((freq - 2407) / 5)

    if freq == 2484:
        return 14

    if 5000 <= freq <= 5900:
        return int((freq - 5000) / 5)

    if 5955 <= freq <= 7115:
        return int((freq - 5950) / 5)

    return None


def band_from_channel_or_frequency(channel: Optional[int], freq: Optional[int]) -> Optional[str]:
    if freq is not None:
        if 2400 <= freq < 2500:
            return "2.4GHz"
        if 5000 <= freq < 5900:
            return "5GHz"
        if 5900 <= freq < 7200:
            return "6GHz"

    if channel is not None:
        if 1 <= channel <= 14:
            return "2.4GHz"
        if 32 <= channel <= 177:
            return "5GHz"

    return None


def has_vendor_wpa(packet) -> bool:
    for element in iter_dot11_elements(packet):
        if element.ID == 221:
            info = bytes(element.info)
            if info.startswith(b"\x00\x50\xf2\x01"):
                return True
    return False


def has_rsn(packet) -> bool:
    for element in iter_dot11_elements(packet):
        if element.ID == 48:
            return True
    return False


def get_capability_text(packet) -> str:
    if packet.haslayer(Dot11Beacon):
        return str(packet[Dot11Beacon].network_stats().get("capability", ""))
    if packet.haslayer(Dot11ProbeResp):
        return str(packet[Dot11ProbeResp].network_stats().get("capability", ""))
    return ""


def get_encryption(packet) -> str:
    stats = {}
    try:
        if packet.haslayer(Dot11Beacon):
            stats = packet[Dot11Beacon].network_stats()
        elif packet.haslayer(Dot11ProbeResp):
            stats = packet[Dot11ProbeResp].network_stats()
    except Exception:
        stats = {}

    crypto = stats.get("crypto")
    if crypto:
        crypto_text = ",".join(sorted(str(item) for item in crypto))
        if crypto_text:
            return crypto_text

    cap_text = get_capability_text(packet).lower()
    privacy_bit = "privacy" in cap_text

    if not privacy_bit:
        return "OPEN"

    if has_rsn(packet):
        return "RSN_WPA2_OR_WPA3"

    if has_vendor_wpa(packet):
        return "WPA"

    return "WEP_OR_UNKNOWN"


def get_signal_dbm(packet) -> Optional[int]:
    signal = getattr(packet, "dBm_AntSignal", None)
    if isinstance(signal, int):
        return signal
    return None


def create_database(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at_utc TEXT NOT NULL,
            interface TEXT NOT NULL,
            note TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS wifi_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_run_id INTEGER NOT NULL,
            observed_at_utc TEXT NOT NULL,
            frame_type TEXT NOT NULL,
            bssid_hash TEXT NOT NULL,
            ssid_hash TEXT,
            ssid TEXT,
            rssi_dbm INTEGER,
            channel INTEGER,
            frequency_mhz INTEGER,
            band TEXT,
            encryption TEXT,
            latitude REAL,
            longitude REAL,
            gps_accuracy_m REAL,
            FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id)
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_wifi_observations_run
        ON wifi_observations(scan_run_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_wifi_observations_bssid
        ON wifi_observations(bssid_hash)
    """)

    conn.commit()
    return conn


def insert_scan_run(conn: sqlite3.Connection, iface: str, note: Optional[str]) -> int:
    cursor = conn.execute(
        "INSERT INTO scan_runs(started_at_utc, interface, note) VALUES (?, ?, ?)",
        (utc_now(), iface, note)
    )
    conn.commit()
    return int(cursor.lastrowid)


def insert_observation(
    conn: sqlite3.Connection,
    scan_run_id: int,
    row: Tuple
) -> None:
    conn.execute("""
        INSERT INTO wifi_observations(
            scan_run_id,
            observed_at_utc,
            frame_type,
            bssid_hash,
            ssid_hash,
            ssid,
            rssi_dbm,
            channel,
            frequency_mhz,
            band,
            encryption,
            latitude,
            longitude,
            gps_accuracy_m
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (scan_run_id, *row))


def channel_hopper(iface: str, channels: list[int], stop_event: threading.Event, dwell_seconds: float) -> None:
    while not stop_event.is_set():
        for channel in channels:
            if stop_event.is_set():
                break

            subprocess.run(
                ["iw", "dev", iface, "set", "channel", str(channel)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
            time.sleep(dwell_seconds)


def parse_channels(value: str) -> list[int]:
    channels = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        channels.append(int(part))
    return channels


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minimal passive Wi-Fi collector for beacon and probe-response metadata."
    )
    parser.add_argument("--iface", required=True, help="Monitor mode interface, for example wlan1 or mon0.")
    parser.add_argument("--db", default="wifi_measurements.sqlite", help="SQLite database path.")
    parser.add_argument("--seconds", type=int, default=60, help="Measurement duration in seconds.")
    parser.add_argument("--channels", default="1,6,11", help="Comma-separated channels for hopping.")
    parser.add_argument("--dwell", type=float, default=1.0, help="Seconds per channel while hopping.")
    parser.add_argument("--lat", type=float, default=None, help="Optional fixed latitude for test runs.")
    parser.add_argument("--lon", type=float, default=None, help="Optional fixed longitude for test runs.")
    parser.add_argument("--gps-accuracy", type=float, default=None, help="Optional GPS accuracy in meters.")
    parser.add_argument("--store-ssid", action="store_true", help="Store readable SSID. Use only in approved tests.")
    parser.add_argument("--no-hop", action="store_true", help="Disable channel hopping.")
    parser.add_argument("--note", default=None, help="Optional note for this scan run.")
    args = parser.parse_args()

    secret = os.environ.get("WIFI_SCAN_SECRET")
    if not secret:
        secret = secrets.token_hex(32)
        print("No WIFI_SCAN_SECRET found. Using a temporary secret for this run.")
        print("BSSID hashes from this run cannot be compared with later runs.")

    conn = create_database(args.db)
    scan_run_id = insert_scan_run(conn, args.iface, args.note)

    channels = parse_channels(args.channels)
    stop_event = threading.Event()
    hopper_thread = None

    if not args.no_hop:
        hopper_thread = threading.Thread(
            target=channel_hopper,
            args=(args.iface, channels, stop_event, args.dwell),
            daemon=True
        )
        hopper_thread.start()

    counters = {
        "observations": 0,
        "beacons": 0,
        "probe_responses": 0,
        "skipped": 0
    }

    seen_commit_count = 0

    def handle_packet(packet) -> None:
        nonlocal seen_commit_count

        if not packet.haslayer(Dot11):
            return

        is_beacon = packet.haslayer(Dot11Beacon)
        is_probe_response = packet.haslayer(Dot11ProbeResp)

        if not is_beacon and not is_probe_response:
            return

        bssid = normalize_mac(packet[Dot11].addr3 or packet[Dot11].addr2)
        if not bssid:
            counters["skipped"] += 1
            return

        ssid = get_ssid(packet)
        ssid_hash = hmac_hash(ssid, secret) if ssid else None
        readable_ssid = ssid if args.store_ssid else None

        freq = get_frequency(packet)
        channel =  channel_from_frequency(freq) or get_channel_from_elements(packet)
        band = band_from_channel_or_frequency(channel, freq)
        rssi = get_signal_dbm(packet)
        encryption = get_encryption(packet)
        frame_type = "BEACON" if is_beacon else "PROBE_RESPONSE"

        bssid_hash = hmac_hash(bssid, secret)

        row = (
            utc_now(),
            frame_type,
            bssid_hash,
            ssid_hash,
            readable_ssid,
            rssi,
            channel,
            freq,
            band,
            encryption,
            args.lat,
            args.lon,
            args.gps_accuracy
        )

        insert_observation(conn, scan_run_id, row)

        counters["observations"] += 1
        if is_beacon:
            counters["beacons"] += 1
        if is_probe_response:
            counters["probe_responses"] += 1

        seen_commit_count += 1
        if seen_commit_count >= 100:
            conn.commit()
            seen_commit_count = 0

    print(f"Starting passive scan on {args.iface} for {args.seconds} seconds.")
    print(f"Writing to {args.db}. Scan run id: {scan_run_id}")

    try:
        sniff(
            iface=args.iface,
            prn=handle_packet,
            store=False,
            timeout=args.seconds
        )
    finally:
        stop_event.set()
        if hopper_thread:
            hopper_thread.join(timeout=2)

        conn.commit()

        summary = conn.execute("""
            SELECT
                COUNT(*) AS total_observations,
                COUNT(DISTINCT bssid_hash) AS distinct_networks
            FROM wifi_observations
            WHERE scan_run_id = ?
        """, (scan_run_id,)).fetchone()

        by_encryption = conn.execute("""
            SELECT encryption, COUNT(DISTINCT bssid_hash)
            FROM wifi_observations
            WHERE scan_run_id = ?
            GROUP BY encryption
            ORDER BY COUNT(DISTINCT bssid_hash) DESC
        """, (scan_run_id,)).fetchall()

        print("")
        print("Scan finished.")
        print(f"Observations: {summary[0]}")
        print(f"Distinct networks: {summary[1]}")
        print(f"Beacons: {counters['beacons']}")
        print(f"Probe responses: {counters['probe_responses']}")
        print(f"Skipped: {counters['skipped']}")
        print("")
        print("Distinct networks by encryption:")
        for encryption, count in by_encryption:
            print(f"- {encryption}: {count}")

        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
