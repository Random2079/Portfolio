"""Quick check parse_lobby without OCR."""
from parse_lobby import OcrLine, parse_lobby


def test_lounge_12():
    lines = [
        OcrLine("Lounge", 10, 0, 1),
        OcrLine("• 12", 40, 0, 1),
        OcrLine("vladswaga", 70, 20, 1),
        OcrLine("дима билан", 100, 20, 1),
        OcrLine("Ищу работу (Python ...", 130, 20, 1),
        OcrLine("Куратор", 160, 20, 1),
        OcrLine("• 13", 200, 0, 1),
        OcrLine("someone", 230, 20, 1),
    ]
    snap = parse_lobby(
        lines,
        "Ищу работу (Python Dev)",
        aliases=["Ищу работу", "Ищу работу (Python"],
    )
    assert snap.lobby == "12", snap
    assert snap.me and "Ищу работу" in snap.me
    assert "vladswaga" in snap.others
    assert "someone" not in snap.others
    # short OCR crumb must NOT match
    bad = parse_lobby(
        [OcrLine("ИщУ", 10, 0, 1), OcrLine("coby", 40, 0, 1)],
        "Ищу работу (Python Dev)",
        ["Ищу работу"],
    )
    assert bad.me is None, bad
    print("ok", snap)


if __name__ == "__main__":
    test_lounge_12()
