import logging
import os
import subprocess
from collections.abc import Mapping
from typing import Protocol


class _CommandResult(Protocol):
    returncode: int
    stdout: str


class CommandRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        text: bool,
        check: bool,
    ) -> _CommandResult: ...


class InterfaceError(RuntimeError):
    """A controlled interface lifecycle failure with a safe category."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class InterfaceManager:
    def __init__(
        self,
        interface: str,
        *,
        command_runner: CommandRunner = subprocess.run,
        environment: Mapping[str, str] = os.environ,
    ) -> None:
        if not interface.strip():
            raise ValueError("interface is required")
        self._interface = interface
        self._command_runner = command_runner
        self._environment = environment
        self._changed = False
        self._was_connected = False

    def prepare(self, *, auto_monitor: bool = True) -> None:
        """Ensure monitor mode, optionally taking temporary ownership of the interface."""
        interface_type = self._interface_type()
        if interface_type == "monitor":
            return
        if interface_type != "managed":
            raise InterfaceError("interface_mode_unsupported")
        if not auto_monitor:
            raise InterfaceError("interface_not_in_monitor_mode")
        if self._is_selected_default_route() or self._carries_current_ssh_session():
            raise InterfaceError("interface_in_use")

        self._was_connected = self._is_connected()
        self._changed = True
        try:
            if self._was_connected:
                self._run(
                    ["nmcli", "device", "disconnect", self._interface],
                    failure_category="interface_disconnect_failed",
                )
            self._run(
                ["nmcli", "device", "set", self._interface, "managed", "no"],
                failure_category="interface_unmanage_failed",
            )
            self._run(
                ["ip", "link", "set", self._interface, "down"],
                failure_category="interface_down_failed",
            )
            self._run(
                ["iw", "dev", self._interface, "set", "type", "monitor"],
                failure_category="interface_monitor_failed",
            )
            self._run(
                ["ip", "link", "set", self._interface, "up"],
                failure_category="interface_up_failed",
            )
            if self._interface_type() != "monitor":
                raise InterfaceError("interface_monitor_verification_failed")
        except Exception as error:
            self._restore_after_prepare_failure()
            if isinstance(error, InterfaceError):
                raise
            raise InterfaceError("interface_prepare_failed") from error

    def restore(self) -> None:
        """Restore only an interface that this manager changed."""
        if not self._changed:
            return

        failed = False
        commands = [
            ["ip", "link", "set", self._interface, "down"],
            ["iw", "dev", self._interface, "set", "type", "managed"],
            ["ip", "link", "set", self._interface, "up"],
            ["nmcli", "device", "set", self._interface, "managed", "yes"],
        ]
        for command in commands:
            try:
                self._run(command)
            except InterfaceError:
                failed = True

        if not failed and self._interface_type() != "managed":
            failed = True
        if failed:
            raise InterfaceError("interface_restore_failed")
        self._changed = False

        if self._was_connected:
            try:
                self._run(["nmcli", "device", "connect", self._interface])
            except InterfaceError:
                logging.warning("interface_reconnect_failed")

    def _restore_after_prepare_failure(self) -> None:
        try:
            self.restore()
        except InterfaceError:
            pass

    def _interface_type(self) -> str:
        result = self._run(["iw", "dev", self._interface, "info"])
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("type "):
                return stripped.removeprefix("type ").strip()
        raise InterfaceError("interface_type_unavailable")

    def _is_connected(self) -> bool:
        result = self._run(["nmcli", "-g", "GENERAL.STATE", "device", "show", self._interface])
        return result.stdout.strip().startswith("100")

    def _is_selected_default_route(self) -> bool:
        result = self._run(["ip", "route", "get", "1.1.1.1"])
        tokens = result.stdout.split()
        return any(
            token == "dev" and index + 1 < len(tokens) and tokens[index + 1] == self._interface
            for index, token in enumerate(tokens)
        )

    def _carries_current_ssh_session(self) -> bool:
        ssh_connection = self._environment.get("SSH_CONNECTION")
        if not ssh_connection:
            return False
        parts = ssh_connection.split()
        if len(parts) < 3:
            return True
        server_ip = parts[2]
        result = self._run(["ip", "-o", "addr", "show", "dev", self._interface])
        return f" {server_ip}/" in result.stdout

    def _run(
        self,
        command: list[str],
        *,
        failure_category: str = "interface_command_failed",
    ) -> _CommandResult:
        try:
            result = self._command_runner(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
        except OSError as error:
            raise InterfaceError("interface_command_unavailable") from error
        if result.returncode != 0:
            raise InterfaceError(failure_category)
        return result
