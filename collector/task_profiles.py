"""
任务调度层 — Task Profiles

职责：
1. 定义不同用途的"任务档案"（Profile）
2. 每个 Profile 决定：选哪些信源、用什么深度采集、后处理策略
3. 对外提供统一接口：run_profile(profile_name)

预置 Profile：
  - quick_scan:    快速资讯扫描（15分钟内完成，只要标题）
  - daily_digest:  每日简报（Tier 1-2，标题+摘要）
  - deep_research: 深度研究/月报（全信源全文，按主题过滤）
  - topic_focus:   专题分析（指定主题关键词，相关信源全文）
  - signal_brief:  Signal Brief 专用（核心源全文 + 辅助源标题）
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .source_manager import SourceManager
from .fetcher_engine import FetcherEngine, FetchDepth, FetchedItem

logger = logging.getLogger("collector.task")


@dataclass
class ProfileConfig:
    """任务档案配置"""
    name: str
    description: str

    # 信源筛选
    tiers: Optional[list[int]] = None              # 允许的 tier
    category_ids: Optional[list[str]] = None       # 只包含这些类目
    exclude_category_ids: Optional[list[str]] = None  # 排除这些类目
    max_priority: Optional[int] = None             # 最大 priority
    langs: Optional[list[str]] = None              # 语言过滤

    # 采集行为
    fetch_depth: FetchDepth = FetchDepth.TITLE_ONLY
    max_sources: Optional[int] = None              # 最多采集多少个源
    concurrency: int = 10                          # 并发数
    rate_limit: float = 0.2                        # 限速

    # 后处理
    dedup: bool = True                             # 去重
    sort_by: str = "published"                     # 排序字段
    max_items: Optional[int] = None                # 最多保留条目数
    keyword_filter: Optional[list[str]] = None     # 关键词过滤（标题/摘要含关键词才保留）

    # 输出
    output_format: str = "json"                    # json / markdown / html
    output_file: Optional[str] = None              # 输出路径


# ── 预置 Profile ──────────────────────────────────────────────

PROFILES: dict[str, ProfileConfig] = {

    "quick_scan": ProfileConfig(
        name="quick_scan",
        description="快速资讯扫描：5分钟内完成，只抓 Tier 1 priority 1 的 RSS 源标题",
        tiers=[1],
        max_priority=1,
        fetch_depth=FetchDepth.TITLE_ONLY,
        exclude_category_ids=["tier_special_gaming", "karpathy_picks"],
        concurrency=20,
        max_items=100,
        dedup=True,
        output_format="json",
    ),

    "daily_digest": ProfileConfig(
        name="daily_digest",
        description="每日简报：Tier 1-2 所有源，标题+摘要模式，排除游戏专题",
        tiers=[1, 2],
        max_priority=3,
        fetch_depth=FetchDepth.TITLE_ONLY,
        exclude_category_ids=["tier_special_gaming"],
        concurrency=15,
        max_items=200,
        dedup=True,
        output_format="json",
    ),

    "deep_research": ProfileConfig(
        name="deep_research",
        description="深度研究/月报：全 Tier 全信源，全文采集模式",
        tiers=[1, 2, 3, 4],
        fetch_depth=FetchDepth.FULL_TEXT,
        concurrency=8,  # 全文模式降低并发
        rate_limit=0.5,
        dedup=True,
        output_format="json",
    ),

    "topic_focus": ProfileConfig(
        name="topic_focus",
        description="专题分析：根据关键词过滤相关信源和内容，全文采集",
        tiers=[1, 2, 3],
        fetch_depth=FetchDepth.FULL_TEXT,
        concurrency=8,
        rate_limit=0.5,
        dedup=True,
        # keyword_filter 和 exclude_category_ids 在运行时动态设置
        output_format="json",
    ),

    "signal_brief": ProfileConfig(
        name="signal_brief",
        description="Signal Brief：核心源(Tier 1, priority 1-2)全文 + 辅助源(Tier 2)标题",
        tiers=[1, 2],
        max_priority=3,
        exclude_category_ids=["karpathy_picks"],
        fetch_depth=FetchDepth.FULL_TEXT,  # 核心源全文（辅助源在运行时降级）
        concurrency=10,
        dedup=True,
        output_format="json",
    ),

    "gaming_focus": ProfileConfig(
        name="gaming_focus",
        description="游戏行业专题：游戏信源 + Tier 1-2 AI 源中游戏相关内容",
        category_ids=["tier_special_gaming", "tier1_official", "tier2_intl_media"],
        fetch_depth=FetchDepth.FULL_TEXT,
        keyword_filter=["game", "gaming", "游戏", "NPC", "unity", "unreal",
                        "playstation", "xbox", "nintendo", "steam", "epic"],
        concurrency=8,
        dedup=True,
        output_format="json",
    ),
}


# ── 主题到信源排除的映射 ──────────────────────────────────────

TOPIC_EXCLUSION_MAP = {
    "ai_general": ["tier_special_gaming"],
    "gaming": [],  # 游戏专题不排除任何
    "research": ["tier_special_gaming", "tier4_aggregators"],
    "investment": ["tier_special_gaming", "karpathy_picks"],
    "china_ai": ["tier_special_gaming", "karpathy_picks"],
}


# ── 任务运行器 ────────────────────────────────────────────────

class TaskRunner:
    """
    任务运行器 — 执行 Profile 定义的采集任务

    用法：
        runner = TaskRunner()
        items = await runner.run("daily_digest")
        items = await runner.run("topic_focus", keyword_filter=["agent", "RAG"])
    """

    def __init__(self, sources_file: str = None):
        self.source_mgr = SourceManager(sources_file)
        self._results_dir = Path(__file__).parent.parent / "output"
        self._results_dir.mkdir(exist_ok=True)

    async def run(
        self,
        profile_name: str,
        # 运行时覆盖参数
        keyword_filter: Optional[list[str]] = None,
        exclude_category_ids: Optional[list[str]] = None,
        langs: Optional[list[str]] = None,
        max_items: Optional[int] = None,
        output_file: Optional[str] = None,
        progress_callback=None,
    ) -> list[FetchedItem]:
        """
        执行采集任务

        Args:
            profile_name: 预置 Profile 名称
            keyword_filter: 运行时关键词过滤（覆盖 Profile 默认值）
            exclude_category_ids: 运行时排除类目
            langs: 运行时语言过滤
            max_items: 运行时最大条目数
            output_file: 运行时输出路径
            progress_callback: 进度回调
        """
        if profile_name not in PROFILES:
            raise ValueError(f"Unknown profile: {profile_name}. Available: {list(PROFILES.keys())}")

        profile = PROFILES[profile_name]
        logger.info(f"=== Running profile: {profile.name} — {profile.description} ===")

        # 1. 信源筛选
        sources = self._select_sources(profile, exclude_category_ids, langs)
        if profile.max_sources:
            sources = sources[:profile.max_sources]
        logger.info(f"Selected {len(sources)} sources from {self.source_mgr.total} total")

        # 2. Signal Brief 特殊处理：核心源全文，辅助源标题
        if profile_name == "signal_brief":
            items = await self._run_signal_brief(sources, profile, progress_callback)
        else:
            # 3. 创建引擎并执行
            engine = FetcherEngine(
                concurrency=profile.concurrency,
                rate_limit=profile.rate_limit,
            )
            items = await engine.fetch_batch(sources, profile.fetch_depth, progress_callback)
            logger.info(f"Fetch stats: {engine.stats}")

        # 4. 后处理
        items = self._postprocess(
            items, profile,
            keyword_filter=keyword_filter or profile.keyword_filter,
            max_items=max_items or profile.max_items,
        )
        logger.info(f"After postprocess: {len(items)} items")

        # 5. 输出
        out_path = output_file or profile.output_file
        if out_path:
            self._save(items, out_path, profile.output_format)
        else:
            # 默认输出
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_path = self._results_dir / f"{profile_name}_{ts}.json"
            self._save(items, str(default_path), "json")

        return items

    def _select_sources(self, profile: ProfileConfig, extra_exclude=None, extra_langs=None) -> list:
        """根据 Profile 配置筛选信源"""
        exclude = list(profile.exclude_category_ids or [])
        if extra_exclude:
            exclude.extend(extra_exclude)

        return self.source_mgr.filter(
            tiers=profile.tiers,
            category_ids=profile.category_ids,
            exclude_category_ids=exclude if exclude else None,
            max_priority=profile.max_priority,
            langs=extra_langs or profile.langs,
        )

    async def _run_signal_brief(self, sources: list, profile: ProfileConfig, progress_callback=None) -> list[FetchedItem]:
        """
        Signal Brief 专用：分层采集策略
        - Tier 1 + priority 1-2 → 全文
        - 其他 → 标题+摘要
        """
        core_sources = [s for s in sources if s["_tier"] == 1 and s.get("priority", 5) <= 2]
        aux_sources = [s for s in sources if s not in core_sources]

        logger.info(f"Signal Brief: {len(core_sources)} core (full_text) + {len(aux_sources)} aux (title_only)")

        engine = FetcherEngine(concurrency=profile.concurrency, rate_limit=profile.rate_limit)

        # 并行执行两组
        core_task = engine.fetch_batch(core_sources, FetchDepth.FULL_TEXT)
        aux_task = engine.fetch_batch(aux_sources, FetchDepth.TITLE_ONLY)

        core_items, aux_items = await asyncio.gather(core_task, aux_task)
        logger.info(f"Signal Brief fetch stats: {engine.stats}")

        return core_items + aux_items

    def _postprocess(self, items: list[FetchedItem], profile: ProfileConfig,
                     keyword_filter=None, max_items=None) -> list[FetchedItem]:
        """后处理：去重 → 关键词过滤 → 排序 → 截断"""

        # 去重（按 url）
        if profile.dedup:
            seen = set()
            deduped = []
            for item in items:
                key = item.url or item.title
                if key not in seen:
                    seen.add(key)
                    deduped.append(item)
            items = deduped

        # 关键词过滤
        if keyword_filter:
            keywords = [kw.lower() for kw in keyword_filter]
            items = [
                item for item in items
                if any(
                    kw in item.title.lower() or kw in item.summary.lower() or kw in item.content[:500].lower()
                    for kw in keywords
                )
            ]

        # 排序（按发布时间倒序，无时间的排后面）
        items.sort(key=lambda x: x.published or "0000", reverse=True)

        # 截断
        if max_items:
            items = items[:max_items]

        return items

    def _save(self, items: list[FetchedItem], path: str, fmt: str):
        """保存采集结果"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            data = [item.to_dict() for item in items]
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif fmt == "markdown":
            lines = [f"# 采集结果 ({len(items)} 条)\n",
                     f"生成时间: {datetime.now(timezone.utc).isoformat()}\n\n"]
            for item in items:
                lines.append(f"## {item.title}\n")
                lines.append(f"- 来源: {item.source_name}\n")
                lines.append(f"- URL: {item.url}\n")
                lines.append(f"- 时间: {item.published}\n")
                if item.summary:
                    lines.append(f"- 摘要: {item.summary[:200]}\n")
                lines.append("\n")
            with open(out_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

        logger.info(f"Saved {len(items)} items to {out_path} ({fmt})")

    def list_profiles(self) -> dict:
        """列出所有可用 Profile"""
        return {
            name: {
                "description": p.description,
                "tiers": p.tiers,
                "depth": p.fetch_depth.value,
                "max_priority": p.max_priority,
                "exclude": p.exclude_category_ids,
            }
            for name, p in PROFILES.items()
        }
