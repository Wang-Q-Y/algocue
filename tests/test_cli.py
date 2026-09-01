import pytest

from coach.cli import _parse_minutes


@pytest.mark.parametrize(
    "tokens,expected",
    [
        (["45"], 45),
        (["45m"], 45),
        (["1h"], 60),
        (["1", "hour"], 60),
        (["90m"], 90),
        (["1h30m"], 90),
        (["I", "have", "90", "minutes"], 90),
        (["I", "have", "an", "hour"], None),  # no digit to anchor on
    ],
)
def test_parse_minutes(tokens, expected):
    assert _parse_minutes(tokens) == expected


def test_parse_minutes_with_no_tokens():
    assert _parse_minutes([]) is None