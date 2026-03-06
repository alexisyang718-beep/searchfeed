"""
github.py — GitHub 渠道

默认工具: gh CLI
可替换为: REST API、PyGitHub……
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .web import JinaReaderTool


# ── Tool 1: gh CLI ────────────────────────────────────────────

class GhCliTool(BaseTool):
    """gh CLI — GitHub 官方命令行工具"""
    name = "gh_cli"
    description = "GitHub CLI，支持 repo/issue/PR/release 查询"
    speed = "★★★★☆"
    reliability = "★★★★★"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "", **kwargs) -> list[FetchedItem]:
        # 判断 URL 类型
        if "github.com" in url:
            return await self._fetch_repo(url, depth, source_name)
        elif query:
            return await self._search_repos(query, depth, source_name)
        else:
            raise ValueError(f"Cannot determine GitHub action from {url}")

    async def _fetch_repo(self, url: str, depth: FetchDepth,
                          source_name: str) -> list[FetchedItem]:
        """获取仓库信息"""
        import re
        m = re.search(r"github\.com/([^/]+/[^/]+)", url)
        if not m:
            raise ValueError(f"Cannot extract repo from {url}")
        repo = m.group(1).rstrip("/")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_gh, ["gh", "repo", "view", repo, "--json",
                                                                   "name,description,stargazersCount,url,createdAt,updatedAt,primaryLanguage,readme"])

        if not result:
            raise RuntimeError(f"gh CLI returned empty for {repo}")

        readme = result.get("readme", "") if depth == FetchDepth.FULL_TEXT else ""

        return [FetchedItem(
            source_name=source_name or "GitHub", source_url=url,
            title=f"{repo}: {result.get('description', '')}",
            url=result.get("url", url),
            content=readme[:80000],
            summary=result.get("description", "")[:500],
            published=result.get("updatedAt", result.get("createdAt", "")),
            fetch_method=self.name, fetch_depth=depth.value,
            extra={"stars": result.get("stargazersCount"), "language": result.get("primaryLanguage", {}).get("name")},
        )]

    async def _search_repos(self, query: str, depth: FetchDepth,
                            source_name: str) -> list[FetchedItem]:
        """搜索仓库"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_gh,
                                            ["gh", "search", "repos", query, "--sort", "stars", "--json",
                                             "name,description,stargazersCount,url,updatedAt", "--limit", "20"])

        if not result:
            raise RuntimeError(f"gh search returned empty for {query}")

        results = result if isinstance(result, list) else [result]
        items = []
        for r in results:
            items.append(FetchedItem(
                source_name=source_name or "GitHub Search", source_url=f"https://github.com/search?q={query}",
                title=f"⭐{r.get('stargazersCount', 0)} {r.get('name', '')}: {r.get('description', '')}",
                url=r.get("url", ""),
                summary=r.get("description", "")[:500],
                published=r.get("updatedAt", ""),
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _run_gh(cmd: list) -> dict | list:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception as e:
            logger.warning(f"gh CLI failed: {e}")
        return {}


# ── Tool 2: GitHub REST API ──────────────────────────────────

class GitHubAPITool(BaseTool):
    """GitHub REST API — 直接 HTTP 请求"""
    name = "github_api"
    description = "GitHub REST API 直接调用（无需 gh CLI）"
    speed = "★★★★☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        import re, httpx
        m = re.search(r"github\.com/([^/]+/[^/]+)", url)
        if not m:
            raise ValueError(f"Cannot extract repo from {url}")
        repo = m.group(1).rstrip("/")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "SignalCollector/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        return [FetchedItem(
            source_name=source_name or "GitHub", source_url=url,
            title=f"{data.get('full_name', repo)}: {data.get('description', '')}",
            url=data.get("html_url", url),
            summary=data.get("description", "")[:500],
            published=data.get("updated_at", ""),
            fetch_method=self.name, fetch_depth=depth.value,
            extra={"stars": data.get("stargazers_count"), "language": data.get("language")},
        )]


# ── GitHub Channel ────────────────────────────────────────────

class GitHubChannel(BaseChannel):
    """
    GitHub 渠道

    降级链: gh CLI → GitHub REST API → Jina Reader
    """
    name = "github"
    description = "GitHub 仓库/搜索采集"
    tools = [GhCliTool, GitHubAPITool, JinaReaderTool]


register_channel(GitHubChannel())
