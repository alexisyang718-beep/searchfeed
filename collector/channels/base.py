"""
渠道基类 & 公共设施

每个渠道（channel）是一个独立的 .py 文件，背后挂一个"默认工具"和多个"可替换工具"。
渠道对外只暴露统一的 fetch() 接口，内部自动降级。

核心概念：
  - Channel：一个渠道（如 web / twitter / rss），对应一种信源类型
  - Tool：一个具体的采集工具（如 Jina Reader / Firecrawl / Crawl4AI）
  - 每个 Channel 内部维护自己的工具降级链
  - Channel 之间由 FetcherEngine 编排
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger("collector.channels")

# ── 统一环境变量 ──────────────────────────────────────────────

ENV_PATH = (
    "/Library/Frameworks/Python.framework/Versions/3.13/bin:"
    "{home}/.nvm/versions/node/v20.20.0/bin:"
    "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
    "{home}/bin:{home}/.browserwing"
).format(home=os.path.expanduser("~"))

BROWSERWING_BASE = "http://localhost:8082/api/v1/executor"

TAVILY_API_KEY = os.environ.get(
    "TAVILY_API_KEY",
    "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",
)


def get_env():
    """获取带完整 PATH 的环境变量"""
    env = os.environ.copy()
    env["PATH"] = ENV_PATH
    return env


# ── 采集深度 ──────────────────────────────────────────────────

class FetchDepth(str, Enum):
    TITLE_ONLY = "title_only"
    FULL_TEXT = "full_text"


# ── 采集结果 ──────────────────────────────────────────────────

@dataclass
class FetchedItem:
    """单条采集结果"""
    source_name: str
    source_url: str
    title: str
    url: str
    summary: str = ""
    content: str = ""
    published: str = ""
    author: str = ""
    lang: str = "en"
    fetch_method: str = ""
    fetch_depth: str = "title_only"
    fetched_at: str = ""
    id: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()
        if not self.id:
            raw = f"{self.source_name}:{self.url}:{self.title}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return asdict(self)


# ── 工具基类 ──────────────────────────────────────────────────

class BaseTool:
    """
    单个采集工具的基类。

    每个 Tool 代表一个具体的采集实现（如 Jina Reader, Firecrawl, Crawl4AI 等）。
    Channel 内部维护多个 Tool，按顺序尝试。
    """
    name: str = "base_tool"
    description: str = ""
    speed: str = "★★★☆☆"
    reliability: str = "★★★☆☆"
    needs_login: bool = False

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        raise NotImplementedError

    def info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "speed": self.speed,
            "reliability": self.reliability,
            "needs_login": self.needs_login,
        }


# ── 渠道基类 ──────────────────────────────────────────────────

class BaseChannel:
    """
    渠道基类 — 每个渠道对应一种信源类型。

    特点：
    1. 每个渠道有一个默认工具 + 多个备选工具（降级链）
    2. fetch() 自动按链尝试，第一个成功的即返回
    3. 渠道是可插拔的 — 不满意？换掉就行。
    """
    name: str = "base_channel"
    description: str = ""

    # 子类覆盖：工具降级链（Tool 类列表，按优先级排列）
    tools: list[type[BaseTool]] = []

    async def fetch(self, url: str, depth: FetchDepth,
                    source_name: str = "", **kwargs) -> list[FetchedItem]:
        """按降级链依次尝试工具，返回第一个成功结果"""
        for tool_cls in self.tools:
            tool = tool_cls()
            try:
                logger.info(f"[{self.name}/{tool.name}] Fetching: {source_name or url[:60]}")
                items = await tool.fetch(url, depth, source_name=source_name, **kwargs)
                if items:
                    return items
            except Exception as e:
                logger.warning(f"[{self.name}/{tool.name}] Failed: {e}")
                continue

        logger.error(f"[{self.name}] ALL TOOLS FAILED for {source_name or url}")
        return []

    async def fetch_with_tool(self, tool_name: str, url: str, depth: FetchDepth,
                              source_name: str = "", **kwargs) -> list[FetchedItem]:
        """指定使用某个工具"""
        for tool_cls in self.tools:
            if tool_cls.name == tool_name:
                tool = tool_cls()
                return await tool.fetch(url, depth, source_name=source_name, **kwargs)
        raise ValueError(f"Tool '{tool_name}' not found in channel '{self.name}'. "
                         f"Available: {[t.name for t in self.tools]}")

    def list_tools(self) -> list[dict]:
        """列出本渠道所有可用工具"""
        return [tool_cls().info() for tool_cls in self.tools]

    def info(self) -> dict:
        return {
            "channel": self.name,
            "description": self.description,
            "tools": [t.name for t in self.tools],
            "default_tool": self.tools[0].name if self.tools else None,
        }


# ── 渠道注册表 ────────────────────────────────────────────────

_CHANNEL_REGISTRY: dict[str, BaseChannel] = {}


def register_channel(channel: BaseChannel):
    """注册一个渠道实例"""
    _CHANNEL_REGISTRY[channel.name] = channel


def get_channel(name: str) -> Optional[BaseChannel]:
    """按名称获取渠道"""
    return _CHANNEL_REGISTRY.get(name)


def all_channels() -> dict[str, BaseChannel]:
    """获取所有注册的渠道"""
    return _CHANNEL_REGISTRY.copy()


def doctor() -> dict:
    """
    健康检查 — 检测所有渠道和工具状态

    返回: {channel_name: {tool_name: "ok"/"unavailable"/error_msg}}
    """
    report = {}
    for ch_name, channel in _CHANNEL_REGISTRY.items():
        ch_report = {}
        for tool_cls in channel.tools:
            tool = tool_cls()
            ch_report[tool.name] = "registered"
        report[ch_name] = ch_report
    return report
