# OpenClaw 自动化 AI 资讯扫描器

<img width="1103" height="820" alt="image" src="https://github.com/user-attachments/assets/a39fe3a3-0468-4f67-ac08-0080b4ebbd4a" />

一套运行在 OpenClaw 定时任务中的 AI 资讯自动化流水线 —— 同时扫描 5 个来源，对文章评分去重、抓取全文，最终由 Gemini Flash 按分类整理成每日资讯简报。

**示例输出：** [newsroom-run-20260317-141349.html](assets/newsroom-run-20260317-141349.html)

---

## 与 OpenClaw 的集成方式

```
OpenClaw Gateway
├── Cron 定时任务（例如每 2 小时）
│   └── 执行 news_scan_deduped.sh
│       ├── 抓取 5 个来源（RSS、Reddit、Twitter、GitHub、Tavily）
│       ├── 通过 quality_score.py 评分 + 去重
│       ├── 通过 enrich_top_articles.py 补充全文
│       └── 通过 llm_editor.py 进行 Gemini Flash AI 策编
│
├── Agent 格式化输出并推送到频道（飞书、Telegram、Slack 等）
│
├── 每晚 Cron（可选）
│   └── 执行 update_editorial_profile.py，从你的采纳/跳过记录中学习偏好
│
└── memory/ 目录（持久化记忆）
    ├── editorial_profile.md        ← LLM 编辑器读取此文件作为选题指导
    ├── editorial_decisions.md      ← 你的采纳/跳过记录
    ├── scanner_presented.md        ← 自动记录：每次呈现了哪些文章
    ├── news_log.md                 ← 已发布文章（用于去重）
    ├── last_scan_candidates.txt    ← "再来 10 条"功能的持久化候选列表
    └── github_trending_state.json  ← GitHub Star 增速追踪状态
```

**核心集成要点：**

1. 脚本存放于 `~/.openclaw/workspace/scripts/` —— OpenClaw 标准脚本目录
2. 记忆文件存放于 `~/.openclaw/workspace/memory/` —— 跨会话持久化
3. Cron 任务使用 `sessionTarget: "isolated"`，每次扫描获得干净的独立会话
4. Agent 负责编排流水线；实际 AI 策编通过 Gemini Flash API 直接调用
5. 推送由 OpenClaw 的频道系统处理

> **不使用 OpenClaw？** 脚本也可以独立运行 —— 直接用系统 cron 或命令行执行 `./news_scan_deduped.sh` 即可。

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    news_scan_deduped.sh                          │
│                       （主编排器）                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [1] RSS 订阅源        ──→  filter_ai_news.sh  （25 个 Feed）    │
│  [2] Reddit JSON API  ──→  fetch_reddit_news.py（13 个社区）    │
│  [3] Twitter/X (bird) ──→  scan_twitter_ai.sh                   │
│      Twitter/X (API)  ──→  fetch_twitter_api.py                 │
│  [4] GitHub           ──→  github_trending.py                   │
│  [5] Tavily 网络搜索  ──→  fetch_web_news.py  （5 个查询）      │
│                                                                  │
│  所有来源均为尽力而为 —— 单个来源失败不会中断整条流水线           │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  quality_score.py       → 评分 + 去重（标题相似度 80% 阈值）     │
│                           输出：最多 500 条评分候选              │
│                                                                  │
│  enrich_top_articles.py → 抓取全文（优先 CF Markdown，HTML 兜底）│
│                                                                  │
│  llm_editor.py          → Gemini Flash AI 策编                  │
│                           读取 editorial_profile.md 作为指导    │
│                           对比 news_log.md 避免重复推送          │
│                           输出：按板块分类的 JSON 结构化结果     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 前置条件

### 必须

- **OpenClaw** v2026.2.23+
- **Python 3.9+** —— 所有脚本仅使用标准库，无需 pip 安装额外依赖
- **blogwatcher** —— RSS 订阅扫描工具。安装方式：`brew install blogwatcher`，或通过 OpenClaw 技能引导安装：[openclaw-skill-blogwatcher](https://github.com/RainL150/openclaw-skill-blogwatcher)

### API 密钥

| 密钥 | 是否必须 | 用途 | 免费额度 |
|------|---------|------|---------|
| `GEMINI_API_KEY` | 必须 | Gemini Flash LLM 策编 | Google AI Studio 免费额度慷慨 |
| `OPENROUTER_API_KEY` | 与 Gemini 二选一 | 通过 OpenRouter 调用 200+ 模型作为备选 | 注册赠送免费额度 |
| `GH_TOKEN` | 建议配置 | GitHub API（5000 次/小时 vs 未认证 60 次/小时） | GitHub 个人访问令牌（免费） |
| `TAVILY_API_KEY` | 可选 | Tavily 网络搜索，补充突发新闻 | 每月 1000 次查询免费 |
| `TWITTERAPI_IO_KEY` | 可选 | twitterapi.io 关键词搜索 | 付费（约 $10/月） |

### 可选工具

- **bird** —— Twitter/X 命令行工具，供 `scan_twitter_ai.sh` 使用。安装：`npm install -g @steipete/bird` 或 `brew install steipete/tap/bird`。若未安装，Twitter bird CLI 数据源会被自动跳过，不影响其他来源。
- **setup_bird_auth.sh** —— 一次性辅助脚本，从 Chrome 读取 Twitter Cookie 并写入 `.env`，彻底避免 macOS 钥匙串弹窗。执行一次即可：`bash scripts/setup_bird_auth.sh`。

---

## 安装步骤

### 第一步：复制脚本

```bash
cp scripts/*.sh scripts/*.py ~/.openclaw/workspace/scripts/
chmod +x ~/.openclaw/workspace/scripts/news_scan_deduped.sh
chmod +x ~/.openclaw/workspace/scripts/filter_ai_news.sh
chmod +x ~/.openclaw/workspace/scripts/scan_twitter_ai.sh
```

### 第二步：配置 RSS 订阅源

安装 blogwatcher 并添加订阅源。推荐入门订阅列表：

```bash
# 一线电讯社（Tier 1）
blogwatcher add "Reuters Tech" "https://www.reuters.com/technology/rss"
blogwatcher add "Axios AI" "https://api.axios.com/feed/top/technology"

# 科技媒体（Tier 2）
blogwatcher add "TechCrunch AI" "https://techcrunch.com/category/artificial-intelligence/feed/"
blogwatcher add "The Verge" "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
blogwatcher add "THE DECODER" "https://the-decoder.com/feed/"
blogwatcher add "Ars Technica" "https://feeds.arstechnica.com/arstechnica/technology-lab"
blogwatcher add "VentureBeat AI" "https://venturebeat.com/category/ai/feed/"
blogwatcher add "Wired AI" "https://www.wired.com/feed/tag/ai/latest/rss"
blogwatcher add "MIT Tech Review" "https://www.technologyreview.com/feed/"

# AI 公司博客（Tier 1-2）
blogwatcher add "OpenAI Blog" "https://openai.com/blog/rss.xml"
blogwatcher add "Google AI Blog" "https://blog.google/technology/ai/rss/"
blogwatcher add "Hugging Face Blog" "https://huggingface.co/blog/feed.xml"

# 博主 & 周刊（Tier 2-3）
blogwatcher add "Simon Willison" "https://simonwillison.net/atom/everything/"
blogwatcher add "Bens Bites" "https://www.bensbites.com/feed"
```

添加完成后，将 Feed 名称同步更新到 `filter_ai_news.sh` 中的 `SOURCE_TIERS` 字典。

### 第三步：配置编辑画像

```bash
mkdir -p ~/.openclaw/workspace/memory
cp config/editorial_profile_template.md ~/.openclaw/workspace/memory/editorial_profile.md
```

编辑 `editorial_profile.md`，填写你的频道选题偏好：

- 哪些话题必选
- 哪些话题通常跳过
- 各来源的可信度排名
- 选题规则

此文件在每次扫描时都会被 LLM 编辑器读取，直接影响选题结果。

### 第四步：配置环境变量

**推荐方式：`.env` 文件**（手动执行和定时任务均生效）

`news_scan_deduped.sh` 启动时会自动加载 `~/.openclaw/workspace/.env`，确保 cron 定时任务和交互式 shell 的环境变量完全一致，不再出现"手动跑成功、定时任务报错"的问题。

```bash
# ~/.openclaw/workspace/.env
GEMINI_API_KEY=your-key
GH_TOKEN=your-token
TAVILY_API_KEY=your-key
TWITTERAPI_IO_KEY=your-key

# Twitter/X bird CLI 认证（由 setup_bird_auth.sh 自动写入）
AUTH_TOKEN=your-auth-token
CT0=your-ct0-token

# LLM 编辑器参数（可选）
MIN_SCORE_THRESHOLD=60      # 文章最低分数阈值（默认 60）
SECTION_MAX_ITEMS=40        # 每个板块最多文章数（默认 40）
LLM_BATCH_SIZE=30           # LLM 批次大小（默认 30）

# 输出文件设置（可选）
NEWSROOM_OUTPUT_DIR=/Users/you/.openclaw/workspace/outputs
NEWSROOM_TZ=Asia/Shanghai   # 输出文件时间戳使用的时区
NEWSROOM_HTML_ENABLED=1     # 是否生成 HTML 报告（默认 1）
```

> `.env` 已写入 `.gitignore`，不会被提交到代码仓库。

**默认输出文件：**
- 原始归档：`$NEWSROOM_OUTPUT_DIR/newsroom-run-YYYYMMDD-HHMMSS.md`
- HTML 报告：`$NEWSROOM_OUTPUT_DIR/newsroom-run-YYYYMMDD-HHMMSS.html`

示例输出文件（可在浏览器中直接打开）：[newsroom-run-20260317-141349.html](assets/newsroom-run-20260317-141349.html)

### 第五步：创建 Cron 定时任务

基础配置（飞书推送，北京时间）：

```bash
openclaw cron add \
  --name "AI News Scan CN" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and archive the original output: bash ~/.openclaw/workspace/scripts/news_scan_deduped.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

如果希望在推送内容中附带归档文件路径（`.md` / `.html`），改用包装脚本：

```bash
openclaw cron add \
  --name "AI News Scan CN With Files" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and show archived file paths: bash ~/.openclaw/workspace/scripts/news_scan_with_files.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

**上述 Cron 会做什么：**

- 每天北京时间 **09:40 / 11:40 / 13:40 / 15:40 / 17:40 / 19:40 / 21:40** 触发
- 将流水线文本输出推送到飞书群
- 每次运行生成两个归档文件：
  - `newsroom-run-YYYYMMDD-HHMMSS.md` —— 原始标准输出归档
  - `newsroom-run-YYYYMMDD-HHMMSS.html` —— 完整 HTML 报告
- 在输出中打印这两个文件的 `file://` 路径，便于 Agent 或人工二次转发

> **注意：** `.md`/`.html` 文件是否作为附件自动推送到飞书，取决于你的 OpenClaw 通道配置。最低限度下，文件路径和文本摘要会出现在群消息中。

调整频率：`openclaw cron edit <job-id> --cron "0 */3 * * *"`

**关于模型选择：** 可省略 `--model` 参数，让 OpenClaw 使用 Agent 默认模型。实际 AI 策编始终由 `llm_editor.py` 通过 Gemini Flash API 直接调用，Cron 侧的编排模型不影响策编质量。

### 第六步：测试流水线

```bash
cd ~/.openclaw/workspace/scripts
./news_scan_deduped.sh
```

正常输出示例：

```
═══════════════════════════════════════════════════════════
  News Scanner v2 (四板块模式)
═══════════════════════════════════════════════════════════

📰 [1/5] Scanning RSS feeds...
  ✅ Extracted 12 new RSS articles
🔴 [2/5] Scanning Reddit (JSON API)...
  ✅ Found 45 Reddit posts (score-filtered)
...

📄 归档文件已生成：
   file:///Users/rainless/.openclaw/workspace/outputs/newsroom-run-20260317-141349.md
🌐 HTML 报告已生成：
   file:///Users/rainless/.openclaw/workspace/outputs/newsroom-run-20260317-141349.html
```

HTML 报告示例效果见：[assets/newsroom-run-20260317-141349.html](assets/newsroom-run-20260317-141349.html)

---

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `news_scan_deduped.sh` | 主编排器 —— 依序调用所有来源，串联评分/富化/LLM 环节 |
| `filter_ai_news.sh` | RSS 关键词过滤，含词边界匹配；分配来源等级 |
| `fetch_reddit_news.py` | Reddit 公开 JSON API；13 个社区，分数阈值过滤，Flair 过滤，3 并发 |
| `scan_twitter_ai.sh` | bird CLI；三级账号体系（官方账号、记者爆料人、CEO） |
| `setup_bird_auth.sh` | 一次性辅助脚本：从 Chrome 提取 Twitter Token 写入 `.env`，避免 macOS 钥匙串反复弹窗 |
| `fetch_twitter_api.py` | twitterapi.io 关键词搜索；互动量过滤（50+ 赞或 5000+ 粉丝） |
| `github_trending.py` | GitHub 新兴仓库（7 天内、50+ Stars）、Star 增速追踪、16 个核心 AI 仓库的 Release 监控 |
| `fetch_web_news.py` | Tavily 网络搜索；5 个查询、2 天新鲜度过滤、跳过 RSS 已覆盖的域名 |
| `quality_score.py` | 按来源等级、关键词、突发信号评分；标题相似度 80% 去重 |
| `enrich_top_articles.py` | 全文抓取（优先 CF Markdown，HTML 兜底）；跳过付费墙网站 |
| `llm_editor.py` | Gemini Flash 策编；四板块输出（模型 / 应用 / 基础设施 / 公司动态） |
| `update_editorial_profile.py` | 每晚运行；分析采纳/跳过规律，更新编辑画像 |
| `news_scan_with_files.sh` | 主编排器包装脚本 —— 在输出末尾附加归档文件路径 |

---

## 目录结构

```
openclaw-newsroom/
├── README.md                              # 英文说明
├── README.zh.md                           # 中文说明（本文件）
├── scripts/
│   ├── news_scan_deduped.sh
│   ├── news_scan_with_files.sh
│   ├── filter_ai_news.sh
│   ├── fetch_reddit_news.py
│   ├── scan_twitter_ai.sh
│   ├── setup_bird_auth.sh
│   ├── fetch_twitter_api.py
│   ├── github_trending.py
│   ├── fetch_web_news.py
│   ├── quality_score.py
│   ├── enrich_top_articles.py
│   ├── llm_editor.py
│   └── update_editorial_profile.py
├── assets/
│   ├── newsroom-run-20260317-141349.html  # HTML 报告示例
│   └── ...（图片等静态资源）
├── outputs/                               # 本地运行生成（不提交 git）
│   ├── newsroom-run-YYYYMMDD-HHMMSS.md
│   └── newsroom-run-YYYYMMDD-HHMMSS.html
└── config/
    └── editorial_profile_template.md      # 编辑画像模板，按需自定义
```

---

## 流水线流程图

```
RSS（25 个 Feed）────────┐
Reddit（13 个社区）──────┤
Twitter（bird + API）────┼──→ quality_score.py ──→ enrich_top_articles.py ──→ llm_editor.py ──→ 输出
GitHub（趋势 + Release）─┤        （最多 500 条）        （最多 500 条）          （Gemini Flash）
Tavily（5 个查询）───────┘
```

典型一次运行：约 100 条原始文章 → 数百条评分候选 → 四板块 LLM 精选结果 → `.md` + `.html` 归档

---

## 费用参考

| 组件 | 月均费用 | 备注 |
|------|---------|------|
| Gemini Flash API | ~$2–3 | 约每天 7 次调用，每次约 30K tokens |
| Tavily API | 免费 | 每月 1000 次查询，典型用量够用 |
| GitHub API | 免费 | 个人访问令牌 |
| twitterapi.io | ~$10 | 可选，bird CLI 免费 |
| OpenClaw Cron 模型 | 按用量 | 取决于所选模型 |
| **合计** | **约 $5/月** | 不含 twitterapi.io |

---

## 自定义指南

**添加 RSS 订阅源：** 向 blogwatcher 添加 Feed 后，在 `filter_ai_news.sh` 的 `SOURCE_TIERS` 中同步添加名称。

**添加 Reddit 社区：** 编辑 `fetch_reddit_news.py` 的 `SUBREDDITS` 列表：
```python
{"sub": "YourSubreddit", "sort": "hot", "limit": 25, "min_score": 30, "flairs": ["News"]},
```

**添加 Twitter 监控账号：** 编辑 `scan_twitter_ai.sh` 中的 `OFFICIAL_ACCOUNTS`、`REPORTER_ACCOUNTS` 或 `CEO_ACCOUNTS`。

**添加 GitHub Release 仓库：** 在 `github_trending.py` 的 `RELEASE_REPOS` 中添加：
```python
"owner/repo-name",
```

**更换 LLM 模型：** 修改 `llm_editor.py` 中的 `GEMINI_MODEL`（推荐 Flash 系列以控制成本）。

---

## 常见问题排查

| 问题 | 解决方法 |
|------|---------|
| `GEMINI_API_KEY not set` | 写入 LaunchAgent plist 或在 Shell 中 export |
| Reddit 429（频率限制） | 正常现象，扫描间隔较短时会触发；减少社区数量或增大 `--hours` |
| Reddit 404 某个社区 | 该社区已私有或被隔离，从配置中移除 |
| `bird` CLI 找不到 | 安装 bird，或从主编排器中移除对 `scan_twitter_ai.sh` 的调用 |
| macOS 钥匙串每次扫描都弹窗 | 执行一次 `bash scripts/setup_bird_auth.sh`，将 Token 缓存到 `.env` |
| Twitter 返回 0 条（Token 过期） | 重新执行 `bash scripts/setup_bird_auth.sh` 刷新 Token |
| 没有新文章 | RSS 订阅源暂无更新，等待新文章发布 |
| LLM 编辑器超时 | 增大 `llm_editor.py` 中的 `TIMEOUT_SEC` |
| 流水线运行太慢 | 增大 Cron 超时：`openclaw cron edit <id> --timeout 120` |
| GitHub 频率限制 | 配置 `GH_TOKEN`（5000 次/小时 vs 未认证 60 次/小时） |
| 重复文章过多 | 调低 `quality_score.py` 的 `--dedup-threshold`（默认 0.80） |

---

## 学习与反馈循环

系统会从你的编辑决策中持续学习：

1. **日常使用：** 扫描器呈现选题候选，你决定采纳或跳过。
2. **每晚：** `update_editorial_profile.py` 分析你的选题规律。
3. **下次扫描：** LLM 编辑器读取更新后的画像，自动调整选题偏好。

在 `~/.openclaw/workspace/memory/editorial_decisions.md` 中记录你的决策：

```
[2026-03-17T14:13:49+08:00] APPROVED | Story Title | https://url | category
[2026-03-17T14:13:49+08:00] SKIPPED  | Another Story | https://url | category
[2026-03-17T14:13:49+08:00] MANUAL_DRAFT | 我自己找到的文章 | https://url | category
```

---

## 许可证

MIT —— 随便用，用出好东西了告诉我一声。
