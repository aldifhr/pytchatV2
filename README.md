pytchat
=======

pytchat is a python library for fetching youtube live chat.
 

<br><br><br>
## Description
pytchat is a python library for fetching youtube live chat
without using Selenium or BeautifulSoup.

Other features:
+ Customizable [chat data processors](https://github.com/taizan-hokuto/pytchat/wiki/ChatProcessor) including youtube api compatible one.
+ Available on asyncio context.

## Status (fork, 2026-10)

This fork fixes a break that made the library fetch **zero chat items** while
reporting no error. The cause was the continuation parameter: the original code
*generated* it by re-encoding a protobuf that YouTube no longer accepts. Measured
on one live stream, a generated token returned 0 items and the page's own token
returned 75.

What changed:

+ **Continuation tokens are read from the page**, not generated
  (`pytchat/paramgen/resolver.py`). The InnerTube key and client version come
  from that same page, so a rotation does not need a library release.
  `liveparam` and `arcparam` are deleted — a fallback that yields an empty chat
  hides the failure.
+ **Channel id regex** accepts the `\x22`-escaped JSON the site emits now, and
  the id is no longer truncated to 21 characters by an optional group.
+ **`force_replay=True` actually reads the archive.** It used to take a live
  token in `_setup` and then deliver nothing.
+ **Errors are surfaced, not buried.** A rejected request used to close the HTTP
  client before recording the reason, so the caller saw "client has been closed".
+ **Python 3.10+.** `signal.signal` off the main thread no longer raises at
  construction; `asyncio.get_event_loop` is now `get_running_loop`;
  `CancelledError` is handled; the default `processor` is per-instance instead of
  one object shared by every reader ever created.

### Known broken upstream

**Chat replay is dead.** `get_live_chat_replay` has answered
"Request contains an invalid argument" for every continuation since
mid-October 2025 — for this library, `chat-downloader`, `yt-dlp` and `ytarchive`
alike. Nothing in this repo can fix it. `force_replay` raises
`ReplayUnavailable` with that message instead of failing obscurely.

**Live chat works.** Verified against a running stream: 34 items in 15s.

For more detailed information, see [wiki](https://github.com/taizan-hokuto/pytchat/wiki). <br>
[wiki (Japanese)](https://github.com/taizan-hokuto/pytchat/wiki/Home_jp)

## Install
```python
pip install pytchat
```
## Examples


### Fetch chat data (see [wiki](https://github.com/taizan-hokuto/pytchat/wiki/PytchatCore))
```python
import pytchat
chat = pytchat.create(video_id="uIx8l2xlYVY")
while chat.is_alive():
    for c in chat.get().sync_items():
        print(f"{c.datetime} [{c.author.name}]- {c.message}")
```


### Output JSON format string (feature of [DefaultProcessor](https://github.com/taizan-hokuto/pytchat/wiki/DefaultProcessor))
```python
import pytchat
import time

chat = pytchat.create(video_id="uIx8l2xlYVY")
while chat.is_alive():
    print(chat.get().json())
    time.sleep(5)
    '''
    # Each chat item can also be output in JSON format.
    for c in chat.get().items:
        print(c.json())
    '''     
```


### other
+ Fetch chat with a buffer ([LiveChat](https://github.com/taizan-hokuto/pytchat/wiki/LiveChat))

+ Use with asyncio ([LiveChatAsync](https://github.com/taizan-hokuto/pytchat/wiki/LiveChatAsync))

+ YT API compatible chat processor ([CompatibleProcessor](https://github.com/taizan-hokuto/pytchat/wiki/CompatibleProcessor))


## Structure of Default Processor
Each item can be got with `sync_items()` function.
<table>
  <tr>
    <th>name</th>
    <th>type</th>
    <th>remarks</th>
  </tr>
  <tr>
    <td>type</td>
    <td>str</td>
    <td>"superChat","textMessage","superSticker","newSponsor"</td>
  </tr>
  <tr>
    <td>id</td>
    <td>str</td>
    <td></td>
  </tr>
  <tr>
    <td>message</td>
    <td>str</td>
    <td>emojis are represented by ":(shortcut text):"</td>
  </tr>
  <tr>
    <td>messageEx</td>
    <td>str</td>
    <td>list of message texts and emoji dicts(id, txt, url).</td>
  </tr>
  <tr>
    <td>timestamp</td>
    <td>int</td>
    <td>unixtime milliseconds</td>
  </tr>
  <tr>
    <td>datetime</td>
    <td>str</td>
    <td>e.g. "2019-10-10 12:34:56"</td>
  </tr>
    <td>elapsedTime</td>
    <td>str</td>
    <td>elapsed time. (e.g. "1:02:27") *Replay Only.</td>
  </tr>
  <tr>
    <td>amountValue</td>
    <td>float</td>
    <td>e.g. 1,234.0</td>
  </tr>
  <tr>
    <td>amountString</td>
    <td>str</td>
    <td>e.g. "$ 1,234"</td>
  </tr>
  <tr>
    <td>currency</td>
    <td>str</td>
    <td><a href="https://en.wikipedia.org/wiki/ISO_4217">ISO 4217 currency codes</a> (e.g. "USD")</td>
  </tr>
  <tr>
    <td>bgColor</td>
    <td>int</td>
    <td>RGB Int</td>
  </tr>
  <tr>
    <td>author</td>
    <td>object</td>
    <td>see below</td>
  </tr>
</table>

Structure of author object.
<table>
  <tr>
    <th>name</th>
    <th>type</th>
    <th>remarks</th>
  </tr>
  <tr>
    <td>name</td>
    <td>str</td>
    <td></td>
  </tr>
  <tr>
    <td>channelId</td>
    <td>str</td>
    <td>*chatter's channel ID.</td>
  </tr>
  <tr>
    <td>channelUrl</td>
    <td>str</td>
    <td></td>
  </tr>
  <tr>
    <td>imageUrl</td>
    <td>str</td>
    <td></td>
  </tr>
  <tr>
    <td>badgeUrl</td>
    <td>str</td>
    <td></td>
  </tr>
  <tr>
    <td>isVerified</td>
    <td>bool</td>
    <td></td>
  </tr>
  <tr>
    <td>isChatOwner</td>
    <td>bool</td>
    <td></td>
  </tr>
  <tr>
    <td>isChatSponsor</td>
    <td>bool</td>
    <td></td>
  </tr>
  <tr>
    <td>isChatModerator</td>
    <td>bool</td>
    <td></td>
  </tr>
</table>

## Licence

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)


