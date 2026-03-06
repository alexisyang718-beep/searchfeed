"""
browser.py — 浏览器自动化渠道（最后防线）

默认工具: nodriver (CDP 直连，反检测)
可替换为: BrowserWing（带 Cookie 登录态）

这是其他渠道都失败时的最后一道防线。
"""

import asyncio
import json
import subprocess

import httpx

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel, BROWSERWING_BASE,
)


# ── Tool 1: nodriver ─────────────────────────────────────────

class NodriverTool(BaseTool):
    """nodriver — CDP 直连无头浏览器，反检测能力强"""
    name = "nodriver"
    description = "nodriver 无头浏览器（CDP 直连），反检测，绕 Cloudflare"
    speed = "★★☆☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_nodriver, url, depth.value)

        if not result:
            raise RuntimeError(f"nodriver returned empty for {url}")

        title = result.get("title", source_name)
        content = result.get("content", "")

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title or source_name, url=url,
            content=content[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=content[:500] if depth == FetchDepth.TITLE_ONLY else "",
            fetch_method=self.name, fetch_depth=depth.value,
        )]

    @staticmethod
    def _run_nodriver(url: str, depth: str) -> dict:
        script = f'''
import asyncio
import nodriver as uc
import json

async def main():
    browser = await uc.start(headless=True)
    try:
        page = await browser.get("{url}")
        await page.sleep(3)
        title = await page.evaluate("document.title")
        if "{depth}" == "full_text":
            content = await page.evaluate("document.body.innerText")
        else:
            content = title
        print(json.dumps({{"title": title, "content": content[:80000]}}))
    finally:
        browser.stop()

asyncio.run(main())
'''
        try:
            result = subprocess.run(
                ["python3", "-c", script],
                capture_output=True, text=True, timeout=45,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
            if result.stderr:
                logger.warning(f"nodriver stderr: {result.stderr[:300]}")
        except Exception as e:
            logger.warning(f"nodriver failed for {url}: {e}")
        return {}


# ── Tool 2: BrowserWing ──────────────────────────────────────

class BrowserWingTool(BaseTool):
    """BrowserWing — 浏览器自动化 + Cookie 登录态（最后防线）"""
    name = "browserwing"
    description = "BrowserWing 本地浏览器自动化，带 Cookie 登录态"
    speed = "★★☆☆☆"
    reliability = "★★★★★"
    needs_login = True

    async def _ensure_available(self, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.get(f"{BROWSERWING_BASE}/help", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        async with httpx.AsyncClient(timeout=60) as client:
            if not await self._ensure_available(client):
                raise RuntimeError("BrowserWing not running at localhost:8082")

            for attempt in range(2):
                try:
                    resp = await client.post(
                        f"{BROWSERWING_BASE}/navigate",
                        json={"url": url, "wait_until": "load", "timeout": 30},
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 200:
                        nav_data = resp.json()
                        if nav_data.get("success"):
                            break
                    if attempt == 0:
                        await asyncio.sleep(2)
                except Exception as e:
                    if attempt == 0:
                        await asyncio.sleep(2)
                    else:
                        raise RuntimeError(f"BrowserWing navigate failed: {e}")
            else:
                raise RuntimeError(f"BrowserWing navigate failed after retries for {url}")

            await asyncio.sleep(2)

            title = source_name
            try:
                resp = await client.get(f"{BROWSERWING_BASE}/page-info")
                if resp.status_code == 200:
                    page_info = resp.json()
                    title = page_info.get("data", {}).get("title", source_name) or source_name
            except Exception:
                pass

            content = ""
            if depth == FetchDepth.FULL_TEXT:
                try:
                    resp = await client.get(f"{BROWSERWING_BASE}/page-text")
                    if resp.status_code == 200:
                        page_data = resp.json()
                        content = page_data.get("data", {}).get("text", "")
                except Exception:
                    pass
                if not content:
                    try:
                        resp = await client.get(f"{BROWSERWING_BASE}/page-content")
                        if resp.status_code == 200:
                            page_data = resp.json()
                            content = page_data.get("data", {}).get("content", "")
                    except Exception:
                        pass

        return [FetchedItem(
            source_name=source_name, source_url=url,
            title=title or source_name, url=url,
            content=content[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=title,
            fetch_method=self.name, fetch_depth=depth.value,
        )]


# ── Browser Channel ──────────────────────────────────────────

class BrowserChannel(BaseChannel):
    """
    浏览器自动化渠道（最后防线）

    降级链: nodriver → BrowserWing
    """
    name = "browser"
    description = "浏览器自动化（nodriver + BrowserWing），最后防线"
    tools = [NodriverTool, BrowserWingTool]


register_channel(BrowserChannel())
