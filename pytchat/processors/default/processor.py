import asyncio
import json
import time
from .custom_encoder import CustomEncoder
from .renderer.textmessage import LiveChatTextMessageRenderer
from .renderer.paidmessage import LiveChatPaidMessageRenderer
from .renderer.paidsticker import LiveChatPaidStickerRenderer
from .renderer.legacypaid import LiveChatLegacyPaidMessageRenderer
from .renderer.membership import LiveChatMembershipItemRenderer
from .renderer.donation import LiveChatDonationAnnouncementRenderer
from .. chat_processor import ChatProcessor
from ... import config

logger = config.logger(__name__)


class Chat:
    def json(self) -> str:
        return json.dumps(vars(self), ensure_ascii=False, cls=CustomEncoder)


class Chatdata:

    def __init__(self, chatlist: list, timeout: float, abs_diff):
        self.items = chatlist
        self.interval = timeout
        self.abs_diff = abs_diff
        self.itemcount = 0

    def tick(self):
        '''DEPRECATE
            Use sync_items()
        '''
        if len(self.items) < 1:
            time.sleep(1)
            return
        if self.itemcount == 0:
            self.starttime = time.time()
        if len(self.items) == 1:
            total_itemcount = 1
        else:
            total_itemcount = len(self.items) - 1
        next_chattime = (self.items[0].timestamp + (self.items[-1].timestamp - self.items[0].timestamp) / total_itemcount * self.itemcount) / 1000
        tobe_disptime = self.abs_diff + next_chattime
        wait_sec = tobe_disptime - time.time()
        self.itemcount += 1
        
        if wait_sec < 0:
            wait_sec = 0
       
        time.sleep(wait_sec)

    async def tick_async(self):
        '''DEPRECATE
            Use async_items()
        '''
        if len(self.items) < 1:
            await asyncio.sleep(1)
            return
        if self.itemcount == 0:
            self.starttime = time.time()
        if len(self.items) == 1:
            total_itemcount = 1
        else:
            total_itemcount = len(self.items) - 1
        next_chattime = (self.items[0].timestamp + (self.items[-1].timestamp - self.items[0].timestamp) / total_itemcount * self.itemcount) / 1000
        tobe_disptime = self.abs_diff + next_chattime
        wait_sec = tobe_disptime - time.time()
        self.itemcount += 1
        
        if wait_sec < 0:
            wait_sec = 0
       
        await asyncio.sleep(wait_sec)

    def sync_items(self):
        """Yield the batch, paced to the speed the messages arrived.

        The pacing is the point: a batch of 70 messages carries timestamps spread
        over the last minute, and replaying them instantly would dump a minute of
        chat into one frame. What was wrong is the budget. `abs_diff` is the lag
        between wall clock and the *first* message ever seen, so on any stream
        more than a few seconds old it makes `wait_total_sec` negative, the queue
        never catches up, and every yield pays a full sleep — measured 45-68s to
        deliver one 70-message batch, while the HTTP request behind it took
        0.09s.

        The cap keeps the pacing but bounds it: if the backlog is larger than one
        batch interval, the stream is behind and dumping it is the right answer.
        """
        starttime = time.time()
        if len(self.items) > 0:
            last_chattime = self.items[-1].timestamp / 1000
            tobe_disptime = self.abs_diff + last_chattime
            wait_total_sec = max(tobe_disptime - time.time(), 0)
            if len(self.items) > 1:
                wait_sec = wait_total_sec / len(self.items)
            else:
                wait_sec = 0
            # A backlog bigger than one batch interval is history, not live
            # chat: pacing it would make the caller wait the past back out. The
            # bug was that `abs_diff` (lag against the first message ever seen)
            # makes that backlog permanent on any stream older than a few
            # seconds, so every batch was paced — 71 messages, 68 seconds, for a
            # request that took 0.09s.
            if wait_total_sec > max(self.interval, 1):
                wait_sec = 0
            for c in self.items:
                if wait_sec > 0:
                    time.sleep(wait_sec)
                yield c
        stop_interval = time.time() - starttime
        if stop_interval < 1:
            time.sleep(1 - stop_interval)

    async def async_items(self):
        """`sync_items`' twin, with the same bounded pacing; see its docstring."""
        starttime = time.time()
        if len(self.items) > 0:
            last_chattime = self.items[-1].timestamp / 1000
            tobe_disptime = self.abs_diff + last_chattime
            wait_total_sec = max(tobe_disptime - time.time(), 0)
            if len(self.items) > 1:
                wait_sec = wait_total_sec / len(self.items)
            else:
                wait_sec = 0
            if wait_total_sec > max(self.interval, 1):
                wait_sec = 0
            for c in self.items:
                if wait_sec > 0:
                    await asyncio.sleep(wait_sec)
                yield c

        stop_interval = time.time() - starttime
        if stop_interval < 1:
            await asyncio.sleep(1 - stop_interval)

    def json(self) -> str:
        return ''.join(("[", ','.join((a.json() for a in self.items)), "]"))


class DefaultProcessor(ChatProcessor):
    def __init__(self):
        self.first = True
        self.abs_diff = 0
        self.renderers = {
            "liveChatTextMessageRenderer": LiveChatTextMessageRenderer(),
            "liveChatPaidMessageRenderer": LiveChatPaidMessageRenderer(),
            "liveChatPaidStickerRenderer": LiveChatPaidStickerRenderer(),
            "liveChatLegacyPaidMessageRenderer": LiveChatLegacyPaidMessageRenderer(),
            "liveChatMembershipItemRenderer": LiveChatMembershipItemRenderer(),
            "liveChatDonationAnnouncementRenderer": LiveChatDonationAnnouncementRenderer(),
        }

    def process(self, chat_components: list):

        chatlist = []
        timeout = 0

        if chat_components:
            for component in chat_components:
                if component is None:
                    continue
                timeout += component.get('timeout', 0)
                chatdata = component.get('chatdata')  # if from Extractor, chatdata is generator.
                if chatdata is None:
                    continue
                for action in chatdata:
                    if action is None:
                        continue
                    if action.get('addChatItemAction') is None:
                        continue
                    item = action['addChatItemAction'].get('item')
                    if item is None:
                        continue
                    chat = self._parse(item)
                    if chat:
                        chatlist.append(chat)
        
        if self.first and chatlist:
            self.abs_diff = time.time() - chatlist[0].timestamp / 1000
            self.first = False

        chatdata = Chatdata(chatlist, float(timeout), self.abs_diff)

        return chatdata

    def _parse(self, item):
        try:
            key = list(item.keys())[0]
            renderer = self.renderers.get(key)
            if renderer is None:
                return None
            renderer.setitem(item.get(key), Chat())
            renderer.settype()
            renderer.get_snippet()
            renderer.get_authordetails()
            rendered_chatobj = renderer.get_chatobj()
            renderer.clear()
        except (KeyError, TypeError) as e:
            logger.error(f"{str(type(e))}-{str(e)} item:{str(item)}")
            return None
        
        return rendered_chatobj
