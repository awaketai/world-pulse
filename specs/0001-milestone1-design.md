# 0001 — Milestone 1 设计方案：AI 科技情报 Agent

> 状态：Draft
> 日期：2026-05-25

## 1. 目标

实现 Milestone 1：一个自动采集、AI 分析、推送和展示的全球科技情报系统。

核心链路：

```
采集 → 去重 → AI 分类/总结 → 热度打分 → 每日 Insight → Telegram 推送 + Web 展示
```

## 2. 技术选型

| 层 | 技术 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | AI/爬虫生态丰富 |
| 包管理 | uv | 快速现代 |
| 数据库 | SQLite | 轻量，本地和 Docker 都适用 |
| LLM SDK | openai（兼容任意 base_url） | 支持 OpenAI / Claude / DeepSeek / Ollama 等 |
| Web | FastAPI + Jinja2 | 异步轻量，模板渲染 |
| 调度 | APScheduler | 定时采集 + 定时推送 |
| 容器 | Docker + docker-compose | 一键部署 |

## 3. 数据源

Milestone 1 聚焦三个高质量来源：

| 来源 | 采集方式 | 频率 |
|---|---|---|
| Hacker News | Firebase API (`hacker-news.firebaseio.com`) | 每 2 小时 |
| GitHub Trending | 爬取 `github.com/trending` | 每 2 小时 |
| arXiv | arXiv API (`export.arxiv.org/api/query`) | 每 2 小时 |

### 3.1 Hacker News 采集逻辑

1. 请求 `https://hacker-news.firebaseio.com/v0/topstories.json` 获取 top story IDs
2. 取前 N 条（默认 30），逐条请求 `/v0/item/{id}.json`
3. 提取：title, url, score, by, time, descendants（评论数）

### 3.2 GitHub Trending 采集逻辑

1. 请求 `https://github.com/trending` HTML 页面
2. 解析 CSS 选择器提取：仓库名、描述、语言、star 增量
3. 构建标准 Item 格式

### 3.3 arXiv 采集逻辑

1. 请求 arXiv API，按分类过滤（cs.AI, cs.CL, cs.LG）
2. 解析 Atom XML 响应
3. 提取：title, summary（abstract）, authors, published, link

## 4. 项目结构

```
world-pulse/
├── config.yaml.example          # 配置模板
├── config.yaml                  # 用户配置（.gitignore 已忽略）
├── pyproject.toml               # 依赖管理
├── Dockerfile                   # Docker 镜像
├── docker-compose.yaml          # 一键部署
├── run.py                       # 入口：启动 scheduler + web
│
├── worldpulse/
│   ├── __init__.py
│   ├── config.py                # 配置加载（YAML → dataclass）
│   ├── db.py                    # SQLite 建表 + CRUD
│   ├── models.py                # Item / DailyInsight 数据模型
│   │
│   ├── collectors/              # 采集层
│   │   ├── __init__.py
│   │   ├── base.py              # BaseCollector 抽象基类
│   │   ├── hackernews.py        # HN 采集器
│   │   ├── github_trending.py   # GitHub Trending 采集器
│   │   └── arxiv.py             # arXiv 采集器
│   │
│   ├── dedup.py                 # 去重逻辑
│   ├── processor.py             # AI 处理：分类 + 总结 + 打分
│   ├── ask.py                   # 用户追问：FTS5 搜索 + LLM 回答
│   ├── telegram_bot.py          # Telegram 推送
│   ├── scheduler.py             # APScheduler 调度
│   │
│   └── web/                     # Web 展示
│       ├── __init__.py
│       ├── app.py               # FastAPI 路由
│       ├── templates/
│       │   └── index.html       # 主页面
│       └── static/
│           └── style.css        # 样式
│
├── data/                        # SQLite 数据文件（自动创建）
└── specs/                       # 设计文档
```

## 5. 数据模型

### 5.1 items 表

```sql
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,           -- SHA256(source:source_id)[:16]
    source TEXT NOT NULL,           -- "hackernews" | "github" | "arxiv"
    source_id TEXT NOT NULL,        -- 原始 ID
    title TEXT NOT NULL,
    url TEXT,
    content TEXT,                   -- 原始内容/摘要
    raw_data TEXT,                  -- 完整 JSON
    category TEXT,                  -- AI 分类（处理后填充）
    summary TEXT,                   -- AI 总结（处理后填充）
    score REAL DEFAULT 0,           -- 热度分数
    published_at TIMESTAMP,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP          -- AI 处理完成时间
);
```

### 5.2 daily_insights 表

```sql
CREATE TABLE IF NOT EXISTS daily_insights (
    id TEXT PRIMARY KEY,            -- "insight-{date}"
    date TEXT NOT NULL UNIQUE,      -- "2026-05-25"
    daily_summary TEXT,             -- AI 生成的每日总结
    trends TEXT,                    -- AI 识别的趋势（Markdown）
    item_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 6. 核心流程

### 6.1 采集流程

```
定时触发（每 2 小时）
    ↓
并发启动所有启用的 Collector
    ↓
Collector.collect() → List[RawItem]
    ↓
去重检查（source + source_id 唯一）
    ↓
插入 items 表（category/summary 为空）
    ↓
触发 AI 处理
```

### 6.2 AI 处理流程

```
查询 items WHERE processed_at IS NULL
    ↓
每 10 条一批，调用 LLM
    ↓
Prompt 要求返回 JSON:
{
    "items": [
        {
            "category": "AI Research",
            "summary": "一句话中文总结",
            "score_adjustment": 0~10
        }
    ]
}
    ↓
更新 items 表的 category / summary / score / processed_at
    ↓
热度分数 = 基础分(source权重) + 互动分 + 时间衰减 + score_adjustment
```

#### 热度分公式

```
base_score = {
    "hackernews": 40,
    "github": 30,
    "arxiv": 20
}

score = base_score
      + min(hackernews.score / 10, 30)       # HN points
      + min(hackernews.descendants / 5, 20)   # HN comments
      + min(github.today_star / 10, 30)       # GitHub stars
      + score_adjustment                       # LLM 调整分 (0-10)
```

### 6.3 每日 Insight 生成

```
定时触发（每天 09:00）
    ↓
查询昨天已处理 items，按 category 分组
    ↓
调用 LLM 生成:
  - daily_summary: 今日科技动态概要（3-5 段）
  - trends: 值得关注的趋势（列表）
    ↓
保存到 daily_insights 表
    ↓
格式化 Telegram 消息并发送
```

### 6.4 Telegram 推送格式

```
📡 World Pulse 科技日报 — 2026-05-25

━━ 今日概要 ━━
{daily_summary}

━━ 趋势洞察 ━━
{trends}

━━ 重点动态 ━━
🏆 [AI Research] 新论文标题
   → 一句话总结
   🔗 https://...

🔥 [LLM & Models] 模型发布
   → 一句话总结
   🔗 https://...
...（按 score 排序，取 Top 15）
```

## 7. 分类体系

LLM 从以下预设分类中选择：

| 分类 ID | 显示名 | 说明 |
|---|---|---|
| ai_research | AI Research | AI 研究论文/突破 |
| open_source | Open Source | 开源项目/发布 |
| llm_models | LLM & Models | 大模型相关 |
| ai_agents | AI Agents | 智能体/Agent 框架 |
| infrastructure | Infrastructure | 基础设施/DevOps |
| chips_hardware | Chips & Hardware | 芯片/硬件 |
| startups_funding | Startups & Funding | 创业/融资 |
| dev_tools | Dev Tools | 开发工具/编程 |
| automation | Automation | 自动化/RPA |

## 8. 配置文件

`config.yaml.example`（需复制为 `config.yaml`）：

```yaml
llm:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-xxx"
  model: "gpt-4o-mini"

telegram:
  bot_token: "xxx"
  chat_id: "xxx"

sources:
  hackernews:
    enabled: true
    top_n: 30
  github_trending:
    enabled: true
  arxiv:
    enabled: true
    categories: ["cs.AI", "cs.CL", "cs.LG"]
    max_results: 20

schedule:
  collect_interval_minutes: 120
  push_time: "09:00"

database:
  path: "data/worldpulse.db"

web:
  host: "0.0.0.0"
  port: 8080
```

## 9. 用户追问（Ask）

用户可以基于系统已采集的数据提问，系统基于已有情报回答，不是联网搜索。

### 流程

```
用户输入问题："最近MCP为什么突然爆发？"
    ↓
SQLite FTS5 全文搜索，检索近 7 天 items
  - 搜索字段：title, summary, content
  - 限制：最多返回 20 条相关条目
    ↓
将相关条目的 title + summary + category + published_at 拼成上下文
    ↓
调用 LLM，Prompt:
  "你是科技情报分析助手。基于以下已采集的情报数据回答用户问题。
   如果数据不足以回答，直接说明，不要编造。

   情报数据：
   {相关条目}

   用户问题：{question}"
    ↓
LLM 返回回答，展示在 Web 页面
```

### 关键设计

- **单次搜索 + 单次 LLM 调用**，不做多轮检索
- **数据不足时明确告知用户**，不让 LLM 猜测或编造
- **搜索范围固定为近 7 天**，不查全部历史
- **用户换种问法再问 = 手动触发新一轮搜索**，等价于多轮检索

### API 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `POST /api/ask` | POST | Body: `{"question": "..."}` → 返回 `{"answer": "...", "sources": [...]}` |

### FTS5 虚拟表

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, content, summary,
    content='items',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- 通过触发器自动同步
CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, content, summary)
    VALUES (new.rowid, new.title, new.content, new.summary);
END;

CREATE TRIGGER items_au AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, content, summary)
    VALUES ('delete', old.rowid, old.title, old.content, old.summary);
    INSERT INTO items_fts(rowid, title, content, summary)
    VALUES (new.rowid, new.title, new.content, new.summary);
END;
```

## 10. Web 展示

### 页面结构

- 单页应用，顶部 Tab 按分类切换
- 默认显示"All"分类，按 score 降序
- 底部显示最新 Daily Insight
- 页面底部有追问输入框
- 响应式设计，支持移动端

### 每条 Item 展示

```
┌──────────────────────────────────────┐
│ 🏆 AI Research    来源: HN   3h ago  │
│ 论文标题（可点击跳转原文）              │
│ AI 一句话总结                         │
│ 热度: ████████░░ 82                  │
└──────────────────────────────────────┘
```

### 追问输入框

页面底部固定一个输入框，用户输入问题后，调用 `/api/ask`，在下方展示回答和引用的来源条目。

### API 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `GET /` | GET | 主页面（服务端渲染） |
| `GET /api/items` | GET | JSON: 获取 items，支持 `?category=&date=` |
| `GET /api/insights` | GET | JSON: 获取 daily insights |
| `GET /api/insights/{date}` | GET | JSON: 获取指定日期 insight |
| `POST /api/ask` | POST | 用户追问（见第 9 节） |

## 11. 调度设计

```python
# scheduler.py
scheduler = AsyncIOScheduler()

# 每 2 小时采集 + 处理
scheduler.add_job(collect_and_process, 'interval', minutes=120)

# 每日 09:00 生成 insight + 推送
scheduler.add_job(generate_and_push, 'cron', hour=9, minute=0)
```

入口 `run.py` 同时启动 scheduler 和 FastAPI web server。

## 12. Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install uv && uv pip install --system -e .
COPY . .
RUN mkdir -p data
CMD ["python", "run.py"]
```

```yaml
# docker-compose.yaml
services:
  worldpulse:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./data:/app/data
    restart: unless-stopped
```

## 13. 依赖

```toml
[project]
name = "worldpulse"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "jinja2>=3.1",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "apscheduler>=3.10",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "python-telegram-bot>=21.0",
]
```

## 14. 实施顺序

1. 项目骨架：pyproject.toml、config.py、db.py、models.py、config.yaml.example
2. 采集器：base.py、hackernews.py、github_trending.py、arxiv.py、dedup.py
3. AI 处理：processor.py
4. 用户追问：ask.py（FTS5 搜索 + LLM 回答）
5. Telegram 推送：telegram_bot.py
6. Web 展示：FastAPI + Jinja2 模板（含追问输入框）
7. 调度 + 入口：scheduler.py、run.py、Dockerfile、docker-compose.yaml

## 15. 验证方式

1. `python run.py` 启动 → 检查采集日志输出
2. 访问 `http://localhost:8080` → 查看分类展示
3. 在 Web 页面输入追问 → 验证 `/api/ask` 返回结果
4. 检查 Telegram → 确认收到推送
5. `docker compose up` → 验证容器部署
