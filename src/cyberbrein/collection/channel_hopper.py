import subprocess
from collections.abc import Sequence
from threading import Event
from typing import Protocol


class _CommandResult(Protocol):
    returncode: int


class CommandRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> _CommandResult: ...


class ChannelHopError(RuntimeError):
    """Raised when changing a Wi-Fi channel fails."""


class ChannelHopper:
    def __init__(
        self,
        interface: str,
        channels: Sequence[int],
        command_runner: CommandRunner = subprocess.run,
        dwell_seconds: float = 1.0,
    ) -> None:
        if not channels:
            raise ValueError("channels must not be empty")

        self._interface = interface
        self._channels = tuple(channels)
        self._command_runner = command_runner
        self._dwell_seconds = dwell_seconds

    def run(self, stop_event: Event) -> None:
        """Hop through configured channels until the stop event is set."""
        while not stop_event.is_set():
            for channel in self._channels:
                if stop_event.is_set():
                    return

                command = [
                    "iw",
                    "dev",
                    self._interface,
                    "set",
                    "channel",
                    str(channel),
                ]
                try:
                    result = self._command_runner(
                        command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                except OSError as error:
                    raise ChannelHopError("unable to execute iw") from error
                if result.returncode != 0:
                    raise ChannelHopError(f"iw exited with status {result.returncode}")

                if stop_event.wait(self._dwell_seconds):
                    return
