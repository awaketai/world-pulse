# 0002 — Milestone 1 实现计划

> 状态：Draft
> 日期：2026-05-25
> 依据：[0001-milestone1-design.md](0001-milestone1-design.md)

## 实施阶段

### Phase 1：项目骨架 + 配置 + 数据层

创建项目基础结构，配置加载，数据库建表。

| 文件 | 内容 |
|---|---|
| `pyproject.toml` | 项目元数据 + 全部依赖声明 |
| `config.yaml.example` | 配置模板（LLM/Telegram/Sources/Schedule/DB/Web） |
| `worldpulse/__init__.py` | 空 |
| `worldpulse/config.py` | YAML → dataclass，`load_config(path)` 函数 |
| `worldpulse/models.py` | `Item`、`DailyInsight` dataclass，`Category` 枚举 |
| `worldpulse/db.py` | SQLite 连接管理，建表（items + items_fts + 触发器 + daily_insights），CRUD 方法 |

**db.py 需实现的方法：**

```python
class Database:
    def __init__(self, db_path: Path) -> None: ...
    async def connect(self) -> None: ...                    # 建连接 + 建表
    async def insert_items(self, items: list[Item]) -> int: ...  # 返回插入条数（去重后）
    async def get_unprocessed_items(self) -> list[Item]: ...
    async def update_item_processed(self, item_id: str, category: str, summary: str, score: float) -> None: ...
    async def get_items(self, category: str | None = None, date: str | None = None, limit: int = 100) -> list[Item]: ...
    async def get_items_by_ids(self, ids: list[str]) -> list[Item]: ...
    async def search_items(self, query: str, days: int = 7, limit: int = 20) -> list[Item]: ...
    async def save_daily_insight(self, insight: DailyInsight) -> None: ...
    async def get_daily_insights(self, limit: int = 10) -> list[DailyInsight]: ...
    async def get_daily_insight(self, date: str) -> DailyInsight | None: ...
    async def close(self) -> None: ...
```

**验证：** Python 能导入各模块，SQLite 表正确创建。

---

### Phase 2：采集器 + 去重

三个数据源采集器 + 去重逻辑。

| 文件 | 内容 |
|---|---|
| `worldpulse/collectors/__init__.py` | 导出所有 collector |
| `worldpulse/collectors/base.py` | `BaseCollector` 抽象基类，定义 `collect() -> list[Item]` 接口 |
| `worldpulse/collectors/hackernews.py` | HN Firebase API 采集，取 top N stories |
| `worldpulse/collectors/github_trending.py` | 爬取 GitHub Trending HTML，BeautifulSoup 解析 |
| `worldpulse/collectors/arxiv.py` | arXiv Atom API 请求，lxml 解析 |
| `worldpulse/dedup.py` | 基于 `source + source_id` 的去重检查 |

**BaseCollector 接口：**

```python
class BaseCollector(ABC):
    def __init__(self, config: dict[str, Any], http_client: httpx.AsyncClient) -> None: ...
    @abstractmethod
    async def collect(self) -> list[Item]: ...
```

**dedup.py：**

```python
async def filter_duplicates(db: Database, items: list[Item]) -> list[Item]: ...
```

检查每个 item 的 `source + source_id` 是否已存在于数据库，返回不存在的新条目。

**验证：** 单独运行每个 collector，确认返回正确的 Item 列表。

---

### Phase 3：AI 处理

LLM 调用封装，分类 + 总结 + 打分。

| 文件 | 内容 |
|---|---|
| `worldpulse/processor.py` | `AIProcessor` 类，封装 OpenAI SDK 调用 |

**AIProcessor 需实现：**

```python
class AIProcessor:
    def __init__(self, config: LLMConfig) -> None: ...

    async def process_items(self, items: list[Item]) -> list[ProcessedItem]: ...
    # 批量处理（每批 10 条），返回 category + summary + score_adjustment

    async def generate_daily_insight(self, items: list[Item]) -> DailyInsight: ...
    # 生成每日总结 + 趋势分析

    async def answer_question(self, question: str, context_items: list[Item]) -> AskResult: ...
    # 基于上下文条目回答用户追问
```

**内部实现：**

- 使用 `openai.AsyncOpenAI(base_url=..., api_key=...)` 初始化客户端
- `process_items`：每 10 条一批，Prompt 要求返回 JSON（category/summary/score_adjustment）
- `generate_daily_insight`：将当日 items 按分类分组后传入 LLM
- `answer_question`：将搜索到的条目拼成上下文 + 用户问题，单次 LLM 调用

**热度分计算（在 process_items 内完成）：**

```
score = base_score[source] + engagement_score(raw_data) + score_adjustment
```

**验证：** 手动构造几条 Item，调用 `process_items` 确认 LLM 返回正确分类和总结。

---

### Phase 4：用户追问

FTS5 搜索 + LLM 回答。

| 文件 | 内容 |
|---|---|
| `worldpulse/ask.py` | `AskService` 类，组合 FTS5 搜索 + LLM 调用 |

**AskService：**

```python
class AskService:
    def __init__(self, db: Database, processor: AIProcessor) -> None: ...

    async def ask(self, question: str) -> AskResult: ...
    # 1. db.search_items(question, days=7, limit=20) 搜索相关条目
    # 2. 无结果 → 返回 "没有找到相关数据"
    # 3. 有结果 → processor.answer_question(question, items)
    # 4. 返回 AskResult(answer=..., sources=[...])
```

**数据模型（加在 models.py）：**

```python
@dataclass
class AskResult:
    answer: str
    sources: list[Item]
    search_query: str
```

**验证：** 先插入测试数据，调用 `ask()` 确认 FTS5 搜索和 LLM 回答正常。

---

### Phase 5：Telegram 推送

格式化消息 + 发送。

| 文件 | 内容 |
|---|---|
| `worldpulse/telegram_bot.py` | `TelegramBot` 类，消息格式化 + 推送 |

**TelegramBot：**

```python
class TelegramBot:
    def __init__(self, config: TelegramConfig, http_client: httpx.AsyncClient) -> None: ...

    async def send_daily_report(self, insight: DailyInsight, top_items: list[Item]) -> None: ...
    # 格式化每日报告（概要 + 趋势 + Top 15 动态），发送到 Telegram

    async def send_message(self, text: str) -> None: ...
    # 发送纯文本消息
```

使用 httpx 直接调用 Telegram Bot API（`POST https://api.telegram.org/bot{token}/sendMessage`），不依赖 python-telegram-bot 框架以保持轻量。

**推送格式：** 见设计文档 6.4 节。

**验证：** 调用 `send_message` 发送一条测试消息到 Telegram。

---

### Phase 6：Web 展示

FastAPI 应用 + Jinja2 模板。

| 文件 | 内容 |
|---|---|
| `worldpulse/web/__init__.py` | 空 |
| `worldpulse/web/app.py` | FastAPI 路由定义 |
| `worldpulse/web/templates/index.html` | 主页面模板 |
| `worldpulse/web/static/style.css` | 样式 |

**app.py 路由：**

```python
def create_app(db: Database, ask_service: AskService) -> FastAPI: ...

# GET /              → 渲染 index.html（分类 Tab + items + insight + 追问框）
# GET /api/items     → JSON，?category=&date=&limit=
# GET /api/insights  → JSON，最近 N 条 insights
# GET /api/insights/{date} → JSON，指定日期 insight
# POST /api/ask      → JSON，{"question": "..."} → {"answer": "...", "sources": [...]}
```

**index.html 包含：**
- 分类 Tab 导航（All + 9 个分类）
- Items 列表（标题、来源、时间、AI 总结、原文链接）
- Daily Insight 区域
- 底部追问输入框 + 回答展示区
- 使用 fetch() 调用 API，无前端框架

**验证：** 启动 FastAPI，浏览器访问确认页面渲染正常，各 API 返回正确数据。

---

### Phase 7：调度 + 入口 + Docker

APScheduler 调度 + 启动入口 + 容器化。

| 文件 | 内容 |
|---|---|
| `worldpulse/scheduler.py` | `Scheduler` 类，管理定时任务 |
| `run.py` | 入口：初始化所有组件，启动时立即采集，启动调度器 + Web 服务 |
| `Dockerfile` | Python 3.11-slim 镜像 |
| `docker-compose.yaml` | 一键部署配置 |

**scheduler.py：**

```python
class Scheduler:
    def __init__(self, db: Database, collectors: list[BaseCollector],
                 processor: AIProcessor, telegram: TelegramBot,
                 config: ScheduleConfig) -> None: ...

    async def collect_and_process(self) -> None: ...
    # 并发采集 → 去重 → 入库 → AI 处理

    async def generate_and_push(self) -> None: ...
    # 生成 daily insight → Telegram 推送

    def start(self) -> None: ...
    # 注册定时任务 + 启动 scheduler
```

**run.py 启动流程：**

```
1. 加载 config.yaml
2. 初始化 Database（建表）
3. 初始化所有组件（collectors, processor, ask_service, telegram_bot）
4. 创建 FastAPI app
5. 立即执行一次 collect_and_process()
6. 启动 APScheduler
7. 启动 uvicorn（FastAPI）
```

**验证：**
- `python run.py` 启动后检查采集日志
- 访问 `http://localhost:8080` 确认页面
- `docker compose up` 确认容器部署

---

## 依赖关系

```
Phase 1（骨架）
    ↓
Phase 2（采集器）─── Phase 3（AI 处理）
    ↓                      ↓
    └───────┬──────────────┘
            ↓
    Phase 4（追问）─── Phase 5（Telegram）
            ↓                ↓
            └───────┬────────┘
                    ↓
            Phase 6（Web）
                    ↓
            Phase 7（调度 + Docker）
```

Phase 2 和 Phase 3 可以并行开发。Phase 4、5 依赖 2+3。Phase 6 整合所有 API。Phase 7 串联一切。

---

## 依赖清单

```toml
[project]
name = "worldpulse"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "apscheduler>=3.10",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
]
```

注意：移除了 `python-telegram-bot`，改用 httpx 直接调用 Telegram Bot API，减少依赖。
