# SearchFeed

一套面向 AI 模型的多源精选信息采集管道。同时接入 14 个平台渠道，自动工具降级容错，结构化输出，支持从快速扫描到深度研究的多种任务模式。

---

## 为什么不直接用 AI 搜索？

Perplexity、ChatGPT Search 等 AI 搜索工具适合临时查询，但用于系统性日常情报采集时有明显局限：

| | AI 搜索 | SearchFeed |
|---|---|---|
| 信源控制 | 黑盒，你不知道抓了哪些 | 你自己定义精选信源列表 |
| 平台覆盖 | 基本只有公开网页 | X/Twitter、小红书、抖音、B站、LinkedIn、GitHub、Reddit、微信公众号等 |
| 时效性 | 索引有延迟 | 直接拉 RSS/API，发布后数分钟内采集到 |
| 失败处理 | 静默丢失 | 每个渠道有多工具降级链 |
| 输出格式 | 自然语言文章 | 结构化 `FetchedItem` 对象，支持 JSON/Markdown/HTML |
| 去重 | 黑盒 | 基于 URL 的确定性去重 |
| 采集深度 | 统一处理 | 可分层：核心信源全文，辅助信源仅标题 |

核心取舍：AI 搜索零配置开箱即用；SearchFeed 给你控制权——控制监控什么、监控多深、以什么可靠性保障。

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    CLI / 任务运行器                       │
│              python -m collector <profile>               │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                      任务档案层                           │
│   quick_scan / daily_digest / signal_brief / topic_focus │
│          决定：选哪些信源、采集深度、关键词过滤            │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                      信源管理器                           │
│            unified_rss_sources.json                      │
│       Tier / Category / Priority / 语言 / 平台            │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                      采集引擎                             │
│         并发调度，自动限速，根据 URL 自动识别渠道           │
└──────────┬──────────────────────────────────────────────┘
           │
    ┌──────▼─────────────────────────────────────────┐
    │              渠道层（14 个渠道）                 │
    │                                                 │
    │  web        → x-reader → Jina → Firecrawl →    │
    │               Crawl4AI → Tavily → httpx         │
    │                                                 │
    │  rss        → feedparser → x-reader → Jina     │
    │                                                 │
    │  twitter    → RSSHub(feedparser) → xreach →    │
    │               x-reader                         │
    │                                                 │
    │  youtube    → yt-dlp → x-reader                │
    │                                                 │
    │  github     → gh CLI → GitHub API → Jina       │
    │                                                 │
    │  bilibili   → yt-dlp → bilibili-api → x-reader │
    │                                                 │
    │  reddit     → JSON API → PRAW → Exa → Jina     │
    │                                                 │
    │  xiaohongshu → mcporter MCP → x-reader         │
    │                                                 │
    │  douyin     → mcporter MCP                     │
    │                                                 │
    │  linkedin   → mcporter MCP → Jina              │
    │                                                 │
    │  bosszp     → mcporter MCP                     │
    │                                                 │
    │  exa_search → Tavily → Exa → 多引擎搜索         │
    │                                                 │
    │  api        → httpx API → httpx Web             │
    │                                                 │
    │  browser    → nodriver → BrowserWing           │
    └─────────────────────────────────────────────────┘
```

### 核心设计决策

**渠道 + 工具降级链**
每个渠道（如 `web`）内部维护一个有序的工具列表。工具 #1 失败后，自动静默切换到工具 #2，依此类推。单个工具挂掉或被限速，不会导致该信源采集失败。

**以实体为中心的信源格式**
信源可以按实体（公司、人物）定义，一个实体绑定多个平台的 feed。OpenAI 作为一个实体，可以同时挂 Blog RSS、X 账号（通过 RSSHub）、GitHub 组织——一次采集，统一归因。

**分层优先级**
信源按 Tier（1–4）和 Priority（1–5）分级。`signal_brief` 模式对 Tier 1 / Priority 1-2 的核心源做全文采集，其余仅取标题——在覆盖面、成本和延迟之间取得平衡。

**结构化输出**
每条采集结果是一个 `FetchedItem` dataclass，包含：`source_name`、`url`、`title`、`summary`、`content`、`published`、`author`、`lang`、`fetch_method`。这是下游 LLM 摘要、趋势分析或数据库存储的基础数据格式。

---

## 任务档案（Task Profiles）

| Profile | 信源范围 | 采集深度 | 适用场景 |
|---|---|---|---|
| `quick_scan` | Tier 1，Priority 1 | 仅标题 | 晨间快速扫描 |
| `daily_digest` | Tier 1–2，Priority ≤3 | 仅标题 | 每日简报 |
| `signal_brief` | Tier 1–2 | 核心全文 / 辅助标题 | 每周 Signal Brief |
| `topic_focus` | Tier 1–3 + 关键词过滤 | 全文 | 专题深度分析 |
| `deep_research` | 全 Tier | 全文 | 月度综合报告 |
| `gaming_focus` | 游戏类目 + 关键词过滤 | 全文 | 游戏行业垂直 |

---

## 渠道与工具说明

### 通用网页 (`web.py`)
通用网页爬取。降级链：
`x-reader` → `Jina Reader` → `Firecrawl` → `Crawl4AI` → `Tavily Extract` → `httpx`

### RSS (`rss.py`)
标准 RSS/Atom 订阅。降级链：
`feedparser` → `x-reader` → `Jina Reader`

### X / Twitter (`twitter.py`)
通过 RSSHub 代理或 CLI 直接采集。降级链：
`feedparser (RSSHub)` → `xreach (Agent Reach)` → `x-reader`

### YouTube (`youtube.py`)
视频元数据与字幕。降级链：
`yt-dlp` → `x-reader`

### GitHub (`github.py`)
仓库信息、README、搜索。降级链：
`gh CLI` → `GitHub REST API` → `Jina Reader`

### B站 (`bilibili.py`)
B站视频与 UP 主内容。降级链：
`yt-dlp` → `bilibili-api` → `x-reader`

### Reddit (`reddit.py`)
子版块与帖子采集。降级链：
`Reddit JSON API` → `PRAW` → `Exa` → `Jina Reader`

### 小红书 (`xiaohongshu.py`)
通过 MCP 采集。降级链：
`mcporter MCP` → `x-reader`

### 抖音 (`douyin.py`)
通过 MCP 采集：
`mcporter MCP`

### LinkedIn (`linkedin.py`)
通过 MCP 采集。降级链：
`mcporter MCP` → `Jina Reader`

### BOSS直聘 (`bosszp.py`)
通过 MCP 采集：
`mcporter MCP`

### 搜索补充 (`exa_search.py`)
无直接 feed 时的搜索兜底。降级链：
`Tavily Search` → `Exa AI (mcporter)` → `多搜索引擎`

### API (`api.py`)
直接调用 JSON API 接口。降级链：
`httpx API` → `httpx Web`

### 浏览器自动化 (`browser.py`)
JS 渲染页面或需要登录态时的最后防线。降级链：
`nodriver` → `BrowserWing`

---

## 安装与配置

### 基础依赖

```bash
pip install feedparser httpx
```

可选工具（按需安装）：

```bash
# 网页爬取
pip install firecrawl-py crawl4ai

# 视频平台
pip install yt-dlp

# Reddit
pip install praw

# 浏览器自动化
pip install nodriver
```

外部服务（本地运行或配置 API Key）：
- **BrowserWing** — 本地浏览器自动化服务（端口 8082）
- **ClawFeed** — 本地 AI 摘要服务（端口 8767）
- **RSSHub** — Twitter/YouTube 等平台的 RSS 代理
- **mcporter** — 小红书、抖音、LinkedIn、Exa 的 MCP 网关

API Key 配置（环境变量）：
```bash
export TAVILY_API_KEY=your_key
export FIRECRAWL_API_KEY=your_key  # 可选
```

### 信源配置

编辑 `unified_rss_sources.json` 定义你的信源。支持两种格式：

**平铺格式**（传统单源）：
```json
{
  "name": "OpenAI Blog",
  "url": "https://openai.com/blog/rss.xml",
  "type": "rss",
  "lang": "en",
  "priority": 1
}
```

**以实体为中心的格式**（一个实体，多平台 feed）：
```json
{
  "entity": "OpenAI",
  "priority": 1,
  "feeds": [
    {"platform": "blog", "url": "https://openai.com/blog/rss.xml", "type": "rss"},
    {"platform": "x", "url": "https://rsshub.app/twitter/user/OpenAI", "type": "rss"}
  ]
}
```

信源按 category 分组，每个 category 有 `tier`（1–4）和 `format` 字段。

---

## 使用方法

```bash
# 快速扫描 — Tier 1 仅标题
python -m collector quick_scan

# 每日简报 — Tier 1-2，标题+摘要
python -m collector daily_digest

# Signal Brief — 核心源全文 + 辅助源标题
python -m collector signal_brief

# 专题分析（带关键词过滤）
python -m collector topic_focus -k "agent,RAG,tool use"

# 深度研究全文采集
python -m collector deep_research

# 游戏行业垂直
python -m collector gaming_focus

# 指定输出路径
python -m collector daily_digest -o ./output/today.json

# 按语言过滤
python -m collector daily_digest -l zh

# 列出所有 Profile
python -m collector --list

# 查看信源统计
python -m collector --stats

# 详细日志
python -m collector daily_digest -v
```

---

## 输出格式

每次运行在 `output/` 目录（或指定路径）生成 JSON 文件：

```json
[
  {
    "source_name": "OpenAI Blog",
    "source_url": "https://openai.com/blog/rss.xml",
    "title": "...",
    "url": "https://openai.com/blog/...",
    "summary": "...",
    "content": "...",
    "published": "2026-03-05T...",
    "author": "",
    "lang": "en",
    "fetch_method": "feedparser",
    "fetch_depth": "full_text",
    "fetched_at": "2026-03-05T...",
    "id": "a3f2b1c4d5e6"
  }
]
```

输出设计为可直接对接 LLM 做摘要生成、存入向量数据库，或用于趋势分析。

---

## 扩展系统

### 新增渠道

创建 `collector/channels/myplatform.py`：

```python
from .base import BaseTool, BaseChannel, FetchDepth, FetchedItem, register_channel

class MyPlatformTool(BaseTool):
    name = "myplatform"
    description = "我的平台采集工具"

    async def fetch(self, url, depth, source_name="", **kwargs):
        # 实现采集逻辑
        return [FetchedItem(...)]

class MyPlatformChannel(BaseChannel):
    name = "myplatform"
    tools = [MyPlatformTool]

register_channel(MyPlatformChannel())
```

然后在 `collector/channels/__init__.py` 中 import，并在 `fetcher_engine.py` 的 `CHANNEL_MAP` 中添加映射。

### 新增任务档案

在 `collector/task_profiles.py` 的 `PROFILES` 中添加：

```python
"my_profile": ProfileConfig(
    name="my_profile",
    description="我的自定义档案",
    tiers=[1, 2],
    fetch_depth=FetchDepth.FULL_TEXT,
    keyword_filter=["AI", "LLM"],
),
```

---

## 项目结构

```
.
├── collector/
│   ├── __main__.py          # 入口（python -m collector）
│   ├── cli.py               # 参数解析与进度显示
│   ├── fetcher_engine.py    # 核心编排器，渠道调度
│   ├── source_manager.py    # 信源加载与筛选
│   ├── task_profiles.py     # 任务档案定义与运行器
│   └── channels/
│       ├── base.py          # BaseChannel、BaseTool、FetchedItem
│       ├── web.py           # 通用网页爬取
│       ├── rss.py           # RSS/Atom 订阅
│       ├── twitter.py       # X / Twitter
│       ├── youtube.py       # YouTube
│       ├── github.py        # GitHub
│       ├── bilibili.py      # B站
│       ├── reddit.py        # Reddit
│       ├── xiaohongshu.py   # 小红书
│       ├── douyin.py        # 抖音
│       ├── linkedin.py      # LinkedIn
│       ├── bosszp.py        # BOSS直聘
│       ├── exa_search.py    # 搜索补充（Tavily / Exa / 多引擎）
│       ├── api.py           # 通用 API 接口
│       └── browser.py       # 浏览器自动化（最后防线）
├── unified_rss_sources.json # 信源配置
├── requirements.txt
└── output/                  # 采集结果输出目录
```

---

## 致谢

本项目站在众多优秀开源工具的肩膀上：

- **[Agent Reach](https://github.com/igtm/agent-reach)** — Twitter/X 渠道中使用的 `xreach` CLI，无需官方 API 即可采集推文
- **[Multi Search Engine](https://github.com/mcp-project/multi-search)** — 集成在 `exa_search.py` 中的多引擎搜索工具，支持 Google、百度、微信、必应等作为搜索降级
- **[Deep Research](https://github.com/dzhng/deep-research)** — 启发了分层研究档案的设计思路和结构化情报采集的概念
- **[x-reader](https://github.com/xreader-project/x-reader)** — 跨平台内容阅读器，在几乎每个渠道中都作为可靠的降级工具，支持微信、X、小红书、Telegram、YouTube、B站及通用网页
- **[BrowserWing](https://github.com/browserwing/browserwing)** — 浏览器渠道中使用的本地自动化服务，提供持久化登录态和可靠的 JS 渲染能力
- **[ModSearch](https://github.com/modsearch/modsearch)** — 基于 MCP 的搜索集成，通过 mcporter 驱动 Exa 及各平台专项搜索能力

---

## License

MIT
