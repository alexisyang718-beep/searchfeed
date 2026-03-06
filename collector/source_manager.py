"""
信源管理模块 — Source Manager

职责：
1. 加载/查询 unified_rss_sources.json
2. 支持两种格式：entity-centric（公司/人物多渠道）和 flat（传统单源）
3. 按 tier / category / priority / lang / entity / platform 筛选信源
4. 为不同任务 Profile 提供信源子集
"""

import json
from pathlib import Path
from typing import Optional


class SourceManager:
    """统一信源管理器 — 支持 entity-centric + flat 混合格式"""

    def __init__(self, sources_file: str = None):
        if sources_file is None:
            sources_file = str(Path(__file__).parent.parent / "unified_rss_sources.json")
        self.sources_file = sources_file
        self._data = None
        self._all_sources = []    # 扁平化后的所有源（附带 category/entity 信息）
        self._entities = []       # 原始 entity 列表（仅 entity 格式的 category）
        self._load()

    def _load(self):
        with open(self.sources_file, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._all_sources = []
        self._entities = []
        for cat in self._data.get("categories", []):
            cat_id = cat["id"]
            cat_name = cat["name"]
            tier = cat.get("tier", 9)
            cat_format = cat.get("format", "flat")

            for src in cat.get("sources", []):
                if cat_format == "entity" and "entity" in src:
                    # --- Entity 格式：展平 entity.feeds 为独立 source ---
                    entity_name = src["entity"]
                    entity_priority = src.get("priority", 3)
                    entity_note = src.get("note", "")
                    entity_category = src.get("category", "")
                    entity_affiliation = src.get("affiliation", "")

                    self._entities.append({
                        **src,
                        "_category_id": cat_id,
                        "_category_name": cat_name,
                        "_tier": tier,
                    })

                    for feed in src.get("feeds", []):
                        platform = feed.get("platform", "rss")
                        handle = feed.get("handle", "")
                        feed_priority = feed.get("priority", entity_priority)
                        feed_lang = feed.get("lang", "en")
                        # 生成 display name: "Entity (Platform: Handle)"
                        display_name = f"{entity_name} ({handle})" if handle else entity_name

                        entry = {
                            "name": display_name,
                            "url": feed.get("url", ""),
                            "type": feed.get("type", "rss"),
                            "lang": feed_lang,
                            "priority": feed_priority,
                            "note": feed.get("note", entity_note),
                            # entity 专属字段
                            "_entity": entity_name,
                            "_entity_category": entity_category,
                            "_entity_affiliation": entity_affiliation,
                            "_platform": platform,
                            "_handle": handle,
                            # 通用字段
                            "_category_id": cat_id,
                            "_category_name": cat_name,
                            "_tier": tier,
                        }
                        entry["_fetch_method"] = self._infer_fetch_method(entry)
                        self._all_sources.append(entry)
                else:
                    # --- Flat 格式：传统单源 ---
                    entry = {**src, "_category_id": cat_id, "_category_name": cat_name, "_tier": tier}
                    entry.setdefault("_entity", "")
                    entry.setdefault("_platform", "")
                    entry.setdefault("_handle", "")
                    entry["_fetch_method"] = self._infer_fetch_method(src)
                    self._all_sources.append(entry)

    @staticmethod
    def _infer_fetch_method(src: dict) -> str:
        """根据源的 type 和 url 推断采集方法（对应 channels/ 渠道）"""
        src_type = src.get("type", "rss")
        url = src.get("url", "")
        name = src.get("name", "")

        # X/Twitter 源 → 优先 RSSHub，降级到 xreach CLI
        if "rsshub.app/twitter" in url or "xgo.ing/rss/user" in url:
            return "rss_with_x_fallback"
        # YouTube
        if "youtube.com" in url or "youtu.be/" in url or "rsshub.app/youtube" in url:
            return "youtube"
        # GitHub
        if "github.com" in url and src_type != "rss":
            return "github"
        # B站
        if "bilibili.com" in url or "rsshub.app/bilibili" in url:
            return "bilibili"
        # Reddit
        if "reddit.com" in url or "rsshub.app/reddit" in url:
            return "reddit"
        # 小红书
        if "xiaohongshu.com" in url or "xhslink.com" in url:
            return "xiaohongshu"
        # 抖音
        if "douyin.com" in url:
            return "douyin"
        # LinkedIn
        if "linkedin.com" in url:
            return "linkedin"
        # RSSHub 代理的其他源
        if "rsshub.app" in url or "rsshub.rssforever.com" in url:
            return "rss"
        # 微信公众号 RSS
        if "wechat2rss" in url or "Wechat-Scholar" in url:
            return "rss"
        # 标准 RSS/Atom
        if src_type == "rss":
            return "rss"
        # API 接口
        if src_type == "api":
            return "api"
        # 需要爬取的网页
        if src_type == "web":
            return "web_scrape"
        return "rss"

    @property
    def meta(self) -> dict:
        return self._data.get("meta", {})

    @property
    def total(self) -> int:
        return len(self._all_sources)

    @property
    def categories(self) -> list:
        return self._data.get("categories", [])

    def all_sources(self) -> list:
        return self._all_sources

    def filter(
        self,
        tiers: Optional[list[int]] = None,
        category_ids: Optional[list[str]] = None,
        exclude_category_ids: Optional[list[str]] = None,
        max_priority: Optional[int] = None,
        langs: Optional[list[str]] = None,
        fetch_methods: Optional[list[str]] = None,
        name_contains: Optional[str] = None,
        entity: Optional[str] = None,
        platforms: Optional[list[str]] = None,
    ) -> list:
        """
        灵活筛选信源

        Args:
            tiers: 允许的 tier 列表，如 [1, 2]
            category_ids: 只包含这些 category，如 ["tier1_official"]
            exclude_category_ids: 排除这些 category，如 ["tier_special_gaming"]
            max_priority: 最大 priority（含），1=最高，如 max_priority=2 表示只要 priority 1-2
            langs: 语言过滤，如 ["en", "zh"]
            fetch_methods: 采集方法过滤，如 ["rss", "api"]
            name_contains: 名称模糊匹配（匹配 name 或 entity）
            entity: 实体名称精确匹配，如 "OpenAI"、"Google"
            platforms: 平台过滤，如 ["x", "blog", "threads"]
        """
        results = self._all_sources

        if tiers is not None:
            results = [s for s in results if s["_tier"] in tiers]

        if category_ids is not None:
            results = [s for s in results if s["_category_id"] in category_ids]

        if exclude_category_ids is not None:
            results = [s for s in results if s["_category_id"] not in exclude_category_ids]

        if max_priority is not None:
            results = [s for s in results if s.get("priority", 5) <= max_priority]

        if langs is not None:
            results = [s for s in results if s.get("lang", "en") in langs]

        if fetch_methods is not None:
            results = [s for s in results if s.get("_fetch_method") in fetch_methods]

        if name_contains is not None:
            kw = name_contains.lower()
            results = [
                s for s in results
                if kw in s.get("name", "").lower() or kw in s.get("_entity", "").lower()
            ]

        if entity is not None:
            ent_lower = entity.lower()
            results = [s for s in results if s.get("_entity", "").lower() == ent_lower]

        if platforms is not None:
            results = [s for s in results if s.get("_platform", "") in platforms]

        return results

    # --- Entity 专用查询 ---

    def get_entities(self, category_id: Optional[str] = None) -> list:
        """获取原始 entity 列表（未展平）"""
        if category_id:
            return [e for e in self._entities if e["_category_id"] == category_id]
        return self._entities

    def get_entity_feeds(self, entity_name: str) -> list:
        """获取某个 entity 的所有 feeds（展平后）"""
        return self.filter(entity=entity_name)

    def get_by_platform(self, platform: str) -> list:
        """获取指定平台的所有源，如 'x', 'blog', 'threads', 'telegram'"""
        return self.filter(platforms=[platform])

    # --- 便捷方法 ---

    def get_by_category(self, category_id: str) -> list:
        return self.filter(category_ids=[category_id])

    def get_tier1_core(self, max_priority: int = 1) -> list:
        """获取 Tier 1 核心源（priority 1）"""
        return self.filter(tiers=[1], max_priority=max_priority)

    def get_x_twitter_sources(self) -> list:
        """获取所有 X/Twitter 类信源"""
        return [
            s for s in self._all_sources
            if s["_fetch_method"] == "rss_with_x_fallback"
            or s.get("_platform") == "x"
        ]

    def get_rss_only(self) -> list:
        """获取纯 RSS 源（最稳定、最快）"""
        return self.filter(fetch_methods=["rss", "rss_with_x_fallback"])

    def summary(self) -> dict:
        """返回统计摘要"""
        from collections import Counter
        by_tier = Counter(s["_tier"] for s in self._all_sources)
        by_method = Counter(s["_fetch_method"] for s in self._all_sources)
        by_lang = Counter(s.get("lang", "en") for s in self._all_sources)
        by_cat = Counter(s["_category_id"] for s in self._all_sources)
        by_platform = Counter(s.get("_platform", "none") for s in self._all_sources if s.get("_platform"))
        entities = set(s.get("_entity", "") for s in self._all_sources if s.get("_entity"))
        return {
            "total": self.total,
            "total_entities": len(entities),
            "by_tier": dict(sorted(by_tier.items())),
            "by_fetch_method": dict(by_method),
            "by_lang": dict(by_lang),
            "by_category": dict(by_cat),
            "by_platform": dict(by_platform),
        }
