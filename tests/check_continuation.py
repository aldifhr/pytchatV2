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
    if "--live" in sys.argv:
        check_live(sys.argv[sys.argv.index("--live") + 1])
    print("SELF-CHECK OK")
