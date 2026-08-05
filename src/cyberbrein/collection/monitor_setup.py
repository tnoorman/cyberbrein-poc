import os
import re
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

INTERFACE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,32}")
UNIT_NAME = "cyberbrein-monitor@.service"
UNIT_TEMPLATE = """[Unit]
Description=Cyberbrein persistent monitor mode for %I
After=NetworkManager.service sys-subsystem-net-devices-%i.device
BindsTo=sys-subsystem-net-devices-%i.device

[Service]
Type=oneshot
ExecStart=/usr/sbin/ip link set dev %i down
ExecStart=/usr/sbin/iw dev %i set type monitor
ExecStart=/usr/sbin/ip link set dev %i up
RemainAfterExit=yes
ExecStop=/usr/sbin/ip link set dev %i down
ExecStop=/usr/sbin/iw dev %i set type managed
ExecStop=/usr/sbin/ip link set dev %i up

[Install]
WantedBy=multi-user.target
"""


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


class MonitorSetupError(RuntimeError):
    """A controlled persistent-monitor setup failure."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class MonitorProvisioner:
    def __init__(
        self,
        interface: str,
        management_interface: str,
        *,
        command_runner: CommandRunner = subprocess.run,
        environment: Mapping[str, str] = os.environ,
        filesystem_root: str | Path = "/",
    ) -> None:
        if INTERFACE_PATTERN.fullmatch(interface) is None:
            raise MonitorSetupError("invalid_interface_name")
        if INTERFACE_PATTERN.fullmatch(management_interface) is None:
            raise MonitorSetupError("invalid_management_interface")
        if interface == management_interface:
            raise MonitorSetupError("management_interface_protected")
        self._interface = interface
        self._management_interface = management_interface
        self._command_runner = command_runner
        self._environment = environment
        self._filesystem_root = Path(filesystem_root)

    @property
    def service_instance(self) -> str:
        return f"cyberbrein-monitor@{self._interface}.service"

    def setup(self) -> None:
        """Persistently dedicate one wireless interface to monitor mode."""
        self._verify_dedicated_interface()
        self._write_managed_file(self._unit_path, UNIT_TEMPLATE)
        self._write_managed_file(self._network_manager_path, self._network_manager_config)
        self._write_managed_file(self._udev_path, self._udev_rule)
        try:
            self._run(["nmcli", "device", "set", self._interface, "managed", "no"])
            self._run(["udevadm", "control", "--reload-rules"])
            self._run(["systemctl", "daemon-reload"])
            self._run(["systemctl", "enable", self.service_instance])
            self._run(["systemctl", "restart", self.service_instance])
            if self._interface_type() != "monitor":
                raise MonitorSetupError("monitor_setup_verification_failed")
        except Exception as error:
            self._rollback_failed_setup()
            if isinstance(error, MonitorSetupError):
                raise
            raise MonitorSetupError("monitor_setup_failed") from error

    def teardown(self) -> None:
        """Remove persistent setup and return the interface to managed mode."""
        self._run_optional(["systemctl", "disable", "--now", self.service_instance])
        self._network_manager_path.unlink(missing_ok=True)
        self._udev_path.unlink(missing_ok=True)
        self._run(["udevadm", "control", "--reload-rules"])
        self._run(["systemctl", "daemon-reload"])
        self._set_interface_type("managed")
        self._run(["nmcli", "device", "set", self._interface, "managed", "yes"])
        if self._interface_type() != "managed":
            raise MonitorSetupError("monitor_teardown_verification_failed")

    @property
    def _unit_path(self) -> Path:
        return self._rooted("etc/systemd/system") / UNIT_NAME

    @property
    def _network_manager_path(self) -> Path:
        return (
            self._rooted("etc/NetworkManager/conf.d")
            / f"90-cyberbrein-monitor-{self._interface}.conf"
        )

    @property
    def _udev_path(self) -> Path:
        return self._rooted("etc/udev/rules.d") / f"90-cyberbrein-monitor-{self._interface}.rules"

    @property
    def _network_manager_config(self) -> str:
        return f"[keyfile]\nunmanaged-devices=interface-name:{self._interface}\n"

    @property
    def _udev_rule(self) -> str:
        return (
            f'ACTION=="add", SUBSYSTEM=="net", KERNEL=="{self._interface}", '
            f'TAG+="systemd", ENV{{SYSTEMD_WANTS}}+="{self.service_instance}"\n'
        )

    def _rooted(self, relative_path: str) -> Path:
        return self._filesystem_root / relative_path

    def _verify_dedicated_interface(self) -> None:
        if self._interface_type() not in {"managed", "monitor"}:
            raise MonitorSetupError("interface_mode_unsupported")
        for family in ("-4", "-6"):
            result = self._run(["ip", family, "route", "show", "default", "dev", self._interface])
            if result.stdout.strip():
                raise MonitorSetupError("capture_interface_in_use")
        if self._carries_current_ssh_session():
            raise MonitorSetupError("capture_interface_in_use")

    def _carries_current_ssh_session(self) -> bool:
        ssh_connection = self._environment.get("SSH_CONNECTION")
        if not ssh_connection:
            return False
        parts = ssh_connection.split()
        if len(parts) < 3:
            return True
        result = self._run(["ip", "-o", "addr", "show", "dev", self._interface])
        return f" {parts[2]}/" in result.stdout

    def _interface_type(self) -> str:
        result = self._run(["iw", "dev", self._interface, "info"])
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("type "):
                return stripped.removeprefix("type ").strip()
        raise MonitorSetupError("interface_type_unavailable")

    def _set_interface_type(self, interface_type: str) -> None:
        self._run(["ip", "link", "set", "dev", self._interface, "down"])
        self._run(["iw", "dev", self._interface, "set", "type", interface_type])
        self._run(["ip", "link", "set", "dev", self._interface, "up"])

    def _rollback_failed_setup(self) -> None:
        self._run_optional(["systemctl", "disable", "--now", self.service_instance])
        self._network_manager_path.unlink(missing_ok=True)
        self._udev_path.unlink(missing_ok=True)
        self._run_optional(["udevadm", "control", "--reload-rules"])
        self._run_optional(["systemctl", "daemon-reload"])
        try:
            self._set_interface_type("managed")
        except MonitorSetupError:
            pass
        self._run_optional(["nmcli", "device", "set", self._interface, "managed", "yes"])

    def _write_managed_file(self, path: Path, contents: str) -> None:
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if path.is_symlink():
            raise MonitorSetupError("unsafe_system_configuration_path")
        temporary_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o644,
            )
            os.fchmod(descriptor, 0o644)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(path)
        except MonitorSetupError:
            raise
        except OSError as error:
            raise MonitorSetupError("system_configuration_write_failed") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)

        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != 0o644:
            raise MonitorSetupError("system_configuration_write_failed")

    def _run(self, command: list[str]) -> _CommandResult:
        try:
            result = self._command_runner(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
        except OSError as error:
            raise MonitorSetupError("monitor_setup_command_unavailable") from error
        if result.returncode != 0:
            raise MonitorSetupError("monitor_setup_command_failed")
        return result

    def _run_optional(self, command: list[str]) -> None:
        try:
            self._run(command)
        except MonitorSetupError:
            pass
