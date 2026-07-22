import subprocess

import pytest

from cyberbrein.collection.interface_manager import InterfaceError, InterfaceManager

SYNTHETIC_INTERFACE = "synthetic-monitor0"


class FakeRunner:
    def __init__(
        self,
        *,
        interface_type: str = "managed",
        connected: bool = True,
        route_interface: str = "synthetic-ethernet0",
        addresses: str = "",
        failing_command: list[str] | None = None,
    ) -> None:
        self.interface_type = interface_type
        self.connected = connected
        self.managed_by_network_manager = True
        self.route_interface = route_interface
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
            return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr="")
        output = self._handle(command)
        return subprocess.CompletedProcess(command, returncode=0, stdout=output, stderr="")

    def _handle(self, command: list[str]) -> str:
        if command == ["iw", "dev", SYNTHETIC_INTERFACE, "info"]:
            return f"Interface {SYNTHETIC_INTERFACE}\n\ttype {self.interface_type}\n"
        if command == ["ip", "route", "get", "1.1.1.1"]:
            return f"1.1.1.1 via 192.0.2.1 dev {self.route_interface} src 192.0.2.2\n"
        if command == ["ip", "-o", "addr", "show", "dev", SYNTHETIC_INTERFACE]:
            return self.addresses
        if command == [
            "nmcli",
            "-g",
            "GENERAL.STATE",
            "device",
            "show",
            SYNTHETIC_INTERFACE,
        ]:
            return "100 (connected)\n" if self.connected else "30 (disconnected)\n"
        if command == ["nmcli", "device", "disconnect", SYNTHETIC_INTERFACE]:
            self.connected = False
        elif command == ["nmcli", "device", "connect", SYNTHETIC_INTERFACE]:
            self.connected = True
        elif command == [
            "nmcli",
            "device",
            "set",
            SYNTHETIC_INTERFACE,
            "managed",
            "no",
        ]:
            self.managed_by_network_manager = False
        elif command == [
            "nmcli",
            "device",
            "set",
            SYNTHETIC_INTERFACE,
            "managed",
            "yes",
        ]:
            self.managed_by_network_manager = True
        elif command == ["iw", "dev", SYNTHETIC_INTERFACE, "set", "type", "monitor"]:
            self.interface_type = "monitor"
        elif command == ["iw", "dev", SYNTHETIC_INTERFACE, "set", "type", "managed"]:
            self.interface_type = "managed"
        return ""


def test_managed_interface_is_prepared_and_restored() -> None:
    runner = FakeRunner()
    manager = InterfaceManager(SYNTHETIC_INTERFACE, command_runner=runner, environment={})

    manager.prepare()

    assert runner.interface_type == "monitor"
    assert runner.connected is False
    assert runner.managed_by_network_manager is False

    manager.restore()

    assert runner.interface_type == "managed"
    assert runner.connected is True
    assert runner.managed_by_network_manager is True


def test_existing_monitor_mode_is_left_unchanged() -> None:
    runner = FakeRunner(interface_type="monitor", connected=False)
    manager = InterfaceManager(SYNTHETIC_INTERFACE, command_runner=runner, environment={})

    manager.prepare()
    manager.restore()

    assert runner.commands == [["iw", "dev", SYNTHETIC_INTERFACE, "info"]]
    assert runner.interface_type == "monitor"


def test_managed_interface_fails_fast_when_auto_monitor_is_disabled() -> None:
    runner = FakeRunner()
    manager = InterfaceManager(SYNTHETIC_INTERFACE, command_runner=runner, environment={})

    with pytest.raises(InterfaceError, match="interface_not_in_monitor_mode"):
        manager.prepare(auto_monitor=False)

    assert runner.interface_type == "managed"


def test_selected_default_route_is_never_modified() -> None:
    runner = FakeRunner(route_interface=SYNTHETIC_INTERFACE)
    manager = InterfaceManager(SYNTHETIC_INTERFACE, command_runner=runner, environment={})

    with pytest.raises(InterfaceError, match="interface_in_use"):
        manager.prepare()

    assert runner.interface_type == "managed"
    assert ["nmcli", "device", "disconnect", SYNTHETIC_INTERFACE] not in runner.commands


def test_interface_carrying_current_ssh_session_is_never_modified() -> None:
    runner = FakeRunner(
        addresses=(
            f"4: {SYNTHETIC_INTERFACE} inet 192.0.2.20/24 "
            "brd 192.0.2.255 scope global synthetic-monitor0\n"
        )
    )
    manager = InterfaceManager(
        SYNTHETIC_INTERFACE,
        command_runner=runner,
        environment={"SSH_CONNECTION": "198.51.100.10 50000 192.0.2.20 22"},
    )

    with pytest.raises(InterfaceError, match="interface_in_use"):
        manager.prepare()

    assert runner.interface_type == "managed"


def test_prepare_failure_attempts_to_restore_original_state() -> None:
    failing_command = ["iw", "dev", SYNTHETIC_INTERFACE, "set", "type", "monitor"]
    runner = FakeRunner(failing_command=failing_command)
    manager = InterfaceManager(SYNTHETIC_INTERFACE, command_runner=runner, environment={})

    with pytest.raises(InterfaceError, match="interface_command_failed"):
        manager.prepare()

    assert runner.interface_type == "managed"
    assert runner.connected is True
    assert runner.managed_by_network_manager is True
