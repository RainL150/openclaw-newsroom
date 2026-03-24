# 运维说明

## 安装方式

推荐以 skill 形式安装：

```bash
mkdir -p ~/.openclaw/workspace/skills
cp -R openclaw-newsroom ~/.openclaw/workspace/skills/openclaw-newsroom
chmod +x ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/*.sh
```

旧的复制脚本方案也仍可使用：

```bash
cp scripts/*.sh scripts/*.py ~/.openclaw/workspace/scripts/
chmod +x ~/.openclaw/workspace/scripts/news_scan_deduped.sh
chmod +x ~/.openclaw/workspace/scripts/filter_ai_news.sh
chmod +x ~/.openclaw/workspace/scripts/scan_twitter_ai.sh
```

## 编辑画像

```bash
mkdir -p ~/.openclaw/workspace/skills/openclaw-newsroom/memory
cp ~/.openclaw/workspace/skills/openclaw-newsroom/config/editorial_profile_template.md \
  ~/.openclaw/workspace/skills/openclaw-newsroom/memory/editorial_profile.md
```

建议在画像中定义：

- 必选话题
- 跳过话题
- 来源可信度偏好
- 选题规则

## 环境变量

在 skill 根目录旁创建 `.env`：

```bash
cp ~/.openclaw/workspace/skills/openclaw-newsroom/.env.example \
  ~/.openclaw/workspace/skills/openclaw-newsroom/.env
```

常见配置如下：

```bash
GEMINI_API_KEY=your-key
GH_TOKEN=your-token
TAVILY_API_KEY=your-key
TWITTERAPI_IO_KEY=your-key

MIN_SCORE_THRESHOLD=60
SECTION_MAX_ITEMS=40
LLM_BATCH_SIZE=30

NEWSROOM_OUTPUT_DIR=/Users/you/.openclaw/workspace/skills/openclaw-newsroom/outputs
NEWSROOM_MEMORY_DIR=/Users/you/.openclaw/workspace/skills/openclaw-newsroom/memory
NEWSROOM_TZ=Asia/Shanghai
NEWSROOM_HTML_ENABLED=1
```

至少要配置一条 LLM 通路：

- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`

## RSS 配置

安装 `blogwatcher` 后，添加与你在 `scripts/filter_ai_news.sh` 中维护的名称一致的订阅源。

可直接用这组起步订阅：

```bash
blogwatcher add "Reuters Tech" "https://www.reuters.com/technology/rss"
blogwatcher add "Axios AI" "https://api.axios.com/feed/top/technology"
blogwatcher add "TechCrunch AI" "https://techcrunch.com/category/artificial-intelligence/feed/"
blogwatcher add "The Verge" "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
blogwatcher add "THE DECODER" "https://the-decoder.com/feed/"
blogwatcher add "Ars Technica" "https://feeds.arstechnica.com/arstechnica/technology-lab"
blogwatcher add "VentureBeat AI" "https://venturebeat.com/category/ai/feed/"
blogwatcher add "Wired AI" "https://www.wired.com/feed/tag/ai/latest/rss"
blogwatcher add "MIT Tech Review" "https://www.technologyreview.com/feed/"
blogwatcher add "OpenAI Blog" "https://openai.com/blog/rss.xml"
blogwatcher add "Google AI Blog" "https://blog.google/technology/ai/rss/"
blogwatcher add "Hugging Face Blog" "https://huggingface.co/blog/feed.xml"
blogwatcher add "Simon Willison" "https://simonwillison.net/atom/everything/"
blogwatcher add "Bens Bites" "https://www.bensbites.com/feed"
```

## 手动运行

```bash
cd ~/.openclaw/workspace/skills/openclaw-newsroom
bash scripts/news_scan_with_files.sh
```

## Cron 示例

原始主流水线：

```bash
openclaw cron add \
  --name "AI News Scan CN" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and archive the original output: bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_deduped.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

带归档文件路径的包装脚本：

```bash
openclaw cron add \
  --name "AI News Scan CN With Files" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and show archived file paths: bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_with_files.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

## 行为与故障说明

- 各数据源按尽力而为执行。
- 缺失 `blogwatcher`、`bird` 或可选 API key 会降低覆盖，但不应中止整次扫描。
- `llm_editor.py` 可以单独失败；此时流水线仍可能通过 raw fallback 完成。
- 包装脚本会在可用时输出 Markdown 与 HTML 归档文件的 `file://` 路径。
