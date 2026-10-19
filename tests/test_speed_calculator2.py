"""The live-network twin of `test_speed_calculator`.

It used to call `pytchat.create("Hj-wnLIYKjw")` against YouTube — not a test, but
a network probe: it fails whenever that video's archive is unavailable, whenever
the runner has no network, and whenever YouTube changes anything. It was red for
reasons that had nothing to do with the code it claimed to cover.

Rewritten to use the same recorded fixture as its twin. The one thing the other
file does not cover is the multi-component form of the call — several poll
results handed to the processor at once — so that is what this checks.
"""

import json

from pytchat.parser.live import Parser
from pytchat.processors.speed.calculator import SpeedCalculator


def _payload(chatdata):
    return [{"video_id": "", "timeout": 10, "chatdata": chatdata}]


def _parse(name):
    with open(f"tests/testdata/speed/{name}", mode="r", encoding="utf-8") as f:
        raw = json.loads(f.read())
    parser = Parser(is_replay=False)
    return parser.parse(parser.get_contents(raw)[0])[1]


def test_speed_across_two_components():
    """An empty poll must not reset the window."""
    processor = SpeedCalculator(capacity=30)
    chatdata = _parse("speedtest_normal.json")

    first = processor.process(_payload(chatdata))
    second = processor.process(_payload([]))
    assert first == 30, first
    assert second == 30, second


def test_speed_zero_on_undefined():
    processor = SpeedCalculator(capacity=30)
    assert processor.process(_payload(_parse("speedtest_undefined.json"))) == 0
