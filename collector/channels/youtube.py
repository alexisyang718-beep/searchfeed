"""
youtube.py — YouTube 渠道

默认工具: yt-dlp
可替换为: YouTube API、Whisper 转录……
"""

import asyncio
import json
import subprocess

from .base import (
    BaseTool, BaseChannel, FetchDepth, FetchedItem,
    get_env, logger, register_channel,
)
from .web import XReaderTool


# ── Tool 1: yt-dlp ───────────────────────────────────────────

class YtDlpTool(BaseTool):
    """yt-dlp — YouTube/视频平台元数据+字幕提取"""
    name = "yt-dlp"
    description = "yt-dlp 命令行工具，提取视频元数据和字幕"
    speed = "★★★☆☆"
    reliability = "★★★★☆"

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        loop = asyncio.get_event_loop()
        meta = await loop.run_in_executor(None, self._get_metadata, url)

        if not meta:
            raise RuntimeError(f"yt-dlp returned empty for {url}")

        title = meta.get("title", source_name)
        description = meta.get("description", "")
        uploader = meta.get("uploader", meta.get("channel", ""))
        upload_date = meta.get("upload_date", "")

        content = ""
        if depth == FetchDepth.FULL_TEXT:
            # 尝试获取字幕
            subtitles = await loop.run_in_executor(None, self._get_subtitles, url)
            content = subtitles or description

        return [FetchedItem(
            source_name=source_name or "YouTube", source_url=url,
            title=title, url=url,
            content=content[:80000] if depth == FetchDepth.FULL_TEXT else "",
            summary=description[:500],
            published=upload_date,
            author=uploader,
            fetch_method=self.name, fetch_depth=depth.value,
            extra={"duration": meta.get("duration"), "view_count": meta.get("view_count")},
        )]

    @staticmethod
    def _get_metadata(url: str) -> dict:
        try:
            result = subprocess.run(
                ["yt-dlp", "--dump-json", "--no-download", url],
                capture_output=True, text=True, timeout=30,
                env=get_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception as e:
            logger.warning(f"yt-dlp metadata failed for {url}: {e}")
        return {}

    @staticmethod
    def _get_subtitles(url: str) -> str:
        try:
            result = subprocess.run(
                ["yt-dlp", "--write-auto-sub", "--sub-lang", "en,zh-Hans",
                 "--skip-download", "--sub-format", "srt",
                 "--output", "/tmp/yt_sub_%(id)s", url],
                capture_output=True, text=True, timeout=60,
                env=get_env(),
            )
            # 尝试读取字幕文件
            import glob
            srt_files = glob.glob("/tmp/yt_sub_*.srt") + glob.glob("/tmp/yt_sub_*.vtt")
            if srt_files:
                with open(srt_files[0], "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"yt-dlp subtitles failed for {url}: {e}")
        return ""


# ── YouTube Channel ───────────────────────────────────────────

class YouTubeChannel(BaseChannel):
    """
    YouTube 渠道

    降级链: yt-dlp → x-reader
    """
    name = "youtube"
    description = "YouTube 视频元数据+字幕采集"
    tools = [YtDlpTool, XReaderTool]


register_channel(YouTubeChannel())
