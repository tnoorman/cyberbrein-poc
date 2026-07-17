import subprocess
from threading import Event

import pytest

from cyberbrein.collection.channel_hopper import ChannelHopError, ChannelHopper

SYNTHETIC_INTERFACE = "synthetic-monitor0"


def test_channel_commands_are_run_in_order() -> None:
    stop_event = Event()
    commands: list[list[str]] = []

    def runner(
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert stdout == subprocess.DEVNULL
        assert stderr == subprocess.DEVNULL
        assert check is False
        commands.append(command)
        if len(commands) == 3:
            stop_event.set()
        return subprocess.CompletedProcess(command, returncode=0)

    hopper = ChannelHopper(
        SYNTHETIC_INTERFACE,
        [1, 6, 11],
        command_runner=runner,
        dwell_seconds=0,
    )

    hopper.run(stop_event)

    assert commands == [
        ["iw", "dev", SYNTHETIC_INTERFACE, "set", "channel", "1"],
        ["iw", "dev", SYNTHETIC_INTERFACE, "set", "channel", "6"],
        ["iw", "dev", SYNTHETIC_INTERFACE, "set", "channel", "11"],
    ]


def test_empty_channel_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="channels must not be empty"):
        ChannelHopper(SYNTHETIC_INTERFACE, [])


def test_stop_event_prevents_further_channel_commands() -> None:
    stop_event = Event()
    commands: list[list[str]] = []

    def runner(
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del stdout, stderr, check
        commands.append(command)
        stop_event.set()
        return subprocess.CompletedProcess(command, returncode=0)

    hopper = ChannelHopper(
        SYNTHETIC_INTERFACE,
        [1, 6],
        command_runner=runner,
        dwell_seconds=0,
    )

    hopper.run(stop_event)

    assert commands == [["iw", "dev", SYNTHETIC_INTERFACE, "set", "channel", "1"]]


def test_iw_failure_status_raises_controlled_error() -> None:
    def runner(
        command: list[str],
        *,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del stdout, stderr, check
        return subprocess.CompletedProcess(command, returncode=1)

    hopper = ChannelHopper(
        SYNTHETIC_INTERFACE,
        [1],
        command_runner=runner,
        dwell_seconds=0,
    )

    with pytest.raises(ChannelHopError, match="iw exited with status 1"):
        hopper.run(Event())
