# SearchFeed

[中文文档](./README_CN.md)

A multi-source intelligence pipeline that supercharges AI model search capabilities. Collects signals across 14 platform channels simultaneously, with automatic tool fallback, structured output, and configurable task profiles for everything from quick scans to deep research.

---

## Why Not Just Use AI Search?

Standard AI search tools (Perplexity, ChatGPT Search, etc.) work fine for general queries. But for systematic daily intelligence work, they have real limitations:

| | AI Search | SearchFeed |
|---|---|---|
| Source control | Black box | You define the exact source list |
| Platform coverage | Web pages only | X/Twitter, Xiaohongshu, Douyin, Bilibili, LinkedIn, GitHub, Reddit, WeChat, and more |
| Timeliness | Index latency | Direct RSS/API pull, minutes after publish |
| Failure handling | Silent drop | Per-channel tool fallback chains |
| Output format | Natural language article | Structured `FetchedItem` objects, JSON/Markdown/HTML |
| Deduplication | Opaque | Explicit URL-based dedup |
| Depth control | Uniform | Per-source: full text for core sources, title-only for auxiliary |

The core trade-off: AI search gives you answers quickly with no setup. SearchFeed gives you control — over what you monitor, how deeply, and with what reliability.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI / Task Runner                     │
│              python -m collector <profile>               │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   Task Profiles Layer                    │
│   quick_scan / daily_digest / signal_brief / topic_focus │
│          Decides: which sources, what depth, filters     │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    Source Manager                        │
│            unified_rss_sources.json                      │
│   Tier / Category / Priority / Language / Platform       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   Fetcher Engine                         │
│        Concurrent dispatch, rate limiting                │
│        Auto-detects channel from URL/type                │
└──────────┬──────────────────────────────────────────────┘
           │
    ┌──────▼─────────────────────────────────────────┐
    │              Channels (14 total)                │
    │                                                 │
    │  web      → x-reader → Jina → Firecrawl →      │
    │             Crawl4AI → Tavily → httpx           │
    │                                                 │
    │  rss      → feedparser → x-reader → Jina       │
    │                                                 │
    │  twitter  → RSSHub(feedparser) → xreach → x-reader │
    │                                                 │
    │  youtube  → yt-dlp → x-reader                  │
    │                                                 │
    │  github   → gh CLI → GitHub API → Jina         │
    │                                                 │
    │  bilibili → yt-dlp → bilibili-api → x-reader   │
    │                                                 │
    │  reddit   → JSON API → PRAW → Exa → Jina       │
    │                                                 │
    │  xiaohongshu → mcporter MCP → x-reader         │
    │                                                 │
    │  douyin   → mcporter MCP                       │
    │                                                 │
    │  linkedin → mcporter MCP → Jina                │
    │                                                 │
    │  bosszp   → mcporter MCP                       │
    │                                                 │
    │  exa_search → Tavily → Exa → Multi-Search      │
    │                                                 │
    │  api      → httpx API → httpx Web               │
    │                                                 │
    │  browser  → nodriver → BrowserWing             │
    └─────────────────────────────────────────────────┘
```

### Key Design Decisions

**Channel + Tool Fallback**
Each channel (e.g., `web`) holds an ordered list of tools. If tool #1 fails, it silently tries tool #2, and so on. This means a single misconfigured or rate-limited tool doesn't break collection for that source.

**Entity-Centric Source Format**
Sources can be defined as entities (companies, people) with multiple platform feeds attached. OpenAI as an entity might have a blog RSS, an X account via RSSHub, and a GitHub org — all collected in one pass and attributed to the same entity.

**Tiered Prioritization**
Sources are assigned Tier (1–4) and Priority (1–5). The `signal_brief` profile runs Tier 1 / Priority 1-2 sources at full-text depth, and everything else at title-only — balancing coverage against cost and latency.

**Structured Output**
Every collected item is a `FetchedItem` dataclass with fields: `source_name`, `url`, `title`, `summary`, `content`, `published`, `author`, `lang`, `fetch_method`. This is the foundation for downstream LLM summarization, trend analysis, or database storage.

---

## Task Profiles

| Profile | Sources | Depth | Use Case |
|---|---|---|---|
| `quick_scan` | Tier 1, Priority 1 | Title only | Morning headlines, ~5 min |
| `daily_digest` | Tier 1–2, Priority ≤3 | Title only | Full daily brief |
| `signal_brief` | Tier 1–2 | Core: full text / Aux: title | Weekly Signal Brief |
| `topic_focus` | Tier 1–3 + keyword filter | Full text | Deep dive on a specific topic |
| `deep_research` | All tiers | Full text | Monthly comprehensive report |
| `gaming_focus` | Gaming category + keyword filter | Full text | Gaming industry vertical |

---

## Channels & Tools

### Web (`web.py`)
General-purpose webpage scraping. Fallback chain:
`x-reader` → `Jina Reader` → `Firecrawl` → `Crawl4AI` → `Tavily Extract` → `httpx`

### RSS (`rss.py`)
Standard RSS/Atom feeds. Fallback chain:
`feedparser` → `x-reader` → `Jina Reader`

### X / Twitter (`twitter.py`)
Twitter/X content via RSSHub proxies or direct CLI. Fallback chain:
`feedparser (RSSHub)` → `xreach (Agent Reach)` → `x-reader`

### YouTube (`youtube.py`)
Video metadata and transcripts. Fallback chain:
`yt-dlp` → `x-reader`

### GitHub (`github.py`)
Repository info, READMEs, search. Fallback chain:
`gh CLI` → `GitHub REST API` → `Jina Reader`

### Bilibili (`bilibili.py`)
Chinese video platform. Fallback chain:
`yt-dlp` → `bilibili-api` → `x-reader`

### Reddit (`reddit.py`)
Subreddit and post collection. Fallback chain:
`Reddit JSON API` → `PRAW` → `Exa` → `Jina Reader`

### Xiaohongshu (`xiaohongshu.py`)
Chinese lifestyle/social platform via MCP. Fallback chain:
`mcporter MCP` → `x-reader`

### Douyin (`douyin.py`)
Chinese short video platform via MCP:
`mcporter MCP`

### LinkedIn (`linkedin.py`)
Professional network content via MCP. Fallback chain:
`mcporter MCP` → `Jina Reader`

### BOSS Zhipin (`bosszp.py`)
Chinese job platform via MCP:
`mcporter MCP`

### Search (`exa_search.py`)
Supplemental search when no direct feed exists. Fallback chain:
`Tavily Search` → `Exa AI (mcporter)` → `Multi-Search Engine`

### API (`api.py`)
Direct API endpoints (JSON responses). Fallback chain:
`httpx API` → `httpx Web`

### Browser (`browser.py`)
Last resort for JavaScript-heavy or login-required pages. Fallback chain:
`nodriver` → `BrowserWing`

---

## Setup

### Requirements

```bash
pip install feedparser httpx
```

Optional tools (install what you need):

```bash
# Web scraping
pip install firecrawl-py crawl4ai

# Video platforms
pip install yt-dlp

# Reddit
pip install praw

# Browser automation
pip install nodriver
```

External services (run locally or configure API keys):
- **BrowserWing** — local browser automation service (port 8082)
- **ClawFeed** — local AI digest service (port 8767)
- **RSSHub** — RSS proxy for Twitter/YouTube/etc
- **mcporter** — MCP bridge for Xiaohongshu, Douyin, LinkedIn, Exa

API keys (set as environment variables):
```bash
export TAVILY_API_KEY=your_key
export FIRECRAWL_API_KEY=your_key  # optional
```

### Source Configuration

Edit `unified_rss_sources.json` to define your sources. Two formats are supported:

**Flat format** (traditional single source):
```json
{
  "name": "OpenAI Blog",
  "url": "https://openai.com/blog/rss.xml",
  "type": "rss",
  "lang": "en",
  "priority": 1
}
```

**Entity-centric format** (one entity, multiple platform feeds):
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

Sources are organized into categories with `tier` (1–4) and `format` fields.

---

## Usage

```bash
# Quick scan — Tier 1 headlines only
python -m collector quick_scan

# Daily digest — Tier 1-2, title + summary
python -m collector daily_digest

# Signal Brief — core sources full text + aux titles
python -m collector signal_brief

# Topic focus with keyword filter
python -m collector topic_focus -k "agent,RAG,tool use"

# Full-text deep research
python -m collector deep_research

# Gaming vertical
python -m collector gaming_focus

# With output file
python -m collector daily_digest -o ./output/today.json

# Filter by language
python -m collector daily_digest -l zh

# List all profiles
python -m collector --list

# Show source statistics
python -m collector --stats

# Verbose logging
python -m collector daily_digest -v
```

---

## Output Format

Each run produces a JSON file in `output/` (or your specified path):

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

This output is designed to be piped directly into an LLM for summarization, stored in a vector database, or used for trend analysis.

---

## Extending the System

### Adding a new channel

Create `collector/channels/myplatform.py`:

```python
from .base import BaseTool, BaseChannel, FetchDepth, FetchedItem, register_channel

class MyPlatformTool(BaseTool):
    name = "myplatform"
    description = "My platform collector"

    async def fetch(self, url, depth, source_name="", **kwargs):
        # your implementation
        return [FetchedItem(...)]

class MyPlatformChannel(BaseChannel):
    name = "myplatform"
    tools = [MyPlatformTool]

register_channel(MyPlatformChannel())
```

Then import it in `collector/channels/__init__.py` and add it to `CHANNEL_MAP` in `fetcher_engine.py`.

### Adding a new task profile

Add an entry to `PROFILES` in `collector/task_profiles.py`:

```python
"my_profile": ProfileConfig(
    name="my_profile",
    description="My custom profile",
    tiers=[1, 2],
    fetch_depth=FetchDepth.FULL_TEXT,
    keyword_filter=["AI", "LLM"],
),
```

---

## Project Structure

```
.
├── collector/
│   ├── __main__.py          # Entry point (python -m collector)
│   ├── cli.py               # Argument parsing & progress display
│   ├── fetcher_engine.py    # Core orchestrator, channel dispatch
│   ├── source_manager.py    # Source list loading & filtering
│   ├── task_profiles.py     # Profile definitions & task runner
│   └── channels/
│       ├── base.py          # BaseChannel, BaseTool, FetchedItem
│       ├── web.py           # General web scraping
│       ├── rss.py           # RSS/Atom feeds
│       ├── twitter.py       # X / Twitter
│       ├── youtube.py       # YouTube
│       ├── github.py        # GitHub
│       ├── bilibili.py      # Bilibili
│       ├── reddit.py        # Reddit
│       ├── xiaohongshu.py   # Xiaohongshu (小红书)
│       ├── douyin.py        # Douyin (抖音)
│       ├── linkedin.py      # LinkedIn
│       ├── bosszp.py        # BOSS Zhipin (BOSS直聘)
│       ├── exa_search.py    # Search (Tavily / Exa / Multi-engine)
│       ├── api.py           # Generic API endpoints
│       └── browser.py       # Browser automation (last resort)
├── unified_rss_sources.json # Source list configuration
├── requirements.txt
└── output/                  # Generated collection results
```

---

## Acknowledgements

This project stands on the shoulders of several excellent open source tools:

- **[Agent Reach](https://github.com/igtm/agent-reach)** — The `xreach` CLI used in the Twitter/X channel for authenticated tweet collection without the official API
- **[Multi Search Engine](https://github.com/mcp-project/multi-search)** — The multi-engine search tool integrated in `exa_search.py` for Google/Baidu/WeChat/Bing fallback search
- **[Deep Research](https://github.com/dzhng/deep-research)** — Inspired the tiered research profile design and the concept of structured intelligence gathering
- **[x-reader](https://github.com/xreader-project/x-reader)** — The multi-platform content reader used across nearly every channel as a reliable fallback, supporting WeChat, X, Xiaohongshu, Telegram, YouTube, Bilibili, and general web pages
- **[BrowserWing](https://github.com/browserwing/browserwing)** — The local browser automation service used in the browser channel, providing persistent login state and reliable JS rendering
- **[ModSearch](https://github.com/modsearch/modsearch)** — MCP-based search integration that powers the Exa and platform-specific search capabilities via mcporter

---

## License

MIT
