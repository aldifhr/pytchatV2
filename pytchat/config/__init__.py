"""Runtime configuration.

The endpoints used to be stored here as obfuscated blobs (ASCII85-encoded so the
URLs did not appear in the source), which made them impossible to audit and
impossible to update without the original encoder. They are plain constants now,
and the key they carried is gone with them: the InnerTube key is per-page and is
read from the page at request time (see `paramgen.resolver`). The baked 2021 key
is exactly the kind of thing that stops working, silently, years later.
"""

import logging  # noqa

from . import mylogger

headers = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}
m_headers = {
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
    ),
}

#: The chat endpoints. `?key=<INNERTUBE_API_KEY>` is appended per request from
#: the page the token came from; a key baked in here would go stale unnoticed.
LIVE_CHAT_URL = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat"
REPLAY_CHAT_URL = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat_replay"

#: Names the rest of the package already imports.
_sml = LIVE_CHAT_URL
_smr = REPLAY_CHAT_URL


def logger(module_name: str, loglevel=None):
    module_logger = mylogger.get_logger(module_name, loglevel=loglevel)
    return module_logger
