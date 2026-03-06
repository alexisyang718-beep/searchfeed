"""快速测试 channels 架构"""
from collector.fetcher_engine import FetcherEngine, FetchDepth, FetchedItem, ClawFeedHelper
from collector.channels import all_channels, doctor

print('=== 已注册渠道 ===\n')
channels = all_channels()
print(f'共 {len(channels)} 个渠道\n')
for ch_name, ch in channels.items():
    tools = [t.name for t in ch.tools]
    if len(tools) > 1:
        print(f'  {ch_name:15s} → {tools[0]:18s} ← 可换: {", ".join(tools[1:])}')
    else:
        print(f'  {ch_name:15s} → {tools[0]}')

print(f'\n=== 所有工具 ===\n')
all_tools = FetcherEngine.list_tools()
print(f'共 {len(all_tools)} 个工具\n')
for t in all_tools:
    ch = t.get('channel','')
    login = 'Y' if t.get('needs_login') else ' '
    print(f'  [{ch:12s}] {t["name"]:20s} | {t.get("speed","N/A"):8s} | login:{login}')

print(f'\n=== 渠道详情 ===\n')
for ch in FetcherEngine.list_channels():
    print(f'  {ch["channel"]:15s} | 默认:{ch["default_tool"]:18s} | 工具数:{len(ch["tools"])}')

print(f'\n=== Doctor ===\n')
for ch, tools in doctor().items():
    print(f'  {ch}: {list(tools.keys())}')

# 测试 task_profiles 能否正常导入
from collector.task_profiles import TaskRunner, PROFILES
print(f'\n=== Task Profiles ===\n')
for name, p in PROFILES.items():
    print(f'  {name:15s}: {p.description[:50]}')

print('\n✅ All imports OK!')
