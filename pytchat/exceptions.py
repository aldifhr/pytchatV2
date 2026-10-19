class ChatParseException(Exception):
    '''
    Base exception thrown by the parser
    '''
    pass


class ResponseContextError(ChatParseException):
    '''
    Thrown when chat data is invalid.
    '''
    pass


class NoContents(ChatParseException):
    '''
    Thrown when ContinuationContents is missing in JSON.
    '''
    pass


class NoContinuation(ChatParseException):
    '''
    Thrown when continuation is missing in ContinuationContents.
    '''
    pass


class IllegalFunctionCall(Exception):
    '''
    Thrown when get() is called even though
    set_callback() has been executed.
    '''
    pass


class InvalidVideoIdException(Exception):
    '''
    Thrown when the video_id is not exist (VideoInfo).
    '''
    def __init__(self, doc):
        self.msg = "InvalidVideoIdException"
        self.doc = doc


class UnknownConnectionError(Exception):
    pass


class RetryExceedMaxCount(Exception):
    '''
    Thrown when the number of retries exceeds the maximum value.
    '''
    pass


class ChatDataFinished(ChatParseException):
    pass


class ReplayUnavailable(ChatDataFinished):
    '''
    Thrown when archived chat cannot be fetched.

    Distinct from a bad token: YouTube stopped serving `get_live_chat_replay` to
    every client in mid-October 2025 (reported against chat-downloader, yt-dlp
    and ytarchive alike). Failing as `ChatDataFinished` keeps a caller's replay
    loop ending the way a finished stream should, while the message says why.
    '''
    pass


class ReceivedUnknownContinuation(ChatParseException):
    pass


class FailedExtractContinuation(ChatDataFinished):
    pass


class VideoInfoParseError(Exception):
    '''
    Base exception when parsing video info.
    '''


class PatternUnmatchError(VideoInfoParseError):
    '''
    Thrown when failed to parse video info with unmatched pattern.
    '''
    def __init__(self, doc=''):
        self.msg = "PatternUnmatchError"
        self.doc = doc
