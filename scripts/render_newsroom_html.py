#!/usr/bin/env python3
"""
根据 newsroom 结果（JSONL）渲染固定模板 HTML 页面。

用法：
  python3 render_newsroom_html.py \
    --input /tmp/newscan_picks.xxxxxx \
    --output ~/.openclaw/workspace/outputs/newsroom-latest.html \
    --title "OpenClaw Newsroom 简报"
"""

import argparse
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

SECTION_ORDER = [
    "模型层面（Model）",
    "应用层面（Application）",
    "基建层面（Infrastructure）",
    "公司层面（Company/Industry）",
]


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _section_key(sec: str) -> str:
    return (
        sec.replace("（", "_")
        .replace("）", "")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("(", "_")
        .replace(")", "")
    )


def parse_section_summary(text: str):
    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
    data = {
        "trend": "",
        "keywords": [],
        "theme": "",
        "problem": "",
        "directions": [],
    }
    mode = None
    for ln in lines:
        if ln.startswith("一句话总趋势"):
            data["trend"] = ln.split("：", 1)[-1].strip() if "：" in ln else ln
            mode = None
        elif ln.startswith("关键词"):
            mode = "keywords"
        elif ln.startswith("最大主题"):
            data["theme"] = ln.split("：", 1)[-1].strip() if "：" in ln else ln
            mode = None
        elif ln.startswith("核心问题"):
            data["problem"] = ln.split("：", 1)[-1].strip() if "：" in ln else ln
            mode = None
        elif ln.startswith("典型方向"):
            mode = "directions"
        elif ln.startswith("-"):
            item = ln.lstrip("- ").strip()
            if mode == "keywords":
                data["keywords"].append(item)
            elif mode == "directions":
                data["directions"].append(item)
    return data


def build_html(title: str, rows):
    rows.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    grouped = OrderedDict((k, []) for k in SECTION_ORDER)
    for r in rows:
        sec = r.get("section", "应用层面（Application）")
        grouped.setdefault(sec, []).append(r)

    visible_sections = [s for s in SECTION_ORDER if grouped.get(s)]
    if not visible_sections:
        visible_sections = ["应用层面（Application）"]
        grouped[visible_sections[0]] = []

    tab_buttons = []
    section_blocks = []

    for idx, sec in enumerate(visible_sections):
        items = grouped.get(sec, [])
        active = "true" if idx == 0 else "false"
        panel_class = "panel active" if idx == 0 else "panel"
        sec_id = _section_key(sec)

        summary = ""
        for it in items:
            s = (it.get("section_summary") or "").strip()
            if s:
                summary = s
                break
        ss = parse_section_summary(summary)

        tab_buttons.append(
            f'<button class="tab-btn" data-target="panel-{esc(sec_id)}" aria-selected="{active}">{esc(sec)} <span class="count">{len(items)}</span></button>'
        )

        cards = []
        for it in items:
            title_txt = esc(str(it.get("title", "(no title)")))
            title_zh = esc(str(it.get("title_zh", "")))
            url = esc(str(it.get("url", "")))
            source = esc(str(it.get("source", "unknown")))
            category = esc(str(it.get("category", "other")))
            channel = esc(str(it.get("channel", "RSS")))
            score = esc(str(it.get("score", 0)))
            summary_txt = esc(str(it.get("summary", "")))
            rank = esc(str(it.get("rank", "-")))
            
            # 如果有中文标题，使用中文标题作为主标题，英文标题作为副标题
            if title_zh:
                main_title = title_zh
                subtitle = f'<div class="subtitle">{title_txt}</div>'
            else:
                main_title = title_txt
                subtitle = ''

            cards.append(
                f"""
<article class=\"card\">
  <div class=\"card-top\">
    <span class=\"badge\">#{rank}</span>
    <span class=\"badge score\">Score {score}</span>
    <span class=\"badge cat\">{category}</span>
    <span class=\"badge ch\">{channel}</span>
  </div>
  <h3>{main_title}</h3>
  {subtitle}
  <p class=\"summary\">{summary_txt}</p>
  <div class=\"meta\">来源：{source}</div>
  <a class=\"link\" href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">查看原文 ↗</a>
</article>
"""
            )

        cards_html = "".join(cards) if cards else "<div class=\"empty\">本板块暂无内容</div>"
        kw_html = ''.join([f'<span class="k">{esc(k)}</span>' for k in ss['keywords']])
        dir_html = ''.join([f'<li>{esc(d)}</li>' for d in ss['directions']])
        summary_card = f"""
<div class=\"summary-card\">
  <div class=\"row\"><span class=\"label\">一句话总趋势</span><p>{esc(ss['trend'] or summary)}</p></div>
  <div class=\"row\"><span class=\"label\">关键词</span><div class=\"keywords\">{kw_html or '<span class="k">（暂无）</span>'}</div></div>
  <div class=\"row\"><span class=\"label\">最大主题</span><p>{esc(ss['theme'] or '（暂无）')}</p></div>
  <div class=\"row\"><span class=\"label\">核心问题</span><p>{esc(ss['problem'] or '（暂无）')}</p></div>
  <div class=\"row\"><span class=\"label\">典型方向</span><ul>{dir_html or '<li>（暂无）</li>'}</ul></div>
</div>
"""
        section_blocks.append(
            f"""
<section id=\"panel-{esc(sec_id)}\" class=\"{panel_class}\">
  <div class=\"section-head\">
    <h2>{esc(sec)}</h2>
    {summary_card}
  </div>
  <div class=\"grid\">{cards_html}</div>
</section>
"""
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{esc(title)}</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --line: #e5e7eb;
      --brand: #2563eb;
      --brand-soft: #dbeafe;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 22px; }}
    h1 {{ margin: 0; font-size: 30px; }}
    .sub {{ margin: 8px 0 16px; color: var(--muted); }}

    .tabs {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }}
    .tab-btn {{ border: 1px solid var(--line); background: #fff; color: #1f2937; padding: 9px 12px; border-radius: 999px; font-size: 14px; cursor: pointer; }}
    .tab-btn .count {{ margin-left: 6px; color: var(--muted); }}
    .tab-btn.active {{ background: var(--brand); color: #fff; border-color: var(--brand); }}
    .tab-btn.active .count {{ color: #e5edff; }}

    .panel {{ display: none; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 16px; box-shadow: 0 2px 10px rgba(15,23,42,.04); }}
    .panel.active {{ display: block; }}

    .section-head h2 {{ margin: 0 0 8px; font-size: 22px; }}
    .section-summary {{ margin: 0 0 14px; color: #374151; line-height: 1.8; white-space: pre-line; }}
    .summary-card {{ border: 1px solid #dbeafe; background: linear-gradient(180deg,#f8fbff,#f3f8ff); border-radius: 12px; padding: 12px; margin-bottom: 14px; }}
    .summary-card .row {{ margin: 7px 0; }}
    .summary-card .label {{ display: inline-block; font-size: 12px; color: #1d4ed8; background: #dbeafe; border-radius: 999px; padding: 2px 8px; margin-bottom: 6px; }}
    .summary-card p {{ margin: 4px 0 0; line-height: 1.75; }}
    .summary-card ul {{ margin: 6px 0 0 18px; }}
    .keywords {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
    .keywords .k {{ font-size: 12px; padding: 3px 8px; border-radius: 999px; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; }}

    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid var(--line); border-radius: 12px; padding: 12px; background: #fff; transition: all .18s ease; }}
    .card:hover {{ transform: translateY(-1px); box-shadow: 0 8px 20px rgba(37,99,235,.08); border-color: #bfdbfe; }}
    .card-top {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
    .badge {{ background: #f3f4f6; color: #374151; border-radius: 999px; font-size: 12px; padding: 2px 8px; }}
    .badge.score {{ background: var(--brand-soft); color: #1e40af; }}
    .badge.cat {{ background: #ecfeff; color: #0e7490; }}
    .badge.ch {{ background: #ecfdf5; color: #065f46; }}
    .card h3 {{ margin: 0 0 4px; font-size: 16px; line-height: 1.45; }}
    .subtitle {{ margin: 0 0 8px; color: #6b7280; font-size: 13px; line-height: 1.4; font-style: italic; }}
    .summary {{ margin: 0 0 8px; color: #374151; line-height: 1.7; font-size: 14px; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 8px; }}
    .link {{ color: var(--brand); text-decoration: none; font-size: 14px; }}
    .empty {{ color: var(--muted); padding: 8px 2px; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>{esc(title)}</h1>
    <div class=\"sub\">生成时间：{now}</div>

    <div class=\"tabs\" id=\"tabs\">
      {''.join(tab_buttons)}
    </div>

    <div id=\"panels\">{''.join(section_blocks)}</div>
  </div>

  <script>
    (function() {{
      const tabs = Array.from(document.querySelectorAll('.tab-btn'));
      const panels = Array.from(document.querySelectorAll('.panel'));
      function activate(btn) {{
        const target = btn.getAttribute('data-target');
        tabs.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        panels.forEach(p => p.classList.remove('active'));
        const panel = document.getElementById(target);
        if (panel) panel.classList.add('active');
      }}
      tabs.forEach((btn, idx) => {{
        if (idx === 0) btn.classList.add('active');
        btn.addEventListener('click', () => activate(btn));
      }});
    }})();
  </script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="OpenClaw Newsroom 简报")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_jsonl(in_path)
    html = build_html(args.title, rows)
    out_path.write_text(html, encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
