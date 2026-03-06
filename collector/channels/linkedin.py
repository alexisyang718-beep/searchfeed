"""
linkedin.py — LinkedIn 渠道

默认工具: linkedin-mcp (mcporter)
可替换为: LinkedIn API……

注意：linkedin mcporter server 当前 offline，需要启动 localhost:3000 服务
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .web import JinaReaderTool


# ── Tool 1: mcporter LinkedIn MCP ────────────────────────────

class LinkedInMcporterTool(BaseTool):
    """mcporter LinkedIn — linkedin-scraper-mcp"""
    name = "linkedin_mcporter"
    description = "Agent Reach mcporter LinkedIn MCP（需启动服务）"
    speed = "★★★☆☆"
    reliability = "★★★☆☆"
    needs_login = True

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._fetch_profile, url)

        if not result:
            raise RuntimeError(f"LinkedIn mcporter returned empty for {url}")

        name = result.get("name", result.get("full_name", source_name))
        headline = result.get("headline", "")
        summary = result.get("summary", result.get("about", ""))

        return [FetchedItem(
            source_name=source_name or "LinkedIn", source_url=url,
            title=f"{name} — {headline}" if headline else name,
            url=url,
            content=json.dumps(result, ensure_ascii=False)[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=summary[:500] if summary else headline,
            author=name,
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    @staticmethod
    def _fetch_profile(url: str) -> dict:
        try:
            cmd = f"""mcporter call 'linkedin.get_person_profile(url: "{url}")' --output json"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"LinkedIn mcporter failed: {e}")
        return {}


# ── LinkedIn Channel ──────────────────────────────────────────

class LinkedInChannel(BaseChannel):
    """
    LinkedIn 渠道

    降级链: mcporter MCP → Jina Reader
    """
    name = "linkedin"
    description = "LinkedIn 人物/公司页面采集"
    tools = [LinkedInMcporterTool, JinaReaderTool]


register_channel(LinkedInChannel())
