"""Continuation tokens, taken from the pages YouTube serves.

The 2021 code *generated* these tokens by re-encoding a protobuf the site no
longer accepts: measured on a live stream, a generated token returned zero chat
items while the page's own token returned 75. So this module does not build
tokens. It asks the page for the one the site itself is using, which is the same
request the client makes and therefore the request that keeps working.

Two pages, because they answer different questions:

* ``/live_chat?is_popout=1&v=<id>`` is the chat-only page. It carries the live
  chat renderer and its continuation, plus the InnerTube key and client version
  the site is currently using. This is the page that works for a running stream.
* ``/watch?v=<id>`` is the fallback, for a stream whose popout page has no chat
  renderer yet (it is served before the chat pane mounts on some streams).

Nothing here is cached across videos: the key and version are per-page, and a
stale one is exactly the failure this module exists to remove.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from .. import config

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

#: The InnerTube key and client version sit in the page's bootstrap script.
_RE_KEY = re.compile(r'"INNERTUBE_API_KEY":"([^"]+)"')
_RE_VERSION = re.compile(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"')

#: Every continuation the page carries, in document order. There is more than
#: one — the popout page ships the live renderer's plus a couple of related
#: tokens — and only some of them return chat, so they are all collected and
#: tried rather than assuming the first is the right one.
_RE_CONTINUATION = re.compile(r'"continuation":"([^"]{40,})"')

#: The same field when the page escapes its JSON instead of emitting it raw.
_RE_CONTINUATION_ESCAPED = re.compile(r'\\x22continuation\\x22:\\x22([^\\"]{40,})')

#: The player's own seek token, which is what the replay endpoint wants.
_RE_PLAYER_SEEK = re.compile(r'"playerSeekContinuationData":\{"continuation":"([^"]+)"')


class ContinuationError(RuntimeError):
    """No usable token could be taken from the page."""


@dataclass(frozen=True)
class Session:
    """What one page load tells us about talking to YouTube right now."""

    video_id: str
    api_key: str
    client_version: str
    continuations: tuple[str, ...]
    is_replay: bool

    @property
    def client(self) -> dict[str, str]:
        return {"clientName": "WEB", "clientVersion": self.client_version}


def _page(client: httpx.Client, url: str) -> str:
    resp = client.get(url, headers={"user-agent": UA}, timeout=30)
    if resp.status_code != 200:
        raise ContinuationError(f"{url} answered {resp.status_code}")
    return resp.text


def _tokens(text: str) -> tuple[str, ...]:
    found = _RE_CONTINUATION.findall(text) + _RE_CONTINUATION_ESCAPED.findall(text)
    # De-duplicated but order-preserving: the candidates are tried in the order
    # the page lists them, and a set would make that order arbitrary.
    return tuple(dict.fromkeys(found))


def _from_text(video_id: str, text: str) -> Session | None:
    key = _RE_KEY.search(text)
    version = _RE_VERSION.search(text)
    tokens = _tokens(text)
    if not (key and version and tokens):
        return None
    # A finished live still serves a popout page; `/watch` is what marks the
    # difference in a way we can read without another request.
    is_replay = '"isLiveContent":true' in text and '"isLive":true' not in text
    return Session(
        video_id=video_id,
        api_key=key.group(1),
        client_version=version.group(1),
        continuations=tokens,
        is_replay=is_replay,
    )


def resolve(client: httpx.Client, video_id: str) -> Session:
    """Ask the pages for this video's chat tokens.

    The popout page first: it is the chat client's own page, so its token is the
    one the chat client uses. `/watch` second, for a stream whose chat pane has
    not been server-rendered yet.
    """
    errors: list[str] = []

    for url in (
        f"https://www.youtube.com/live_chat?is_popout=1&v={video_id}",
        f"https://www.youtube.com/watch?v={video_id}",
    ):
        try:
            text = _page(client, url)
        except (httpx.HTTPError, ContinuationError) as exc:
            errors.append(f"{url}: {exc}")
            continue
        session = _from_text(video_id, text)
        if session is not None:
            return session
        errors.append(f"{url}: no continuation in the page")

    raise ContinuationError(f"no chat continuation for {video_id}: {'; '.join(errors)}")


def player_seek(client: httpx.Client, session: Session) -> str | None:
    """The replay endpoint's own token, from the watch page.

    Replay does not accept the live renderer's continuation — measured: every
    candidate from the popout page returned an error against
    `get_live_chat_replay`. The seek token is a different field on a different
    page.
    """
    try:
        text = _page(client, f"https://www.youtube.com/watch?v={session.video_id}")
    except (httpx.HTTPError, ContinuationError):
        return None
    match = _RE_PLAYER_SEEK.search(text)
    return match.group(1) if match else None


def parse_initial_data(text: str) -> dict | None:
    """The page's bootstrap JSON, when it is emitted as a script var.

    Kept separate from token scraping because it is a different shape: the tokens
    are regular enough to find with a regex, and the chat renderer is not.
    """
    match = re.search(r"var ytInitialData = (\{.*?\});</script>", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


# --- async twins -----------------------------------------------------------
#
# The async reader cannot call the blocking versions — one `httpx.get` inside a
# coroutine parks the whole event loop — so these repeat the same two requests
# against an `AsyncClient`. Duplicated rather than shared through a callback
# because the parser is three regexes and a dataclass, and threading a callable
# through it would be longer than the copy.

async def _page_async(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url, headers={"user-agent": UA}, timeout=30)
    if resp.status_code != 200:
        raise ContinuationError(f"{url} answered {resp.status_code}")
    return resp.text


async def resolve_async(client: httpx.AsyncClient, video_id: str) -> Session:
    """`resolve`, for an async client."""
    errors: list[str] = []

    for url in (
        f"https://www.youtube.com/live_chat?is_popout=1&v={video_id}",
        f"https://www.youtube.com/watch?v={video_id}",
    ):
        try:
            text = await _page_async(client, url)
        except (httpx.HTTPError, ContinuationError) as exc:
            errors.append(f"{url}: {exc}")
            continue
        session = _from_text(video_id, text)
        if session is not None:
            return session
        errors.append(f"{url}: no continuation in the page")

    raise ContinuationError(f"no chat continuation for {video_id}: {'; '.join(errors)}")


async def player_seek_async(client: httpx.AsyncClient, session: Session) -> str | None:
    """`player_seek`, for an async client."""
    try:
        text = await _page_async(client, f"https://www.youtube.com/watch?v={session.video_id}")
    except (httpx.HTTPError, ContinuationError):
        return None
    match = _RE_PLAYER_SEEK.search(text)
    return match.group(1) if match else None


# --- picking the right candidate -------------------------------------------
#
# A page ships three tokens, and the first one is not the chat token: it is the
# placeholder the page mounts before the chat pane has data. Measured across four
# streams, actions per candidate were [0, 6, 6], [1, 86, 86], [1, 72, 76],
# [0, 77, 77] — index 0 was always the worst. A reader that always took index 0
# therefore opened with an empty poll, every time.
#
# So the candidates are tried in order and the first one that comes back with
# chat wins. That costs one extra request per reader start and removes a failure
# mode that looked exactly like a quiet stream.

def _action_count(payload: dict) -> int:
    contents = (payload.get("continuationContents") or {}).get("liveChatContinuation") or {}
    return len(contents.get("actions") or [])


def pick(client: httpx.Client, session: Session) -> tuple[str, dict] | None:
    """The candidate carrying the most chat, with the payload it returned.

    Not "the first candidate with any chat": the placeholder does return
    something — measured [1, 86, 86] on one stream — so a non-empty test picks it
    and the reader opens on a single stale system message. The most is the one
    that is actually the chat feed.

    Returns `None` when every candidate is empty, which is a quiet stream rather
    than a broken one; the caller keeps its fallback.
    """
    url = f"{config.LIVE_CHAT_URL}?key={session.api_key}&prettyPrint=false"
    best: tuple[str, dict] | None = None
    best_count = 0
    for token in session.continuations:
        try:
            payload = client.post(
                url, json={"context": {"client": session.client}, "continuation": token}
            ).json()
        except (httpx.HTTPError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        count = _action_count(payload)
        if count > best_count:
            best, best_count = (token, payload), count
    return best


async def pick_async(client: httpx.AsyncClient, session: Session) -> tuple[str, dict] | None:
    """`pick`, for an async client."""
    url = f"{config.LIVE_CHAT_URL}?key={session.api_key}&prettyPrint=false"
    best: tuple[str, dict] | None = None
    best_count = 0
    for token in session.continuations:
        try:
            payload = (await client.post(
                url, json={"context": {"client": session.client}, "continuation": token}
            )).json()
        except (httpx.HTTPError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        count = _action_count(payload)
        if count > best_count:
            best, best_count = (token, payload), count
    return best
