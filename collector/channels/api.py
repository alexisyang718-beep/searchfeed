"""
api.py — JSON API 渠道

默认工具: httpx API 直接请求
可替换为: httpx 通用网页
"""

import re

import httpx

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    logger, register_channel,
)


# ── Tool 1: httpx API ────────────────────────────────────────

class HttpxAPITool(BaseTool):
    """httpx API — JSON API 直接请求"""
    name = "httpx_api"
    description = "httpx 直接请求 JSON API 端点"
    speed = "★★★★★"
    reliability = "★★★★★"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "SignalCollector/1.0"})
            resp.raise_for_status()
            data = resp.json()

        entries = []
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            for key in ("items", "data", "results", "articles", "entries", "feed"):
                if key in data and isinstance(data[key], list):
                    entries = data[key]
                    break
            if not entries:
                entries = [data]

        items = []
        for entry in entries[:50]:
            title = entry.get("title", entry.get("name", entry.get("text", "")))
            link = entry.get("url", entry.get("link", entry.get("href", "")))
            if not title:
                continue
            item = FetchedItem(
                source_name=source_name, source_url=url,
                title=str(title), url=str(link),
                summary=str(entry.get("summary", entry.get("description", entry.get("content", ""))))[:500],
                content=str(entry.get("content", "")) if depth == FetchDepth.FULL_TEXT else "",
                published=str(entry.get("published", entry.get("date", entry.get("created_at", "")))),
                author=str(entry.get("author", entry.get("user", ""))),
                fetch_method=self.name, fetch_depth=depth.value,
            )
            items.append(item)
        return items


# ── Tool 2: httpx 通用网页 ───────────────────────────────────

class HttpxWebTool(BaseTool):
    """httpx Web — 通用网页抓取（降级用）"""
    name = "httpx_web"
    description = "httpx 简单网页抓取，无 JS 渲染"
    speed = "★★★★★"
    reliability = "★★★☆☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            resp.raise_for_status()
            html = resp.text

        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        if m:
            title = m.group(1).strip()

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title or source_name, url=url,
            content=html[:50000] if depth == FetchDepth.FULL_TEXT else "",
            summary=title,
            fetch_method=self.name, fetch_depth=depth.value,
        )]


# ── API Channel ───────────────────────────────────────────────

class APIChannel(BaseChannel):
    """
    JSON API 渠道

    降级链: httpx_api → httpx_web
    """
    name = "api"
    description = "JSON API 直接请求"
    tools = [HttpxAPITool, HttpxWebTool]


register_channel(APIChannel())
