"""
web.py — 通用网页爬取渠道

默认工具: Jina Reader
可替换为: Firecrawl、Crawl4AI、x-reader、httpx、nodriver、tavily_extract

这是最通用的渠道，适合任意网页内容抓取。
"""

import asyncio
import json
import os
import re
import subprocess

import httpx

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel, TAVILY_API_KEY,
)


# ── Tool 1: Jina Reader ──────────────────────────────────────

class JinaReaderTool(BaseTool):
    """Jina Reader — 网页转干净 Markdown（云端 API）"""
    name = "jina_reader"
    description = "Jina Reader 云端服务，将网页转为干净 Markdown"
    speed = "★★★☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        jina_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers={
                "Accept": "text/markdown",
                "User-Agent": "SignalCollector/1.0",
            })
            resp.raise_for_status()
            md = resp.text

        title = source_name
        m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
        if m:
            title = m.group(1).strip()

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title, url=url,
            content=md[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=md[:500] if depth == FetchDepth.TITLE_ONLY else "",
            fetch_method=self.name, fetch_depth=depth.value,
        )]


# ── Tool 2: Firecrawl ────────────────────────────────────────

class FirecrawlTool(BaseTool):
    """Firecrawl — 高级网页爬虫，自动处理 JS 渲染和反爬"""
    name = "firecrawl"
    description = "Firecrawl 云端/自部署爬虫，自动 JS 渲染，输出 Markdown"
    speed = "★★★☆☆"
    reliability = "★★★★★"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "")

        if api_key:
            return await self._fetch_cloud(url, depth, source_name, api_key)
        else:
            return await self._fetch_local(url, depth, source_name)

    async def _fetch_cloud(self, url: str, depth: FetchDepth,
                           source_name: str, api_key: str) -> list[FetchedItem]:
        """使用 Firecrawl 云端 API"""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"url": url, "formats": ["markdown"]},
            )
            resp.raise_for_status()
            data = resp.json()

        result = data.get("data", {})
        md = result.get("markdown", "")
        title = result.get("metadata", {}).get("title", source_name)

        if not md:
            raise RuntimeError(f"Firecrawl returned empty for {url}")

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title, url=url,
            content=md[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=md[:500] if depth == FetchDepth.TITLE_ONLY else "",
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    async def _fetch_local(self, url: str, depth: FetchDepth,
                           source_name: str) -> list[FetchedItem]:
        """使用本地 firecrawl-py SDK（无 API key 时）"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_firecrawl_sdk, url)

        if not result:
            raise RuntimeError(f"Firecrawl SDK returned empty for {url}")

        title = result.get("title", source_name)
        md = result.get("markdown", "")

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title, url=url,
            content=md[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=md[:500] if depth == FetchDepth.TITLE_ONLY else "",
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    @staticmethod
    def _run_firecrawl_sdk(url: str) -> dict:
        script = f'''
import json
from firecrawl import FirecrawlApp
app = FirecrawlApp(api_url="https://api.firecrawl.dev")
result = app.scrape_url("{url}", params={{"formats": ["markdown"]}})
if result:
    md = result.get("markdown", "") if isinstance(result, dict) else getattr(result, "markdown", "")
    title = ""
    if isinstance(result, dict):
        title = result.get("metadata", {{}}).get("title", "")
    print(json.dumps({{"title": title, "markdown": md[:80000]}}))
'''
        try:
            result = subprocess.run(
                ["python3", "-c", script],
                capture_output=True, text=True, timeout=60,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Firecrawl SDK failed for {url}: {e}")
        return {}


# ── Tool 3: Crawl4AI ─────────────────────────────────────────

class Crawl4AITool(BaseTool):
    """Crawl4AI — LLM-friendly 开源爬虫，反爬能力强"""
    name = "crawl4ai"
    description = "Crawl4AI 开源智能爬虫，JS 渲染，输出 Markdown"
    speed = "★★★☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_crawl4ai, url)

        if not result:
            raise RuntimeError(f"crawl4ai returned empty for {url}")

        title = source_name
        m = re.search(r"^#\s+(.+)$", result, re.MULTILINE)
        if m:
            title = m.group(1).strip()

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title, url=url,
            content=result[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=result[:500] if depth == FetchDepth.TITLE_ONLY else "",
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    @staticmethod
    def _run_crawl4ai(url: str) -> str:
        script = f'''
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

async def main():
    config = CrawlerRunConfig(
        word_count_threshold=10,
        excluded_tags=["nav", "footer", "header"],
        remove_overlay_elements=True,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="{url}", config=config)
        if result.success:
            print(result.markdown_v2.raw_markdown if hasattr(result, 'markdown_v2') else result.markdown)
        else:
            raise RuntimeError(result.error_message)

asyncio.run(main())
'''
        try:
            result = subprocess.run(
                ["python3", "-c", script],
                capture_output=True, text=True, timeout=60,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            if result.stderr:
                logger.warning(f"crawl4ai stderr: {result.stderr[:200]}")
        except Exception as e:
            logger.warning(f"crawl4ai failed for {url}: {e}")
        return ""


# ── Tool 4: x-reader ─────────────────────────────────────────

class XReaderTool(BaseTool):
    """x-reader — 多平台内容阅读器（微信/X/小红书/Telegram/YouTube/B站/RSS/网页）"""
    name = "x-reader"
    description = "多平台阅读器，支持微信/X/小红书/Telegram/YouTube/B站等"
    speed = "★★★★☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_xreader, url)

        if not result:
            raise RuntimeError(f"x-reader returned empty for {url}")

        md = result
        title = source_name
        m_title = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
        if m_title:
            title = m_title.group(1).strip()

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title, url=url,
            content=md[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=md[:500] if depth == FetchDepth.TITLE_ONLY else "",
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    @staticmethod
    def _run_xreader(url: str) -> str:
        try:
            result = subprocess.run(
                ["x-reader", url],
                capture_output=True, text=True, timeout=60,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"x-reader failed for {url}: {e}")
        return ""


# ── Tool 5: httpx (通用网页) ─────────────────────────────────

class HttpxTool(BaseTool):
    """httpx — 最简单的网页抓取（无 JS 渲染）"""
    name = "httpx_web"
    description = "httpx 简单网页抓取，无 JS 渲染，速度最快"
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


# ── Tool 6: Tavily Extract ───────────────────────────────────

class TavilyExtractTool(BaseTool):
    """Tavily Extract — 高级内容提取 API"""
    name = "tavily_extract"
    description = "Tavily 高级内容提取，付费 API，质量最高"
    speed = "★★★☆☆"
    reliability = "★★★★★"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        if not TAVILY_API_KEY:
            raise RuntimeError("TAVILY_API_KEY not set")

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.tavily.com/extract",
                json={"urls": [url], "api_key": TAVILY_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        items = []
        for r in results:
            items.append(FetchedItem(
                source_name=source_name, source_url=url,
                title=r.get("title", source_name),
                url=r.get("url", url),
                content=r.get("raw_content", "")[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=r.get("raw_content", "")[:500] if depth == FetchDepth.TITLE_ONLY else "",
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        if not items:
            raise RuntimeError(f"tavily_extract returned no results for {url}")
        return items


# ── Web Channel ───────────────────────────────────────────────

class WebChannel(BaseChannel):
    """
    通用网页爬取渠道

    降级链: x-reader → Jina Reader → Firecrawl → Crawl4AI → Tavily Extract → httpx
    """
    name = "web"
    description = "通用网页爬取，支持 6 个工具自动降级"
    tools = [XReaderTool, JinaReaderTool, FirecrawlTool, Crawl4AITool, TavilyExtractTool, HttpxTool]


# 注册
register_channel(WebChannel())
