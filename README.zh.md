# OpenClaw Newsroom

这是一个用于 OpenClaw 的 AI 资讯 newsroom skill，负责多源抓取、评分去重、全文补充、LLM 策编，并输出可归档的 Markdown 与 HTML 简报。

**示例报告：** [newsroom-run-20260317-141349.html](assets/newsroom-run-20260317-141349.html)

## 这个 Skill 能做什么

- 同时扫描 RSS、Reddit、X/Twitter、GitHub、Tavily
- 在策编前先做评分与去重
- 为高价值候选补充更多正文内容
- 产出适合频道投递的 Markdown 和 HTML 归档
- 维护本地 newsroom 记忆，如编辑画像与已呈现记录

## 推荐安装形态

推荐将整个仓库作为 skill 安装，而不是散装复制脚本：

```bash
~/.openclaw/workspace/skills/openclaw-newsroom/
```

只有当技能根目录存在 [`SKILL.md`](/Users/rainless/Desktop/project/claw/openclaw-newsroom/SKILL.md) 时，OpenClaw 才会把它识别为正式 skill。

## 入口脚本

如果你希望输出里带上归档文件路径，优先使用包装脚本：

```bash
bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_with_files.sh
```

如果你只需要原始简报文本，可直接运行主流水线：

```bash
bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_deduped.sh
```

## 快速开始

1. 安装 skill：

```bash
mkdir -p ~/.openclaw/workspace/skills
cp -R openclaw-newsroom ~/.openclaw/workspace/skills/openclaw-newsroom
chmod +x ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/*.sh
```

2. 生成本地配置：

```bash
cp ~/.openclaw/workspace/skills/openclaw-newsroom/.env.example \
  ~/.openclaw/workspace/skills/openclaw-newsroom/.env
```

3. 初始化编辑画像：

```bash
mkdir -p ~/.openclaw/workspace/skills/openclaw-newsroom/memory
cp ~/.openclaw/workspace/skills/openclaw-newsroom/config/editorial_profile_template.md \
  ~/.openclaw/workspace/skills/openclaw-newsroom/memory/editorial_profile.md
```

4. 手动跑一次：

```bash
cd ~/.openclaw/workspace/skills/openclaw-newsroom
bash scripts/news_scan_with_files.sh
```

## 依赖说明

必须：

- OpenClaw `v2026.2.23+`
- Python `3.9+`
- 至少一条 LLM 通路：`GEMINI_API_KEY` 或 `OPENROUTER_API_KEY`

建议：

- `blogwatcher`，保证 RSS 覆盖
- `GH_TOKEN`，提升 GitHub API 限额

可选：

- `TAVILY_API_KEY`，补充网页搜索
- `TWITTERAPI_IO_KEY`，补充关键词推文搜索
- `bird` CLI，补充账号维度的 X/Twitter 扫描

## 运行约定

- 默认输出写入 `outputs/`
- 默认记忆写入 `memory/`
- Shell 入口会自动加载同级 `.env`
- 各数据源失败按尽力而为处理，不应让整条流水线中断
- `llm_editor.py` 失败时，流水线仍可能以 raw top articles fallback 方式完成

## Cron 示例

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

## 仓库结构

```text
openclaw-newsroom/
├── SKILL.md
├── agents/openai.yaml
├── config/editorial_profile_template.md
├── scripts/
├── assets/
└── references/
```

## 详细参考

- 英文运维说明：[references/ops.md](/Users/rainless/Desktop/project/claw/openclaw-newsroom/references/ops.md)
- 中文运维说明：[references/ops.zh.md](/Users/rainless/Desktop/project/claw/openclaw-newsroom/references/ops.zh.md)
- 技能元信息：[SKILL.md](/Users/rainless/Desktop/project/claw/openclaw-newsroom/SKILL.md)
- UI 元数据：[agents/openai.yaml](/Users/rainless/Desktop/project/claw/openclaw-newsroom/agents/openai.yaml)

## 补充说明

- 旧的 `workspace/scripts` 复制方案仍可运行，但不再是推荐发布形态。
- 运行期产物已经通过 [`.gitignore`](/Users/rainless/Desktop/project/claw/openclaw-newsroom/.gitignore) 排除。
