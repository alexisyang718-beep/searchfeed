"""
CLI 入口 — 命令行运行采集任务

用法：
  # 快速扫描（5分钟，只看标题）
  python -m collector quick_scan

  # 每日简报
  python -m collector daily_digest

  # 深度研究
  python -m collector deep_research

  # 专题分析（带关键词）
  python -m collector topic_focus --keywords "agent,RAG,tool use"

  # Signal Brief
  python -m collector signal_brief

  # 游戏专题
  python -m collector gaming_focus

  # 列出所有 Profile
  python -m collector --list

  # 查看信源统计
  python -m collector --stats
"""

import argparse
import asyncio
import logging
import sys

from .task_profiles import TaskRunner, PROFILES
from .source_manager import SourceManager


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def progress_bar(done, total, name):
    pct = done / total * 100
    bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
    print(f"\r  [{bar}] {done}/{total} ({pct:.0f}%) — {name[:40]}", end="", flush=True)
    if done == total:
        print()


def main():
    parser = argparse.ArgumentParser(
        description="AI Signal Collector — 多层内容采集系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m collector quick_scan                     # 快速扫描
  python -m collector daily_digest                   # 每日简报
  python -m collector topic_focus -k "agent,RAG"     # 专题分析
  python -m collector signal_brief                   # Signal Brief
  python -m collector --list                         # 列出所有 Profile
  python -m collector --stats                        # 信源统计
        """,
    )
    parser.add_argument("profile", nargs="?", help="任务 Profile 名称")
    parser.add_argument("-k", "--keywords", help="关键词过滤（逗号分隔）")
    parser.add_argument("-l", "--langs", help="语言过滤（逗号分隔，如 en,zh）")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument("-n", "--max-items", type=int, help="最大输出条目数")
    parser.add_argument("--exclude", help="排除类目（逗号分隔）")
    parser.add_argument("--list", action="store_true", help="列出所有可用 Profile")
    parser.add_argument("--stats", action="store_true", help="显示信源统计")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 列出 Profile
    if args.list:
        print("\n可用任务 Profile：\n")
        for name, profile in PROFILES.items():
            depth_icon = "📋" if profile.fetch_depth.value == "title_only" else "📄"
            tiers_str = f"Tier {profile.tiers}" if profile.tiers else "All Tiers"
            print(f"  {depth_icon} {name:20s} — {profile.description}")
            print(f"     {tiers_str} | priority ≤ {profile.max_priority or 'all'} | 并发 {profile.concurrency}")
            if profile.exclude_category_ids:
                print(f"     排除: {profile.exclude_category_ids}")
            print()
        return

    # 信源统计
    if args.stats:
        mgr = SourceManager()
        s = mgr.summary()
        print(f"\n信源总数: {s['total']}\n")
        print("按 Tier:")
        for tier, count in sorted(s["by_tier"].items()):
            print(f"  Tier {tier}: {count}")
        print("\n按采集方式:")
        for method, count in s["by_fetch_method"].items():
            print(f"  {method}: {count}")
        print("\n按语言:")
        for lang, count in s["by_lang"].items():
            print(f"  {lang}: {count}")
        print("\n按类目:")
        for cat, count in s["by_category"].items():
            print(f"  {cat}: {count}")
        return

    # 执行采集
    if not args.profile:
        parser.print_help()
        sys.exit(1)

    runner = TaskRunner()

    keyword_filter = args.keywords.split(",") if args.keywords else None
    exclude = args.exclude.split(",") if args.exclude else None
    langs = args.langs.split(",") if args.langs else None

    items = asyncio.run(runner.run(
        args.profile,
        keyword_filter=keyword_filter,
        exclude_category_ids=exclude,
        langs=langs,
        max_items=args.max_items,
        output_file=args.output,
        progress_callback=progress_bar,
    ))

    print(f"\n✅ 完成！共采集 {len(items)} 条内容")


if __name__ == "__main__":
    main()
