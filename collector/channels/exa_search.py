"""
exa_search.py — Exa AI 搜索渠道

默认工具: mcporter MCP (Exa)
可替换为: Tavily Search、SerpAPI……
"""

import asyncio
import json
import subprocess
import re

import httpx

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel, TAVILY_API_KEY,
)


# ── Tool 1: Exa AI 搜索 (mcporter) ──────────────────────────

class ExaMcporterTool(BaseTool):
    """Exa AI — 语义搜索（Agent Reach mcporter）"""
    name = "exa_mcporter"
    description = "Exa AI 语义搜索（mcporter MCP），适合公司/代码/学术搜索"
    speed = "★★★☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "", **kwargs) -> list[FetchedItem]:
        if not query:
            query = source_name

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_exa, query)

        if not result:
            raise RuntimeError(f"exa search returned empty for {query}")

        items = []
        for r in (result if isinstance(result, list) else [result]):
            items.append(FetchedItem(
                source_name=source_name or "Exa Search", source_url=url,
                title=r.get("title", ""), url=r.get("url", ""),
                content=r.get("text", "")[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=r.get("text", "")[:500] if depth == FetchDepth.TITLE_ONLY else "",
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _run_exa(query: str, num_results: int = 10) -> list:
        try:
            cmd = f"""mcporter call 'exa.web_search_exa(query: "{query}", numResults: {num_results})'"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"exa search failed: {e}")
        return []


# ── Tool 2: Tavily Search ────────────────────────────────────

class TavilySearchTool(BaseTool):
    """Tavily Search — 高质量网络搜索"""
    name = "tavily_search"
    description = "Tavily 网络搜索 API，付费但质量最高"
    speed = "★★★★☆"
    reliability = "★★★★★"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "", **kwargs) -> list[FetchedItem]:
        if not query:
            query = source_name

        search_depth = "advanced" if depth == FetchDepth.FULL_TEXT else "basic"
        include_raw = depth == FetchDepth.FULL_TEXT

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "search_depth": search_depth,
                    "include_raw_content": include_raw,
                    "max_results": 10,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items = []
        for r in data.get("results", []):
            items.append(FetchedItem(
                source_name=source_name or "Tavily Search", source_url=url,
                title=r.get("title", ""), url=r.get("url", ""),
                content=r.get("raw_content", r.get("content", ""))[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=r.get("content", "")[:500],
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        if not items:
            raise RuntimeError(f"tavily_search returned no results for {query}")
        return items


# ── Tool 3: Multi-Search Engine ──────────────────────────────

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={keyword}",
    "baidu": "https://www.baidu.com/s?wd={keyword}",
    "wechat": "https://wx.sogou.com/weixin?type=2&query={keyword}",
    "bing_cn": "https://cn.bing.com/search?q={keyword}&ensearch=0",
    "duckduckgo": "https://duckduckgo.com/html/?q={keyword}",
    "toutiao": "https://so.toutiao.com/search?keyword={keyword}",
}


class MultiSearchTool(BaseTool):
    """Multi-Search Engine — 多搜索引擎（Google/百度/微信/头条等）"""
    name = "multi_search"
    description = "多搜索引擎 URL 模板搜索，适合国内搜索/微信搜索"
    speed = "★★★☆☆"
    reliability = "★★★☆☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "",
                    engines: list[str] = None, **kwargs) -> list[FetchedItem]:
        if not query:
            query = source_name
        if not engines:
            engines = ["baidu", "wechat", "google"]

        items = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for engine_name in engines:
                template = SEARCH_ENGINES.get(engine_name)
                if not template:
                    continue
                search_url = template.format(keyword=query)
                try:
                    resp = await client.get(search_url, headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    })
                    if resp.status_code == 200:
                        parsed = self._parse_results(resp.text, engine_name, query, source_name)
                        items.extend(parsed)
                except Exception as e:
                    logger.warning(f"multi_search {engine_name} failed for {query}: {e}")

        if not items:
            raise RuntimeError(f"multi_search returned no results for {query}")
        return items

    def _parse_results(self, html: str, engine: str, query: str, source_name: str) -> list[FetchedItem]:
        items = []
        if engine == "baidu":
            pattern = r'<h3[^>]*class="[^"]*t[^"]*"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        elif engine == "wechat":
            pattern = r'<h3>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        elif engine == "google":
            pattern = r'<h3[^>]*>(.*?)</h3>.*?<a[^>]*href="([^"]*)"'
        else:
            pattern = r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'

        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        for match in matches[:15]:
            if engine == "google":
                title, link = match
            else:
                link, title = match

            title = re.sub(r'<[^>]+>', '', title).strip()
            if not title or len(title) < 5:
                continue

            items.append(FetchedItem(
                source_name=source_name or f"搜索:{engine}",
                source_url=f"search://{engine}?q={query}",
                title=title[:200], url=link,
                summary=f"[{engine}] {title}",
                fetch_method=f"multi_search:{engine}", fetch_depth="title_only",
            ))
        return items


# ── Exa Search Channel ───────────────────────────────────────

class ExaSearchChannel(BaseChannel):
    """
    搜索补充渠道

    降级链: Tavily Search → Exa AI (mcporter) → Multi-Search Engine
    """
    name = "exa_search"
    description = "搜索补充（Tavily/Exa/多引擎）"
    tools = [TavilySearchTool, ExaMcporterTool, MultiSearchTool]


register_channel(ExaSearchChannel())
