"""
多工具采集引擎 — Fetcher Engine (v2: channels 架构)

职责：
1. 根据信源类型自动选择 channel（渠道）
2. 每个 channel 内部维护自己的工具降级链
3. Channel 之间由 FetcherEngine 编排
4. 并发采集，尊重限速

架构变更 (v1 → v2)：
  v1: 单文件 15 个 Fetcher 类 + FALLBACK_CHAINS 字典
  v2: channels/ 目录，每个渠道一个独立文件，可插拔

已接入渠道（14个）：
  channels/
  ├── web.py          → x-reader / Jina Reader / Firecrawl / Crawl4AI / Tavily / httpx
  ├── rss.py          → feedparser / x-reader / Jina Reader
  ├── twitter.py      → feedparser(RSSHub) / xreach / x-reader
  ├── youtube.py      → yt-dlp / x-reader
  ├── github.py       → gh CLI / GitHub API / Jina Reader
  ├── bilibili.py     → yt-dlp / bilibili-api / x-reader
  ├── reddit.py       → JSON API / PRAW / Exa / Jina Reader
  ├── xiaohongshu.py  → mcporter MCP / x-reader
  ├── douyin.py       → mcporter MCP
  ├── linkedin.py     → mcporter MCP / Jina Reader
  ├── bosszp.py       → mcporter MCP
  ├── exa_search.py   → Tavily Search / Exa (mcporter) / Multi-Search
  ├── api.py          → httpx API / httpx Web
  ├── browser.py      → nodriver / BrowserWing
  └── __init__.py     → 渠道注册 (doctor 检测用)

  外部服务：
  ClawFeed (http://127.0.0.1:8767) — AI新闻摘要（独立调用，不在渠道中）
"""

import asyncio
import logging

import httpx

from .channels import (
    FetchDepth, FetchedItem,
    all_channels, get_channel, doctor,
)

# 向后兼容：重新导出 FetchDepth / FetchedItem，让 task_profiles.py 等不用改
__all__ = ["FetcherEngine", "FetchDepth", "FetchedItem", "ClawFeedHelper"]

logger = logging.getLogger("collector.fetcher")


# ── 信源类型 → Channel 映射 ──────────────────────────────────

# 这个映射决定了 source["_fetch_method"] 对应哪个 channel
CHANNEL_MAP = {
    "rss": "rss",
    "rss_with_x_fallback": "twitter",
    "web_scrape": "web",
    "api": "api",
    "xiaohongshu": "xiaohongshu",
    "douyin": "douyin",
    "search": "exa_search",
    "github": "github",
    "youtube": "youtube",
    "bilibili": "bilibili",
    "reddit": "reddit",
    "linkedin": "linkedin",
    "bosszp": "bosszp",
    "browser": "browser",
}


# ── ClawFeed 独立服务 Helper ─────────────────────────────────

CLAWFEED_BASE = "http://127.0.0.1:8767"


class ClawFeedHelper:
    """
    ClawFeed — AI 新闻摘要服务（独立调用，不参与渠道降级）
    API: http://127.0.0.1:8767
    """

    @staticmethod
    async def health_check() -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{CLAWFEED_BASE}/api/health")
                return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    async def create_digest(sources: list[str] = None, date: str = None) -> dict:
        params = {}
        if sources:
            params["sources"] = sources
        if date:
            params["date"] = date
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{CLAWFEED_BASE}/api/digest", json=params)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def get_digest(digest_id: str = None) -> dict:
        url = f"{CLAWFEED_BASE}/api/digest/{digest_id}" if digest_id else f"{CLAWFEED_BASE}/api/digest/latest"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def list_sources() -> list:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{CLAWFEED_BASE}/api/sources")
            resp.raise_for_status()
            return resp.json()


# ── 采集引擎（编排层）────────────────────────────────────────

class FetcherEngine:
    """
    采集引擎 — 核心编排器 (v2: channels 架构)

    对外接口与 v1 完全相同：
      - fetch_source(source, depth)
      - fetch_batch(sources, depth)
      - fetch_url(url, depth, method)
      - stats / reset_stats()
      - list_tools()

    内部从 channels/ 加载渠道，每个渠道内部自动降级。
    """

    def __init__(self, concurrency: int = 10, rate_limit: float = 0.2):
        self.concurrency = concurrency
        self.rate_limit = rate_limit
        self._semaphore = asyncio.Semaphore(concurrency)
        self._stats = {"success": 0, "failed": 0, "total_items": 0, "by_method": {}, "by_channel": {}}

    async def fetch_source(self, source: dict, depth: FetchDepth) -> list[FetchedItem]:
        """
        采集单个信源（来自 SourceManager 的 source dict）
        """
        method = source.get("_fetch_method", "rss")
        channel_name = CHANNEL_MAP.get(method, "web")
        channel = get_channel(channel_name)
        if not channel:
            channel = get_channel("web")  # 兜底用 web

        url = source.get("url", "")
        name = source.get("name", "")

        async with self._semaphore:
            try:
                items = await channel.fetch(url, depth, source_name=name)
                if items:
                    self._stats["success"] += 1
                    self._stats["total_items"] += len(items)
                    tool_used = items[0].fetch_method if items else channel_name
                    self._stats["by_method"][tool_used] = self._stats["by_method"].get(tool_used, 0) + 1
                    self._stats["by_channel"][channel_name] = self._stats["by_channel"].get(channel_name, 0) + 1
                    for item in items:
                        item.lang = source.get("lang", "en")
                    return items
            except Exception as e:
                logger.error(f"[{channel_name}] ALL TOOLS FAILED for {name} ({url}): {e}")

            self._stats["failed"] += 1
            return []

    async def fetch_batch(self, sources: list, depth: FetchDepth,
                          progress_callback=None) -> list[FetchedItem]:
        """批量采集多个信源"""
        all_items = []
        total = len(sources)

        async def _fetch_one(idx, src):
            await asyncio.sleep(self.rate_limit * idx * 0.1)
            items = await self.fetch_source(src, depth)
            if progress_callback:
                progress_callback(idx + 1, total, src.get("name", ""))
            return items

        tasks = [_fetch_one(i, src) for i, src in enumerate(sources)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Batch fetch exception: {result}")

        return all_items

    async def fetch_url(self, url: str, depth: FetchDepth = FetchDepth.FULL_TEXT,
                        source_name: str = "", method: str = "auto") -> list[FetchedItem]:
        """
        直接采集单个 URL

        method 参数:
          - "auto": 根据 URL 特征自动选渠道
          - channel 名称 (如 "web", "twitter", "rss"): 使用指定渠道
          - tool 名称 (如 "jina_reader", "firecrawl", "crawl4ai"): 在对应渠道中指定工具
        """
        if method != "auto":
            # 先尝试作为 channel 名称
            channel = get_channel(method)
            if channel:
                return await channel.fetch(url, depth, source_name=source_name)

            # 再尝试作为 tool 名称，在所有 channel 中查找
            for ch_name, ch in all_channels().items():
                for tool_cls in ch.tools:
                    if tool_cls.name == method:
                        return await ch.fetch_with_tool(method, url, depth, source_name=source_name)

            # 兼容旧名称映射
            old_name_map = {
                "feedparser": "rss", "x-reader": "web", "xreader": "web",
                "xreach": "twitter", "crawl4ai": "web", "nodriver": "browser",
                "jina": "web", "jina_reader": "web",
                "tavily": "web", "tavily_extract": "web", "tavily_search": "exa_search",
                "browserwing": "browser", "web_fetch": "web", "httpx_web": "web",
                "api": "api", "httpx_api": "api",
                "exa": "exa_search", "exa_search": "exa_search",
                "xiaohongshu": "xiaohongshu", "xhs": "xiaohongshu",
                "douyin": "douyin", "multi_search": "exa_search", "search": "exa_search",
                "firecrawl": "web",
            }
            channel_name = old_name_map.get(method)
            if channel_name:
                channel = get_channel(channel_name)
                if channel:
                    return await channel.fetch(url, depth, source_name=source_name)

            raise ValueError(f"Unknown method: {method}. Available channels: {list(all_channels().keys())}")

        # 自动选择：根据 URL 特征判断
        channel_name = self._auto_detect_channel(url)
        channel = get_channel(channel_name) or get_channel("web")
        return await channel.fetch(url, depth, source_name=source_name)

    @staticmethod
    def _auto_detect_channel(url: str) -> str:
        """根据 URL 特征自动判断使用哪个 channel"""
        if "x.com/" in url or "twitter.com/" in url:
            return "twitter"
        if "xiaohongshu.com" in url or "xhslink.com" in url:
            return "xiaohongshu"
        if "douyin.com" in url:
            return "douyin"
        if "youtube.com" in url or "youtu.be/" in url:
            return "youtube"
        if "github.com" in url:
            return "github"
        if "bilibili.com" in url or "b23.tv/" in url:
            return "bilibili"
        if "reddit.com" in url:
            return "reddit"
        if "linkedin.com" in url:
            return "linkedin"
        if url.endswith((".xml", ".rss", ".atom", "/feed", "/rss")):
            return "rss"
        return "web"

    @property
    def stats(self) -> dict:
        return self._stats

    def reset_stats(self):
        self._stats = {"success": 0, "failed": 0, "total_items": 0, "by_method": {}, "by_channel": {}}

    @staticmethod
    def list_tools() -> list[dict]:
        """列出所有渠道及其工具"""
        result = []
        for ch_name, channel in all_channels().items():
            for tool_info in channel.list_tools():
                result.append({
                    "channel": ch_name,
                    **tool_info,
                })
        # ClawFeed（独立服务）
        result.append({
            "channel": "clawfeed",
            "name": "clawfeed",
            "description": "AI 新闻摘要服务（独立调用）",
            "speed": "N/A",
            "reliability": "★★★★☆",
            "needs_login": False,
            "note": "独立服务 http://127.0.0.1:8767, 通过 ClawFeedHelper 调用",
        })
        return result

    @staticmethod
    def list_channels() -> list[dict]:
        """列出所有已注册渠道"""
        return [ch.info() for ch in all_channels().values()]

    @staticmethod
    def doctor() -> dict:
        """健康检查：检测所有渠道和工具"""
        return doctor()
