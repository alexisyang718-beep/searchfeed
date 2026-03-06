"""
bilibili.py — B站渠道

默认工具: yt-dlp (也支持 B站)
可替换为: bilibili-api、x-reader……
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .youtube import YtDlpTool
from .web import XReaderTool


# ── Tool: yt-dlp (B站模式) ───────────────────────────────────

# yt-dlp 本身就支持 B站，直接复用 YtDlpTool


# ── Tool 2: bilibili-api ─────────────────────────────────────

class BilibiliAPITool(BaseTool):
    """bilibili-api — B站 Python API（需安装 bilibili-api-python）"""
    name = "bilibili_api"
    description = "bilibili-api-python SDK，B站视频/UP主/弹幕采集"
    speed = "★★★★☆"
    reliability = "★★★☆☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        import re
        # 提取 BV 号
        m = re.search(r"(BV\w+)", url)
        if not m:
            raise ValueError(f"Cannot extract BV id from {url}")
        bvid = m.group(1)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._fetch_video, bvid)

        if not result:
            raise RuntimeError(f"bilibili_api returned empty for {bvid}")

        return [FetchedItem(
            source_name=source_name or "B站", source_url=url,
            title=result.get("title", ""),
            url=f"https://www.bilibili.com/video/{bvid}",
            content=result.get("desc", "")[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=result.get("desc", "")[:500],
            published=result.get("pubdate", ""),
            author=result.get("owner", {}).get("name", ""),
            fetch_method=self.name, fetch_depth=depth.value,
            extra={"view": result.get("stat", {}).get("view"), "bvid": bvid},
        )]

    @staticmethod
    def _fetch_video(bvid: str) -> dict:
        """通过 bilibili-api 获取视频信息"""
        script = f'''
import asyncio, json
try:
    from bilibili_api import video
    v = video.Video(bvid="{bvid}")
    info = asyncio.run(v.get_info())
    print(json.dumps(info, ensure_ascii=False))
except ImportError:
    import urllib.request
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    req = urllib.request.Request(url, headers={{"User-Agent": "Mozilla/5.0"}})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        if data.get("code") == 0:
            print(json.dumps(data["data"], ensure_ascii=False))
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
            logger.warning(f"bilibili_api failed for {bvid}: {e}")
        return {}


# ── Bilibili Channel ─────────────────────────────────────────

class BilibiliChannel(BaseChannel):
    """
    B站渠道

    降级链: yt-dlp → bilibili-api → x-reader
    """
    name = "bilibili"
    description = "B站视频/UP主采集"
    tools = [YtDlpTool, BilibiliAPITool, XReaderTool]


register_channel(BilibiliChannel())
