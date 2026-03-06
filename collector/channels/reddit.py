"""
reddit.py — Reddit 渠道

默认工具: JSON API + Exa
可替换为: PRAW、Pushshift……
"""

import asyncio
import json
import subprocess

import httpx

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .web import JinaReaderTool


# ── Tool 1: Reddit JSON API ──────────────────────────────────

class RedditJSONTool(BaseTool):
    """Reddit JSON API — 免费无需认证，URL + .json"""
    name = "reddit_json"
    description = "Reddit 原生 JSON API（URL 加 .json 后缀）"
    speed = "★★★★☆"
    reliability = "★★★☆☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        # 确保 URL 指向 .json 端点
        json_url = url.rstrip("/") + ".json" if not url.endswith(".json") else url

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(json_url, headers={
                "User-Agent": "SignalCollector/1.0 (research bot)",
            })
            resp.raise_for_status()
            data = resp.json()

        items = []
        # Reddit 返回数组（listing + comments）
        if isinstance(data, list):
            listing = data[0] if data else {}
        elif isinstance(data, dict):
            listing = data
        else:
            return []

        children = listing.get("data", {}).get("children", [])
        for child in children[:30]:
            post = child.get("data", {})
            if not post.get("title"):
                continue

            selftext = post.get("selftext", "")
            items.append(FetchedItem(
                source_name=source_name or f"r/{post.get('subreddit', 'reddit')}",
                source_url=url,
                title=post.get("title", ""),
                url=f"https://reddit.com{post.get('permalink', '')}",
                content=selftext[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=selftext[:500] if selftext else post.get("title", ""),
                published=str(post.get("created_utc", "")),
                author=post.get("author", ""),
                fetch_method=self.name, fetch_depth=depth.value,
                extra={"score": post.get("score"), "num_comments": post.get("num_comments")},
            ))
        return items


# ── Tool 2: PRAW ─────────────────────────────────────────────

class PRAWTool(BaseTool):
    """PRAW — Python Reddit API Wrapper"""
    name = "praw"
    description = "PRAW 官方 Python SDK（需 Reddit API credentials）"
    speed = "★★★★☆"
    reliability = "★★★★☆"
    needs_login = True

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        import re
        # 提取 subreddit
        m = re.search(r"/r/(\w+)", url)
        subreddit_name = m.group(1) if m else ""
        if not subreddit_name:
            raise ValueError(f"Cannot extract subreddit from {url}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._fetch_praw, subreddit_name)

        if not result:
            raise RuntimeError(f"PRAW returned empty for r/{subreddit_name}")

        items = []
        for post in result:
            items.append(FetchedItem(
                source_name=source_name or f"r/{subreddit_name}",
                source_url=url,
                title=post.get("title", ""),
                url=f"https://reddit.com{post.get('permalink', '')}",
                content=post.get("selftext", "")[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=post.get("selftext", "")[:500] or post.get("title", ""),
                published=str(post.get("created_utc", "")),
                author=post.get("author", ""),
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _fetch_praw(subreddit_name: str) -> list:
        script = f'''
import json, os, praw
reddit = praw.Reddit(
    client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
    client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
    user_agent="SignalCollector/1.0",
)
sub = reddit.subreddit("{subreddit_name}")
posts = []
for post in sub.hot(limit=20):
    posts.append({{"title": post.title, "selftext": post.selftext[:5000],
                   "permalink": post.permalink, "author": str(post.author),
                   "created_utc": post.created_utc, "score": post.score}})
print(json.dumps(posts, ensure_ascii=False))
'''
        try:
            result = subprocess.run(
                ["python3", "-c", script],
                capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception as e:
            logger.warning(f"PRAW failed for r/{subreddit_name}: {e}")
        return []


# ── Tool 3: Exa Search (Reddit) ─────────────────────────────

class ExaRedditTool(BaseTool):
    """Exa AI 搜索 — 聚焦 Reddit 内容"""
    name = "exa_reddit"
    description = "Exa AI 语义搜索 Reddit 内容（mcporter）"
    speed = "★★★☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", query: str = "", **kwargs) -> list[FetchedItem]:
        if not query:
            import re
            m = re.search(r"/r/(\w+)", url)
            query = m.group(1) if m else source_name

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._search_exa, query)

        if not result:
            raise RuntimeError(f"Exa Reddit search returned empty for {query}")

        items = []
        for r in (result if isinstance(result, list) else [result]):
            items.append(FetchedItem(
                source_name=source_name or "Reddit/Exa", source_url=url,
                title=r.get("title", ""), url=r.get("url", ""),
                content=r.get("text", "")[:80000] if depth == FetchDepth.FULL_TEXT else "",
                summary=r.get("text", "")[:500],
                fetch_method=self.name, fetch_depth=depth.value,
            ))
        return items

    @staticmethod
    def _search_exa(query: str) -> list:
        try:
            cmd = f"""mcporter call 'exa.web_search_exa(query: "site:reddit.com {query}", numResults: 10)'"""
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"Exa Reddit search failed: {e}")
        return []


# ── Reddit Channel ────────────────────────────────────────────

class RedditChannel(BaseChannel):
    """
    Reddit 渠道

    降级链: Reddit JSON API → PRAW → Exa Reddit → Jina Reader
    """
    name = "reddit"
    description = "Reddit 帖子/subreddit 采集"
    tools = [RedditJSONTool, PRAWTool, ExaRedditTool, JinaReaderTool]


register_channel(RedditChannel())
