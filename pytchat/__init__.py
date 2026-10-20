"""
pytchat is a lightweight python library to browse youtube livechat without Selenium or BeautifulSoup.
"""
__copyright__    = 'Copyright (C) 2019, 2020, 2021 taizan-hokuto'
__version__      = '0.6.0'
__license__      = 'MIT'
# Upstream (taizan-hokuto/pytchat) is archived and its generated-token path
# stopped working years ago; this fork replaces it. `__author__` keeps the
# original because the bulk of the code is theirs and MIT requires the notice to
# travel with it, but `__url__` has to point at the place bugs can actually be
# fixed — otherwise every traceback and every `pip show` sends the reader to a
# repository that cannot accept an issue.
__author__       = 'taizan-hokuto'
__author_email__ = '55448286+taizan-hokuto@users.noreply.github.com'
__url__          = 'https://github.com/aldifhr/pytchatV2'


from .exceptions import (
    ChatParseException,
    ResponseContextError,
    NoContents,
    NoContinuation,
    IllegalFunctionCall,
    InvalidVideoIdException,
    UnknownConnectionError,
    RetryExceedMaxCount,
    ChatDataFinished,
    ReceivedUnknownContinuation,
    FailedExtractContinuation,
    VideoInfoParseError,
    PatternUnmatchError
)

from .api import (
    config,
    LiveChat,
    LiveChatAsync,
    ChatProcessor,
    CompatibleProcessor,
    DummyProcessor,
    DefaultProcessor,
    HTMLArchiver,
    TSVArchiver,
    JsonfileArchiver,
    SimpleDisplayProcessor,
    SpeedCalculator,
    SuperchatCalculator,
    create
)
# flake8: noqa