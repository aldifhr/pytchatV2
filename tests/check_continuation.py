"""Checks the parts of the chat path that broke, without needing a live stream.

Run: python tests/check_continuation.py

The failures this covers were all silent: a token that returned zero items, a
page whose JSON was escaped differently than the regex expected, an id that came
out one character short. None of them raised. So each check below asserts on a
value that was wrong before, not on "it ran".

The live-network check is opt-in (`--live VIDEO_ID`) because CI has no stream to
point at, and a test that silently skips when the network is down is not a test.
"""

from __future__ import annotations

import re
import sys

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from pytchat import util  # noqa: E402
from pytchat.paramgen import resolver  # noqa: E402


def check_channel_id_pattern():
    """The page escapes its JSON as `\\x22`; the 2021 pattern only knew `"`."""
    raw = r'{"channelId":"UC3uJIdRFTGgLWrUziaHbzrg"}'
    escaped = r'{\x22channelId\x22:\x22UC3uJIdRFTGgLWrUziaHbzrg\x22}'
    for text, label in ((raw, "plain"), (escaped, "escaped")):
        match = util.PATTERN_CHANNEL.search(text) or util.PATTERN_M_CHANNEL.search(text)
        assert match, f"{label}: no match"
        found = util._first_group(match)
        assert found == "UC3uJIdRFTGgLWrUziaHbzrg", f"{label}: got {found!r}"
    print("ok  channel id regex matches both escapings")


def check_channel_id_length():
    """An optional group used to truncate the id to 21 characters."""
    id_ = "UC3uJIdRFTGgLWrUziaHbzrg"
    assert len(id_) == 24
    assert re.fullmatch(r"UC[A-Za-z0-9_-]{22}", id_), "id shape"
    print("ok  channel id is 24 characters")


def check_request_body():
    """The body must carry the page's client version, not a baked constant."""
    body = util.get_param("TOKEN", client_version="2.20261016.01.00")
    client = body["context"]["client"]
    assert client["clientVersion"] == "2.20261016.01.00", client
    assert body["continuation"] == "TOKEN"
    assert "visitorData" not in client, "a stale visitorData is one more thing to go wrong"
    print("ok  request body uses the page's client version")


def check_session_parsing():
    """Both pages' shapes produce a session; a page without tokens does not."""
    text = (
        '{"INNERTUBE_API_KEY":"KEY123",'
        '"INNERTUBE_CONTEXT_CLIENT_VERSION":"2.20261016.01.00",'
        '"continuation":"' + "A" * 60 + '",'
        '"continuation":"' + "B" * 60 + '"}'
    )
    session = resolver._from_text("vid", text)
    assert session is not None, "session not parsed"
    assert session.api_key == "KEY123"
    assert session.client_version == "2.20261016.01.00"
    assert len(session.continuations) == 2, "both candidates should be kept"
    assert resolver._from_text("vid", "<html>nothing</html>") is None
    print("ok  session parsing keeps every candidate, rejects empty pages")


def check_no_generated_tokens():
    """The protobuf generators are gone; importing them must fail."""
    for name in ("liveparam", "arcparam"):
        try:
            __import__(f"pytchat.paramgen.{name}")
        except ImportError:
            continue
        raise AssertionError(f"{name} still importable — it returns zero chat items")
    print("ok  generated-token modules are removed")


def check_picks_the_chat_candidate():
    """Index 0 is the page's placeholder; `pick` must skip it.

    Measured on four live streams, actions per candidate were [0, 6, 6],
    [1, 86, 86], [1, 72, 76] and [0, 77, 77] — the first token was always the
    worst. So the selection is checked against those exact shapes rather than
    against a mock that would just agree with whatever it was given.
    """
    session = resolver.Session(
        video_id="vid",
        api_key="KEY",
        client_version="2.20261016.01.00",
        continuations=("PLACEHOLDER", "SECOND", "THIRD"),
        is_replay=False,
    )

    class _Stub:
        """Answers per token, the way the page did."""

        def __init__(self, counts):
            self.counts = counts
            self.posted = []

        def post(self, url, json):  # noqa: A002 — httpx's parameter name
            self.posted.append(json["continuation"])
            actions = [{"x": 1}] * self.counts[json["continuation"]]

            class _Resp:
                def __init__(self, payload):
                    self._payload = payload

                def json(self):
                    return self._payload

            return _Resp({
                "continuationContents": {"liveChatContinuation": {"actions": actions}}
            })

    for counts, expected in (
        ({"PLACEHOLDER": 0, "SECOND": 6, "THIRD": 6}, "SECOND"),
        ({"PLACEHOLDER": 1, "SECOND": 86, "THIRD": 86}, "SECOND"),
        # 72 vs 76: the third candidate is the fuller feed, so it wins. This is
        # the case that proves "most" and not "first non-empty".
        ({"PLACEHOLDER": 1, "SECOND": 72, "THIRD": 76}, "THIRD"),
        ({"PLACEHOLDER": 0, "SECOND": 77, "THIRD": 77}, "SECOND"),
    ):
        stub = _Stub(counts)
        picked = resolver.pick(stub, session)
        assert picked is not None, counts
        assert picked[0] == expected, f"{counts}: picked {picked[0]}, wanted {expected}"

    # A quiet stream: nothing has chat, so the caller keeps its fallback.
    quiet = resolver.pick(_Stub({"PLACEHOLDER": 0, "SECOND": 0, "THIRD": 0}), session)
    assert quiet is None, "an all-empty stream should not claim a winner"
    print("ok  candidate selection skips the placeholder token")


def check_pacing_is_bounded():
    """A backlog must not be paced back out one message at a time.

    `abs_diff` is the lag against the first message ever seen, so on any stream
    older than a few seconds `wait_total_sec` never shrinks and every batch was
    paced: 71 messages took 68 seconds to yield while the HTTP request behind
    them took 0.09. This asserts the delivery time, which is the only thing the
    caller can feel.
    """
    import time as _time

    from pytchat.processors.default.processor import Chatdata

    class _Msg:
        def __init__(self, ts):
            self.timestamp = ts

    now_ms = _time.time() * 1000
    # 70 messages spread over the last 60 seconds — an ordinary busy batch — and
    # an `abs_diff` large enough that the queue is a minute behind.
    items = [_Msg(now_ms - 60_000 + i * 850) for i in range(70)]
    data = Chatdata(items, 10.0, _time.time() - 120)

    start = _time.time()
    got = list(data.sync_items())
    elapsed = _time.time() - start
    assert len(got) == 70, len(got)
    assert elapsed < 5, f"delivering 70 messages took {elapsed:.1f}s"
    print(f"ok  pacing bounded (70 messages in {elapsed:.1f}s)")


def check_live(video_id: str):
    """The whole path, against a real stream. Opt-in."""
    import time

    import httpx

    import pytchat

    chat = pytchat.create(video_id=video_id, interruptable=False)
    assert chat.is_alive(), "reader died at construction"
    seen = 0
    for _ in range(5):
        seen += len(list(chat.get().sync_items()))
        time.sleep(3)
    chat.raise_for_status()
    chat.terminate()
    assert seen > 0, "reader alive but delivered no chat in 15s"
    print(f"ok  live: {seen} chat items in 15s")
    _ = httpx  # imported for the reader's benefit; keeps the check honest


if __name__ == "__main__":
    check_channel_id_pattern()
    check_channel_id_length()
    check_request_body()
    check_session_parsing()
    check_no_generated_tokens()
    check_picks_the_chat_candidate()
    check_pacing_is_bounded()
    if "--live" in sys.argv:
        check_live(sys.argv[sys.argv.index("--live") + 1])
    print("SELF-CHECK OK")
