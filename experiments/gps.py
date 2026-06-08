#!/usr/bin/env python3
import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class GpsFix:
    timestamp_utc: str
    latitude: float
    longitude: float
    mode: int
    speed_mps: float | None
    track_deg: float | None
    horizontal_accuracy_m: float | None


class GpsdClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 2947, timeout_seconds: int = 5) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def read_fix(self, max_wait_seconds: int = 30) -> GpsFix:
        deadline = time.time() + max_wait_seconds

        with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds) as sock:
            sock.settimeout(self.timeout_seconds)

            watch_command = '?WATCH={"enable":true,"json":true}\n'
            sock.sendall(watch_command.encode("ascii"))

            buffer = ""

            while time.time() < deadline:
                chunk = sock.recv(4096).decode("utf-8", errors="replace")
                if not chunk:
                    continue

                buffer += chunk

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if message.get("class") != "TPV":
                        continue

                    mode = int(message.get("mode", 0))

                    # mode 2 = 2D fix, mode 3 = 3D fix
                    if mode < 2:
                        continue

                    lat = message.get("lat")
                    lon = message.get("lon")

                    if lat is None or lon is None:
                        continue

                    return GpsFix(
                        timestamp_utc=datetime.now(timezone.utc).isoformat(),
                        latitude=float(lat),
                        longitude=float(lon),
                        mode=mode,
                        speed_mps=message.get("speed"),
                        track_deg=message.get("track"),
                        horizontal_accuracy_m=message.get("eph"),
                    )

        raise TimeoutError("Geen geldige GPS-fix ontvangen binnen de ingestelde wachttijd.")


def main() -> int:
    client = GpsdClient()

    print("Wachten op GPS-fix via gpsd...")

    try:
        fix = client.read_fix(max_wait_seconds=60)
    except TimeoutError as error:
        print(f"Fout: {error}")
        return 1

    print("GPS-fix ontvangen:")
    print(f"- timestamp_utc: {fix.timestamp_utc}")
    print(f"- latitude: {fix.latitude}")
    print(f"- longitude: {fix.longitude}")
    print(f"- mode: {fix.mode}")
    print(f"- speed_mps: {fix.speed_mps}")
    print(f"- track_deg: {fix.track_deg}")
    print(f"- horizontal_accuracy_m: {fix.horizontal_accuracy_m}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
