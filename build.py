#!/usr/bin/env python3
"""把 content/*.md 构建成 site/ 下的静态网页。

用法：python3 build.py
依赖：pip install markdown
"""
import html
import re
import shutil
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("缺少 markdown 库：pip install markdown")

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
SITE = ROOT / "site"

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
TYPE_LABEL = {"思想": "新闻＋思想", "艺术": "新闻＋艺术", "仅新闻": "新闻"}
SECTION_CLASS = {"新闻": "news", "短讯": "brief", "今日思想": "reading", "今日艺术": "reading", "本周后续": "news"}


def parse(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path.name}: 缺少 --- 包围的头信息")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    for key in ("date", "type", "minutes", "lede"):
        if not meta.get(key):
            raise ValueError(f"{path.name}: 头信息缺少 {key}")
    if meta["type"] not in TYPE_LABEL:
        raise ValueError(f"{path.name}: type 只能是 思想 / 艺术 / 仅新闻")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
        raise ValueError(f"{path.name}: date 格式应为 YYYY-MM-DD")
    if path.stem != meta["date"]:
        raise ValueError(f"{path.name}: 文件名应与 date 一致")
    meta["lede"] = cn_quotes(meta["lede"])
    if "reading" in meta:
        meta["reading"] = cn_quotes(meta["reading"])
    return meta, m.group(2)


def cn_quotes(text: str) -> str:
    """把成对的英文双引号换成中文引号“”，逐行处理。"""
    out = []
    for line in text.split("\n"):
        n = 0
        buf = []
        for ch in line:
            if ch == '"':
                buf.append("“" if n % 2 == 0 else "”")
                n += 1
            else:
                buf.append(ch)
        out.append("".join(buf) if n % 2 == 0 else line)
    return "\n".join(out)


def render_body(md_text: str) -> str:
    md_text = cn_quotes(md_text)
    body = markdown.markdown(md_text, extensions=["extra", "sane_lists"], output_format="html")
    # 外链新窗口打开
    body = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', body)
    # “打开原文”按钮
    body = re.sub(r"<p>(<a [^>]+>)(打开原文|观看|收听)", r'<p class="cta">\1\2', body)
    # 单独一行的图片 + 下一段斜体 → figure
    body = re.sub(
        r"<p>(<img [^>]+>)</p>\s*<p><em>(.*?)</em></p>",
        r"<figure>\1<figcaption>\2</figcaption></figure>",
        body,
        flags=re.S,
    )
    body = re.sub(r"<p>(<img [^>]+>)</p>", r"<figure>\1</figure>", body)
    body = body.replace("<img ", '<img loading="lazy" ')
    # 以 h2 切分成 section
    parts = re.split(r"(<h2>.*?</h2>)", body)
    out = [parts[0]] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        heading = re.sub(r"<.*?>", "", parts[i]).strip()
        key = heading.split("·")[0].split(" ")[0].strip()
        cls = SECTION_CLASS.get(key, "misc")
        out.append(f'<section class="{cls}">{parts[i]}{parts[i + 1] if i + 1 < len(parts) else ""}</section>')
    return "\n".join(out)


def cn_date(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{int(y)}年{int(m)}月{int(dd)}日"


def weekday(d: str) -> str:
    import datetime as dt
    return WEEKDAYS[dt.date.fromisoformat(d).weekday()]


HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#111111" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="阅读小刊">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="icon" href="/icon-192.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<main class="page">
"""

FOOT = """</main>
</body>
</html>
"""


def masthead(link_home: bool) -> str:
    name = '<a href="/">阅读小刊</a>' if link_home else "阅读小刊"
    return f'<header class="masthead"><h1 class="name">{name}</h1></header>\n'


def issue_page(meta, body_html, prev_d, next_d) -> str:
    d = meta["date"]
    dateline = f'{cn_date(d)} · {weekday(d)} · {TYPE_LABEL[meta["type"]]} · 约{meta["minutes"]}分钟'
    nav = ['<nav class="issue-nav">']
    nav.append(f'<a href="/p/{prev_d}.html">← 前一期</a>' if prev_d else "<span></span>")
    nav.append('<a href="/archive.html">往期</a>')
    nav.append(f'<a href="/p/{next_d}.html">后一期 →</a>' if next_d else "<span></span>")
    nav.append("</nav>")
    return (
        HEAD.format(title=f"阅读小刊 · {cn_date(d)}", desc=html.escape(meta["lede"]))
        + masthead(True)
        + f'<p class="dateline">{dateline}</p>\n'
        + f'<p class="lede">{html.escape(meta["lede"])}</p>\n'
        + f'<article class="issue">{body_html}</article>\n'
        + "\n".join(nav)
        + FOOT
    )


def archive_page(issues) -> str:
    rows = []
    month = None
    for meta, _ in reversed(issues):
        d = meta["date"]
        ym = d[:7]
        if ym != month:
            if month:
                rows.append("</ol>")
            y, m = ym.split("-")
            rows.append(f'<h2 class="month">{int(y)}年{int(m)}月</h2><ol class="archive">')
            month = ym
        reading = meta.get("reading") or TYPE_LABEL[meta["type"]]
        rows.append(
            f'<li><a href="/p/{d}.html"><span class="a-date">{int(d[5:7])}月{int(d[8:])}日 {weekday(d)[-1]}</span>'
            f'<span class="a-title">{html.escape(reading)}</span></a></li>'
        )
    if month:
        rows.append("</ol>")
    return (
        HEAD.format(title="阅读小刊 · 往期", desc="阅读小刊全部往期")
        + masthead(True)
        + '<p class="dateline">往期</p>\n'
        + "\n".join(rows)
        + '\n<nav class="issue-nav"><span></span><a href="/">回到今天</a><span></span></nav>'
        + FOOT
    )


def main():
    files = sorted(CONTENT.glob("*.md"))
    if not files:
        sys.exit("content/ 里还没有刊物")
    issues = [parse(f) for f in files]
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "p").mkdir(parents=True)
    for f in STATIC.iterdir():
        shutil.copy(f, SITE / f.name)
    dates = [m["date"] for m, _ in issues]
    for i, (meta, body) in enumerate(issues):
        prev_d = dates[i - 1] if i > 0 else None
        next_d = dates[i + 1] if i + 1 < len(dates) else None
        page = issue_page(meta, render_body(body), prev_d, next_d)
        (SITE / "p" / f'{meta["date"]}.html').write_text(page, encoding="utf-8")
    latest_meta, latest_body = issues[-1]
    index = issue_page(latest_meta, render_body(latest_body), dates[-2] if len(dates) > 1 else None, None)
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / "archive.html").write_text(archive_page(issues), encoding="utf-8")
    print(f"已构建 {len(issues)} 期，最新：{latest_meta['date']}")


if __name__ == "__main__":
    main()
