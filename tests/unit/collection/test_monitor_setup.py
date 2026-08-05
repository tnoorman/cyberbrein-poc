import subprocess
from pathlib import Path

import pytest

from cyberbrein.collection.monitor_setup import (
    UNIT_NAME,
    MonitorProvisioner,
    MonitorSetupError,
)

INTERFACE = "wlan1"


class FakeRunner:
    def __init__(
        self,
        *,
        route_family: str | None = None,
        addresses: str = "",
        failing_command: list[str] | None = None,
        interface_type: str = "managed",
    ) -> None:
        self.interface_type = interface_type
        self.managed = True
        self.route_family = route_family
        self.addresses = addresses
        self.failing_command = failing_command
        self.commands: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert stdout == subprocess.PIPE
        assert stderr == subprocess.DEVNULL
        assert text is True
        assert check is False
        self.commands.append(command)
        if command == self.failing_command:
            return subprocess.CompletedProcess(command, 1, "", "")
        output = self._handle(command)
        return subprocess.CompletedProcess(command, 0, output, "")

    def _handle(self, command: list[str]) -> str:
        if command == ["iw", "dev", INTERFACE, "info"]:
            return f"Interface {INTERFACE}\n\ttype {self.interface_type}\n"
        if command[:4] == ["ip", "-4", "route", "show"]:
            return f"default dev {INTERFACE}\n" if self.route_family == "-4" else ""
        if command[:4] == ["ip", "-6", "route", "show"]:
            return f"default dev {INTERFACE}\n" if self.route_family == "-6" else ""
        if command == ["ip", "-o", "addr", "show", "dev", INTERFACE]:
            return self.addresses
        if command == ["nmcli", "device", "set", INTERFACE, "managed", "no"]:
            self.managed = False
        elif command == ["nmcli", "device", "set", INTERFACE, "managed", "yes"]:
            self.managed = True
        elif command == [
            "systemctl",
            "restart",
            f"cyberbrein-monitor@{INTERFACE}.service",
        ]:
            self.interface_type = "monitor"
        elif command == [
            "systemctl",
            "disable",
            "--now",
            f"cyberbrein-monitor@{INTERFACE}.service",
        ]:
            self.interface_type = "managed"
        elif command == ["iw", "dev", INTERFACE, "set", "type", "managed"]:
            self.interface_type = "managed"
        return ""


def _provisioner(tmp_path: Path, runner: FakeRunner, environment: dict[str, str] | None = None):
    return MonitorProvisioner(
        INTERFACE,
        "wlan0",
        command_runner=runner,
        environment=environment or {},
        filesystem_root=tmp_path,
    )


def test_setup_writes_configuration_and_enables_monitor_service(tmp_path: Path) -> None:
    runner = FakeRunner()
    provisioner = _provisioner(tmp_path, runner)

    provisioner.setup()

    network_manager = tmp_path / "etc/NetworkManager/conf.d/90-cyberbrein-monitor-wlan1.conf"
    unit = tmp_path / "etc/systemd/system" / UNIT_NAME
    udev_rule = tmp_path / "etc/udev/rules.d/90-cyberbrein-monitor-wlan1.rules"
    assert network_manager.read_text() == "[keyfile]\nunmanaged-devices=interface-name:wlan1\n"
    assert "ExecStart=/usr/sbin/iw dev %i set type monitor" in unit.read_text()
    assert 'SYSTEMD_WANTS}+="cyberbrein-monitor@wlan1.service"' in udev_rule.read_text()
    assert network_manager.stat().st_mode & 0o777 == 0o644
    assert runner.interface_type == "monitor"
    assert runner.managed is False


def test_setup_is_idempotent(tmp_path: Path) -> None:
    runner = FakeRunner()
    provisioner = _provisioner(tmp_path, runner)

    provisioner.setup()
    provisioner.setup()

    assert runner.interface_type == "monitor"


def test_teardown_removes_configuration_and_restores_managed_mode(tmp_path: Path) -> None:
    runner = FakeRunner()
    provisioner = _provisioner(tmp_path, runner)
    provisioner.setup()

    provisioner.teardown()

    assert not (tmp_path / "etc/NetworkManager/conf.d/90-cyberbrein-monitor-wlan1.conf").exists()
    assert not (tmp_path / "etc/udev/rules.d/90-cyberbrein-monitor-wlan1.rules").exists()
    assert runner.interface_type == "managed"
    assert runner.managed is True


def test_management_interface_is_always_protected() -> None:
    with pytest.raises(MonitorSetupError, match="management_interface_protected"):
        MonitorProvisioner("wlan0", "wlan0")


@pytest.mark.parametrize("family", ["-4", "-6"])
def test_default_route_interface_is_rejected(tmp_path: Path, family: str) -> None:
    provisioner = _provisioner(tmp_path, FakeRunner(route_family=family))

    with pytest.raises(MonitorSetupError, match="capture_interface_in_use"):
        provisioner.setup()


def test_current_ssh_interface_is_rejected(tmp_path: Path) -> None:
    runner = FakeRunner(
        addresses="4: wlan1 inet 192.0.2.20/24 scope global wlan1\n",
    )
    provisioner = _provisioner(
        tmp_path,
        runner,
        {"SSH_CONNECTION": "198.51.100.10 50000 192.0.2.20 22"},
    )

    with pytest.raises(MonitorSetupError, match="capture_interface_in_use"):
        provisioner.setup()


def test_non_capture_wireless_mode_is_rejected(tmp_path: Path) -> None:
    provisioner = _provisioner(tmp_path, FakeRunner(interface_type="AP"))

    with pytest.raises(MonitorSetupError, match="interface_mode_unsupported"):
        provisioner.setup()


def test_failed_setup_rolls_back_interface_and_specific_config(tmp_path: Path) -> None:
    restart = [
        "systemctl",
        "restart",
        f"cyberbrein-monitor@{INTERFACE}.service",
    ]
    runner = FakeRunner(failing_command=restart)
    provisioner = _provisioner(tmp_path, runner)

    with pytest.raises(MonitorSetupError, match="monitor_setup_command_failed"):
        provisioner.setup()

    assert not (tmp_path / "etc/NetworkManager/conf.d/90-cyberbrein-monitor-wlan1.conf").exists()
    assert not (tmp_path / "etc/udev/rules.d/90-cyberbrein-monitor-wlan1.rules").exists()
    assert runner.interface_type == "managed"
    assert runner.managed is True
