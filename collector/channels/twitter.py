"""
twitter.py — X/Twitter 渠道

默认工具: xreach (Agent Reach CLI)
可替换为: RSSHub(feedparser)、x-reader、Nitter、官方 API……
"""

import asyncio
import json
import re
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .rss import FeedparserTool
from .web import XReaderTool


# ── Tool 1: xreach CLI ───────────────────────────────────────

class XReachTool(BaseTool):
    """xreach — X/Twitter 专用 CLI (Agent Reach)"""
    name = "xreach"
    description = "X/Twitter 专用采集 CLI，支持搜索/用户推文/单条/线程"
    speed = "★★★★☆"
    reliability = "★★★★☆"
    needs_login = True

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        username = self._extract_username(url, source_name)
        if not username:
            raise ValueError(f"Cannot extract X username from {url}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_xreach, username)

        if not result:
            raise RuntimeError(f"xreach returned empty for @{username}")

        items = []
        for tweet in result:
            text = str(tweet.get("text", tweet.get("full_text", "")))
            tweet_id = tweet.get("id", tweet.get("id_str", ""))
            tweet_url = tweet.get("url", f"https://x.com/{username}/status/{tweet_id}" if tweet_id else f"https://x.com/{username}")
            items.append(FetchedItem(
                source_name=source_name, source_url=url,
                title=text[:200], url=tweet_url,
                content=text if depth == FetchDepth.FULL_TEXT else "",
                summary=text[:500],
                published=tweet.get("created_at", tweet.get("timestamp", "")),
                author=username,
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _extract_username(url: str, source_name: str) -> str:
        m = re.search(r"/twitter/user/(\w+)", url)
        if m:
            return m.group(1)
        m = re.search(r"x\.com/(\w+)", url)
        if m:
            return m.group(1)
        m = re.search(r"@(\w+)", source_name)
        if m:
            return m.group(1)
        return ""

    @staticmethod
    def _run_xreach(username: str, count: int = 20) -> list:
        try:
            result = subprocess.run(
                ["xreach", "tweets", username, "-n", str(count), "--json"],
                capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "tweets" in data:
                    return data["tweets"]
                return [data] if data else []
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.warning(f"xreach tweets failed for {username}: {e}")

        # 降级到 search
        try:
            result = subprocess.run(
                ["xreach", "search", f"from:{username}", "--json", "-n", str(count)],
                capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"xreach search failed for {username}: {e}")
        return []


# ── Twitter Channel ───────────────────────────────────────────

class TwitterChannel(BaseChannel):
    """
    X/Twitter 渠道

    降级链: feedparser(RSSHub) → xreach CLI → x-reader
    """
    name = "twitter"
    description = "X/Twitter 采集，RSSHub + xreach CLI"
    tools = [FeedparserTool, XReachTool, XReaderTool]


register_channel(TwitterChannel())
