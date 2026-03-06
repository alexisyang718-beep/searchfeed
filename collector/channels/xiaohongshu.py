"""
xiaohongshu.py — 小红书渠道

默认工具: mcporter MCP (Agent Reach)
可替换为: x-reader、其他 XHS 工具……
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .web import XReaderTool


# ── Tool 1: mcporter (小红书 MCP) ────────────────────────────

class XHSMcporterTool(BaseTool):
    """mcporter 小红书 — Agent Reach MCP（13 个工具）"""
    name = "xhs_mcporter"
    description = "Agent Reach mcporter 小红书 MCP，搜索/详情/发布/评论/用户"
    speed = "★★★★☆"
    reliability = "★★★★☆"
    needs_login = True

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "", **kwargs) -> list[FetchedItem]:
        if not query:
            query = source_name

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._search_xhs, query)

        if not result:
            raise RuntimeError(f"xiaohongshu mcporter returned empty for {query}")

        items = []
        if isinstance(result, list):
            for feed in result:
                title = feed.get("title", feed.get("noteCard", {}).get("displayTitle", ""))
                note_id = feed.get("id", feed.get("noteId", ""))
                link = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
                content_text = feed.get("desc", feed.get("noteCard", {}).get("desc", ""))
                items.append(FetchedItem(
                    source_name=source_name or "小红书", source_url=url,
                    title=str(title)[:200], url=link,
                    content=str(content_text)[:80000] if depth == FetchDepth.FULL_TEXT else "",
                    summary=str(content_text)[:500] if depth == FetchDepth.TITLE_ONLY else str(title),
                    author=feed.get("author", feed.get("noteCard", {}).get("user", {}).get("nickname", "")),
                    fetch_method=self.name, fetch_depth=depth.value,
                ))
        elif isinstance(result, str) and result.strip():
            items.append(FetchedItem(
                source_name=source_name or "小红书", source_url=url,
                title=f"小红书搜索: {query}", url=url,
                content=result[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=result[:500],
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _search_xhs(keyword: str):
        try:
            cmd = f"""mcporter call 'xiaohongshu.search_feeds(keyword: "{keyword}")' --output json"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return result.stdout.strip()
        except Exception as e:
            logger.warning(f"xiaohongshu mcporter failed: {e}")
        return None


# ── Xiaohongshu Channel ──────────────────────────────────────

class XiaohongshuChannel(BaseChannel):
    """
    小红书渠道

    降级链: mcporter MCP → x-reader
    """
    name = "xiaohongshu"
    description = "小红书笔记采集（搜索/详情/feed）"
    tools = [XHSMcporterTool, XReaderTool]


register_channel(XiaohongshuChannel())
