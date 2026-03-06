"""
rss.py — RSS/Atom 订阅渠道

默认工具: feedparser
可替换为: x-reader（也能解析 RSS）、Jina Reader
"""

import asyncio
import re

import httpx

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)


# ── Tool 1: feedparser ────────────────────────────────────────

class FeedparserTool(BaseTool):
    """feedparser — 标准 RSS/Atom 解析，最快最稳定"""
    name = "feedparser"
    description = "Python feedparser 库，标准 RSS/Atom 解析"
    speed = "★★★★★"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        try:
            import feedparser
        except ImportError:
            raise RuntimeError("feedparser not installed: pip install feedparser")

        loop = asyncio.get_event_loop()
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                })
                resp.raise_for_status()
                raw_content = resp.text
            feed = await loop.run_in_executor(None, feedparser.parse, raw_content)
        except Exception:
            feed = await loop.run_in_executor(None, feedparser.parse, url)

        items = []
        for entry in feed.entries:
            item = FetchedItem(
                source_name=source_name or feed.feed.get("title", ""),
                source_url=url,
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                summary=entry.get("summary", "")[:500] if depth == FetchDepth.TITLE_ONLY else "",
                content=entry.get("content", [{}])[0].get("value", "") if depth == FetchDepth.FULL_TEXT else "",
                published=entry.get("published", ""),
                author=entry.get("author", ""),
                fetch_method=self.name,
                fetch_depth=depth.value,
            )
            items.append(item)
        return items


# ── Tool 2: x-reader (RSS 模式) ──────────────────────────────

# 复用 web.py 中的 XReaderTool
from .web import XReaderTool as XReaderRSSTool


# ── Tool 3: Jina Reader (RSS 降级) ───────────────────────────

from .web import JinaReaderTool as JinaReaderRSSTool


# ── RSS Channel ───────────────────────────────────────────────

class RSSChannel(BaseChannel):
    """
    RSS/Atom 订阅渠道

    降级链: feedparser → x-reader → Jina Reader
    """
    name = "rss"
    description = "标准 RSS/Atom 解析，最快最稳"
    tools = [FeedparserTool, XReaderRSSTool, JinaReaderRSSTool]


register_channel(RSSChannel())
