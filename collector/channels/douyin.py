"""
douyin.py — 抖音渠道

默认工具: mcporter MCP (Agent Reach)
可替换为: 其他抖音工具……
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)


# ── Tool 1: mcporter (抖音 MCP) ──────────────────────────────

class DouyinMcporterTool(BaseTool):
    """mcporter 抖音 — Agent Reach MCP（3 个工具）"""
    name = "douyin_mcporter"
    description = "Agent Reach mcporter 抖音 MCP，解析/下载/转文字"
    speed = "★★★☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._parse_douyin, url)

        if not result:
            raise RuntimeError(f"douyin mcporter returned empty for {url}")

        title = result.get("title", result.get("desc", source_name))
        author = result.get("author", result.get("nickname", ""))
        content = ""
        if depth == FetchDepth.FULL_TEXT:
            text_result = await loop.run_in_executor(None, self._extract_text, url)
            content = text_result or result.get("desc", "")

        return [FetchedItem(
            source_name=source_name or "抖音", source_url=url,
            title=str(title)[:200], url=url,
            content=str(content)[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=str(title),
            author=str(author),
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    @staticmethod
    def _parse_douyin(share_link: str) -> dict:
        try:
            cmd = f"""mcporter call 'douyin.parse_douyin_video_info(share_link: "{share_link}")' --output json"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"desc": result.stdout.strip()}
        except Exception as e:
            logger.warning(f"douyin mcporter parse failed: {e}")
        return {}

    @staticmethod
    def _extract_text(share_link: str) -> str:
        try:
            cmd = f"""mcporter call 'douyin.extract_douyin_text(share_link: "{share_link}")' --output text"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"douyin extract_text failed: {e}")
        return ""


# ── Douyin Channel ────────────────────────────────────────────

class DouyinChannel(BaseChannel):
    """
    抖音渠道

    目前只有 mcporter MCP 一个工具
    """
    name = "douyin"
    description = "抖音视频解析/下载/转文字"
    tools = [DouyinMcporterTool]


register_channel(DouyinChannel())
