# World Pulse

AI 全球科技情报系统。自动采集、AI 分析、推送和展示全球科技动态。

## 功能

- **自动采集**：Hacker News、GitHub Trending、arXiv 三个数据源，定时抓取
- **AI 分析**：自动分类、总结、热度评分（支持任意 OpenAI 兼容 LLM）
- **每日 Insight**：自动生成每日科技情报摘要和趋势分析
- **Telegram 推送**：每天定时推送科技日报到 Telegram
- **Web 展示**：分类浏览情报，按热度排序
- **智能追问**：基于已采集数据回答问题（FTS5 全文搜索 + LLM）

## 快速开始

### 前置条件

- Python 3.11+

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd world-pulse

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .
```

### 配置

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`，至少配置以下项：

```yaml
llm:
  base_url: "https://api.openai.com/v1"  # 或任意兼容端点
  api_key: "sk-xxx"
  model: "gpt-4o-mini"

telegram:
  bot_token: "xxx"   # 可选，不配置则跳过推送
  chat_id: "xxx"
```

### 运行

```bash
python run.py
```

启动后会立即采集一次数据，之后按配置的间隔定时采集。Web 界面默认访问 `http://localhost:8080`。

## Docker 部署

```bash
# 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml...

# 启动
docker compose up -d
```

访问 `http://localhost:8080`。

## 配置说明

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `llm.base_url` | LLM API 端点 | `https://api.openai.com/v1` |
| `llm.api_key` | API 密钥 | - |
| `llm.model` | 模型名称 | `gpt-4o-mini` |
| `telegram.bot_token` | Telegram Bot Token | - |
| `telegram.chat_id` | 推送目标 Chat ID | - |
| `sources.hackernews.enabled` | 启用 HN 采集 | `true` |
| `sources.hackernews.top_n` | HN 采集条数 | `30` |
| `sources.github_trending.enabled` | 启用 GitHub 采集 | `true` |
| `sources.arxiv.enabled` | 启用 arXiv 采集 | `true` |
| `sources.arxiv.categories` | arXiv 分类过滤 | `["cs.AI", "cs.CL", "cs.LG"]` |
| `sources.arxiv.max_results` | arXiv 最大条数 | `20` |
| `schedule.collect_interval_minutes` | 采集间隔（分钟） | `120` |
| `schedule.push_time` | 每日推送时间 | `"09:00"` |
| `web.host` | Web 监听地址 | `"0.0.0.0"` |
| `web.port` | Web 端口 | `8080` |

## API

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 主页面 |
| `/api/items` | GET | 情报列表，支持 `?category=&date=&limit=` |
| `/api/insights` | GET | 每日洞察列表 |
| `/api/insights/{date}` | GET | 指定日期洞察 |
| `/api/ask` | POST | 智能追问，Body: `{"question": "..."}` |

## 分类

系统自动将情报分为 9 个类别：

AI Research / Open Source / LLM & Models / AI Agents / Infrastructure / Chips & Hardware / Startups & Funding / Dev Tools / Automation

## 项目结构

```
worldpulse/
├── config.py          # 配置加载
├── db.py              # SQLite + FTS5
├── models.py          # 数据模型
├── collectors/        # 数据采集器
├── processor.py       # AI 处理（分类/总结/打分）
├── ask.py             # 智能追问
├── telegram_bot.py    # Telegram 推送
├── scheduler.py       # 定时调度
└── web/               # Web 展示
```

## License

MIT
