"""
bosszp.py — BOSS直聘渠道

默认工具: mcp-bosszp (mcporter)
可替换为: 其他招聘工具……

注意：bosszp mcporter server 当前 HTTP 404，需修复服务
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)


# ── Tool 1: mcporter BOSS直聘 MCP ────────────────────────────

class BossZPMcporterTool(BaseTool):
    """mcporter BOSS直聘 — mcp-bosszp"""
    name = "bosszp_mcporter"
    description = "Agent Reach mcporter BOSS直聘 MCP（需修复服务）"
    speed = "★★★☆☆"
    reliability = "★★☆☆☆"
    needs_login = True

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "", **kwargs) -> list[FetchedItem]:
        if not query:
            query = source_name

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._search_jobs, query)

        if not result:
            raise RuntimeError(f"BOSS直聘 mcporter returned empty for {query}")

        items = []
        results = result if isinstance(result, list) else [result]
        for job in results:
            items.append(FetchedItem(
                source_name=source_name or "BOSS直聘", source_url=url,
                title=job.get("title", job.get("jobName", "")),
                url=job.get("url", ""),
                content=json.dumps(job, ensure_ascii=False)[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=job.get("description", job.get("jobDesc", ""))[:500],
                author=job.get("company", job.get("brandName", "")),
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _search_jobs(query: str) -> list:
        try:
            cmd = f"""mcporter call 'bosszp.search_jobs(keyword: "{query}")' --output json"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"BOSS直聘 mcporter failed: {e}")
        return []


# ── BOSS直聘 Channel ──────────────────────────────────────────

class BossZPChannel(BaseChannel):
    """
    BOSS直聘渠道

    目前只有 mcporter MCP 一个工具
    """
    name = "bosszp"
    description = "BOSS直聘职位搜索"
    tools = [BossZPMcporterTool]


register_channel(BossZPChannel())
