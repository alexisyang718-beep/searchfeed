"""
channels/ — 可插拔渠道架构

🔌 每个渠道都是可插拔的
每个平台背后是一个独立的上游工具。不满意？换掉就行。

channels/
├── web.py          → Jina Reader      ← 可以换成 Firecrawl、Crawl4AI……
├── twitter.py      → xreach           ← 可以换成 Nitter、官方 API……
├── youtube.py      → yt-dlp           ← 可以换成 YouTube API、Whisper……
├── github.py       → gh CLI           ← 可以换成 REST API、PyGitHub……
├── bilibili.py     → yt-dlp           ← 可以换成 bilibili-api……
├── reddit.py       → JSON API + Exa   ← 可以换成 PRAW、Pushshift……
├── xiaohongshu.py  → mcporter MCP     ← 可以换成其他 XHS 工具……
├── douyin.py       → mcporter MCP     ← 可以换成其他抖音工具……
├── linkedin.py     → linkedin-mcp     ← 可以换成 LinkedIn API……
├── bosszp.py       → mcp-bosszp       ← 可以换成其他招聘工具……
├── rss.py          → feedparser       ← 可以换成 atoma……
├── exa_search.py   → mcporter MCP     ← 可以换成 Tavily、SerpAPI……
├── api.py          → httpx            ← JSON API 直接请求
├── browser.py      → nodriver+BrowserWing ← 最后防线（浏览器自动化）
└── __init__.py     → 渠道注册 (doctor 检测用)
"""

# 导入所有渠道模块（触发 register_channel）
from . import web          # noqa: F401
from . import rss          # noqa: F401
from . import twitter      # noqa: F401
from . import youtube      # noqa: F401
from . import github       # noqa: F401
from . import bilibili     # noqa: F401
from . import reddit       # noqa: F401
from . import xiaohongshu  # noqa: F401
from . import douyin       # noqa: F401
from . import linkedin     # noqa: F401
from . import bosszp       # noqa: F401
from . import exa_search   # noqa: F401
from . import api          # noqa: F401
from . import browser      # noqa: F401

# 导出公共接口
from .base import (
    BaseChannel,
    BaseTool,
    FetchDepth,
    FetchedItem,
    all_channels,
    doctor,
    get_channel,
    register_channel,
)

__all__ = [
    "BaseChannel", "BaseTool", "FetchDepth", "FetchedItem",
    "all_channels", "doctor", "get_channel", "register_channel",
]
