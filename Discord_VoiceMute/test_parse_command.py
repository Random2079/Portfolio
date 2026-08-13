"""Tests for command parser."""
from parse_command import format_command, parse_command


def test_commands():
    assert format_command(parse_command("замуть 3")) == "MUTE slot=3"
    assert format_command(parse_command("замуть три слота")) == "MUTE slot=3"
    assert format_command(parse_command("размуть 2")) == "UNMUTE slot=2"
    assert format_command(parse_command("привет")) == "UNKNOWN"
    # strip stream tag in lobby names — separate module, smoke import
    from parse_lobby import OcrLine, parse_lobby

    snap = parse_lobby(
        [
            OcrLine("• 16", 10, 0, 1),
            OcrLine("husfee B ЭФИРЕ", 40, 0, 1),
            OcrLine("Ищу работу (Python", 70, 0, 1),
        ],
        "Ищу работу (Python Dev)",
        ["Ищу работу"],
    )
    assert snap.lobby == "16"
    assert snap.others == ["husfee"]
    print("ok commands + stream tag")


if __name__ == "__main__":
    test_commands()
