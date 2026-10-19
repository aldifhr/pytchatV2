import json
import signal
import time
import traceback

import httpx

from ..parser.live import Parser
from .. import config
from .. import exceptions
from ..paramgen import resolver
from ..processors.default.processor import DefaultProcessor
from ..processors.combinator import Combinator
from .. import util

headers = config.headers
MAX_RETRY = 10


class PytchatCore:
    '''

    Parameter
    ---------
    video_id : str

    seektime : int
        start position of fetching chat (seconds).
        This option is valid for archived chat only.
        If negative value, chat data posted before the start of the broadcast
        will be retrieved as well.

    processor : ChatProcessor
        Defaults to a fresh `DefaultProcessor` per instance. It used to be a
        default argument — one object shared by every `PytchatCore` ever created,
        so a finalized processor from one stream was handed to the next.

    client : httpx.Client
        The client for connecting youtube.
        You can specify any customized httpx client (e.g. coolies, user agent).

    interruptable : bool
        Allows keyboard interrupts.
        Set this parameter to False if your own multi-threading program causes
        the problem.

    force_replay : bool
        force to fetch archived chat data, even if specified video is live.

    topchat_only : bool
        If True, get only top chat. Ignored since the page supplies the token:
        the site's own chat renderer decides which chat it renders.

    hold_exception : bool [default:True]
        If True, when exceptions occur, the exception is held internally,
        and can be raised by raise_for_status().

    replay_continuation : str
        If this parameter is not None, the processor will attempt to get chat data from continuation.
        This parameter is only allowed in archived mode.

    Attributes
    ---------
    _is_alive : bool
        Flag to stop getting chat.
    '''

    def __init__(self, video_id,
                 seektime=-1,
                 processor=None,
                 client=None,
                 interruptable=True,
                 force_replay=False,
                 topchat_only=False,
                 hold_exception=True,
                 logger=None,
                 replay_continuation=None
                 ):
        self._client = client if client is not None else httpx.Client(http2=True)
        self._owns_client = client is None
        self._video_id = util.extract_video_id(video_id)
        self.seektime = seektime
        if isinstance(processor, tuple):
            self.processor = Combinator(processor)
        elif processor is None:
            self.processor = DefaultProcessor()
        else:
            self.processor = processor
        self._is_alive = True
        self._is_replay = force_replay or (replay_continuation is not None)
        self._hold_exception = hold_exception
        self._exception_holder = None
        self._parser = Parser(
            is_replay=self._is_replay,
            exception_holder=self._exception_holder
        )
        self._first_fetch = replay_continuation is None
        self._topchat_only = topchat_only
        self._dat = ''
        self._last_offset_ms = 0
        self._logger = logger or config.logger(__name__)
        self._session = None
        self._api_key = None
        self._client_version = None
        self.continuation = replay_continuation
        if interruptable:
            self._install_signal_handler()
        self._setup()

    def _install_signal_handler(self):
        """Handle Ctrl-C, but only where a handler can be installed.

        `signal.signal` raises `ValueError` off the main thread, so a caller that
        runs the reader in a worker thread — the ordinary shape for an app — used
        to get a crash at construction for leaving the default in place.
        """
        try:
            signal.signal(signal.SIGINT, lambda a, b: self.terminate())
        except (ValueError, OSError):
            self._logger.debug("SIGINT handler not installed (not the main thread).")

    def _setup(self):
        if self._is_replay:
            # A replay reader has no live token to start from: `_get_contents`
            # fetches the archive on its first pass. Taking a live continuation
            # here was why `force_replay=True` silently behaved like a live
            # reader that delivered nothing.
            return
        if not self.continuation:
            time.sleep(0.1)  # sleep shortly to prohibit skipping fetching data
            """Take the page's own continuation and start the poll loop.

            The token is scraped, not generated. The generator this used to call
            re-encoded a protobuf YouTube no longer accepts: measured on a live
            stream, its token returned zero chat items while the page's own token
            returned 75.
            """
            self._load_session()
            self.continuation = self._session.continuations[0] if self._session else None

    def _load_session(self):
        self._session = resolver.resolve(self._client, self._video_id)
        self._api_key = self._session.api_key
        self._client_version = self._session.client_version
        self._logger.debug(
            "[%s] %d continuation candidate(s), client %s",
            self._video_id, len(self._session.continuations), self._client_version,
        )

    def _poll_url(self, replay: bool) -> str:
        base = config.REPLAY_CHAT_URL if replay else config.LIVE_CHAT_URL
        return f"{base}?key={self._api_key}&prettyPrint=false"

    def _get_chat_component(self):
        ''' Fetch chat data and store them into buffer,
        get next continuaiton parameter and loop.

        Parameter
        ---------
        continuation : str
            parameter for next chat data
        '''
        try:
            # A replay reader starts with no token: its first pass fetches the
            # archive. Guarding on `self.continuation` here meant `force_replay`
            # delivered nothing at all.
            if self._is_alive and (self.continuation or self._is_replay):
                contents = self._get_contents(self.continuation, self._client, headers)
                metadata, chatdata = self._parser.parse(contents)
                timeout = metadata['timeoutMs'] / 1000
                chat_component = {
                    "video_id": self._video_id,
                    "timeout": timeout,
                    "chatdata": chatdata
                }
                self.continuation = metadata.get('continuation')
                self._last_offset_ms = metadata.get('last_offset_ms', 0)
                return chat_component
        except exceptions.ChatParseException as e:
            self._logger.debug(f"[{self._video_id}]{str(e)}")
            self._raise_exception(e)
        except Exception as e:
            self._logger.error(f"{traceback.format_exc(limit=-1)}")
            self._raise_exception(e)

    def _get_contents(self, continuation, client, headers):
        '''Get 'continuationContents' from livechat json.
           If contents is None at first fetching,
           try to fetch archive chat data.

          Return:
          -------
            'continuationContents' which includes metadata & chat data.
        '''
        livechat_json = self._get_livechat_json(
            continuation, client, replay=self._is_replay, offset_ms=self._last_offset_ms)
        contents, dat = self._parser.get_contents(livechat_json)
        if self._first_fetch:
            if contents is None or self._is_replay:
                '''Try to fetch archive chat data.'''
                self._parser.is_replay = True
                self._is_replay = True
                contents = self._fetch_replay()
            self._first_fetch = False
        return contents

    def _fetch_replay(self):
        """Replay data, from the token that endpoint actually takes.

        Every continuation the popout page carries is rejected by
        `get_live_chat_replay` — measured: all of them answered `error`. The
        player's own seek token is a different field on the watch page, and it is
        the one that works.
        """
        if self._session is None:
            self._load_session()
        seek = resolver.player_seek(self._client, self._session) if self._session else None
        if not seek:
            raise exceptions.NoContinuation(
                "No playerSeek continuation on the watch page; "
                "the video may have no archived chat."
            )
        livechat_json = self._get_livechat_json(
            seek, self._client, replay=True, offset_ms=self.seektime * 1000)
        # YouTube has rejected every replay continuation since mid-October 2025 —
        # not this token specifically. Reported upstream against chat-downloader,
        # yt-dlp and ytarchive too, so it is the endpoint, not the request. Say so,
        # because "Request contains an invalid argument" sends the reader hunting
        # for a token bug that cannot be fixed here.
        if isinstance(livechat_json, dict) and "error" in livechat_json:
            raise exceptions.ReplayUnavailable(
                "YouTube no longer serves archived chat over "
                "get_live_chat_replay (broken upstream since ~2025-10). "
                "Live chat still works; replay does not, for any client."
            )
        reload_continuation = self._parser.reload_continuation(
            self._parser.get_contents(livechat_json)[0])
        if reload_continuation:
            livechat_json = self._get_livechat_json(
                reload_continuation, self._client, replay=True,
                offset_ms=self.seektime * 1000)
        contents, _ = self._parser.get_contents(livechat_json)
        return contents

    def _get_livechat_json(self, continuation, client, replay: bool, offset_ms: int = 0):
        '''
        Get json which includes chat data.
        '''
        livechat_json = None
        err = None
        param = util.get_param(
            continuation,
            dat=self._dat,
            replay=replay,
            offsetms=offset_ms,
            client_version=self._client_version,
        )
        url = self._poll_url(replay)
        for _ in range(MAX_RETRY + 1):
            try:
                response = client.post(url, json=param)
                livechat_json = response.json()
                break
            except (json.JSONDecodeError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
                err = e
                time.sleep(2)
                continue
        else:
            self._logger.error(f"[{self._video_id}]"
                               f"Exceeded retry count. Last error: {str(err)}")
            self._raise_exception(exceptions.RetryExceedMaxCount())
        # A token YouTube has forgotten answers 200 with an `error` body rather
        # than an HTTP failure, so it is read here: otherwise the poll loop treats
        # an expired session as a quiet stream and waits forever.
        if isinstance(livechat_json, dict) and "error" in livechat_json:
            message = livechat_json["error"].get("message", str(livechat_json["error"]))
            self._logger.error(f"[{self._video_id}] chat request rejected: {message}")
            # Raised, not held: `_get_livechat_json` is called again further up
            # the replay path, and a *held* exception lets that next call go
            # through against the client `terminate()` just closed — so the
            # caller saw "client has been closed" instead of this message.
            if replay:
                exc = exceptions.ReplayUnavailable(
                    "YouTube no longer serves archived chat over "
                    f"get_live_chat_replay (broken upstream since ~2025-10): {message}"
                )
            else:
                exc = exceptions.ResponseContextError(message)
            self._is_alive = False
            self.processor.finalize()
            if self._hold_exception is False:
                raise exc
            self._exception_holder = exc
            raise exc
        return livechat_json

    def get(self):
        if self.is_alive():
            chat_component = self._get_chat_component()
            return self.processor.process([chat_component])
        else:
            return []

    def is_replay(self):
        return self._is_replay

    def is_alive(self):
        return self._is_alive

    def terminate(self):
        if not self.is_alive():
            return
        self._is_alive = False
        self.processor.finalize()
        if self._owns_client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 — a close must not mask the caller's reason
                pass

    def raise_for_status(self):
        if self._exception_holder is not None:
            raise self._exception_holder

    def _raise_exception(self, exception: Exception = None):
        # The exception is recorded before `terminate()`: closing the client used
        # to happen first, so the next request inside the failing call raised
        # "client has been closed" and buried the real reason.
        if self._hold_exception is False:
            self._is_alive = False
            self.processor.finalize()
            raise exception
        self._exception_holder = exception
        self.terminate()
