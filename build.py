#!/usr/bin/env python3
"""把 content/*.md 构建成 site/ 下的静态网页，另外生成更新日志页和系列页。

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
CHANGELOG = ROOT / "更新日志.md"
SERIES_DIR = ROOT / "series"
# 系列页的顺序和播出日；文件名对应 series/ 里的大纲文件
SERIES_ORDER = [
    ("西方艺术史.md", "每周一"),
    ("交易与投资.md", "每周二、周六"),
    ("摄影.md", "每周三"),
    ("AI工具与方法.md", "每周四"),
    ("音乐史与古典音乐.md", "每周五；周日聆听"),
]
FOOT_LINKS = [("/", "今天"), ("/archive.html", "往期"), ("/series.html", "系列"), ("/changelog.html", "更新日志")]

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
TYPE_LABEL = {
    # 旧版（2026-09-28 及以前）
    "思想": "新闻＋思想", "艺术": "新闻＋艺术", "仅新闻": "新闻",
    # 新版：type 写当天的系列
    "西方艺术史": "系列·西方艺术史", "交易与投资": "系列·交易与投资", "摄影": "系列·摄影",
    "AI工具": "系列·AI工具与方法", "音乐史": "系列·音乐史", "周日": "周日·复盘与聆听",
}
SECTION_CLASS = {
    "新闻": "news", "要闻与解析": "news", "本周复盘": "news", "本周后续": "news",
    "短讯": "brief",
    "币市一页": "market", "币市周报": "market",
    "系列": "series", "周日聆听": "series",
    "今日思想": "reading", "今日艺术": "reading", "深度长文": "reading",
}


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
        raise ValueError(f"{path.name}: type 只能是 {' / '.join(TYPE_LABEL)}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
        raise ValueError(f"{path.name}: date 格式应为 YYYY-MM-DD")
    if path.stem != meta["date"]:
        raise ValueError(f"{path.name}: 文件名应与 date 一致")
    meta["lede"] = cn_quotes(meta["lede"])
    for key in ("reading", "series"):
        if key in meta:
            meta[key] = cn_quotes(meta[key])
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
    # 表格外包一层，窄屏可横向滚动
    body = re.sub(r"(<table>.*?</table>)", r'<div class="table-wrap">\1</div>', body, flags=re.S)
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


def site_foot(skip=()) -> str:
    links = "".join(f'<a href="{href}">{label}</a>' for href, label in FOOT_LINKS if href not in skip)
    return f'<nav class="site-foot">{links}</nav>\n'


def md_html(text: str) -> str:
    body = markdown.markdown(cn_quotes(text), extensions=["extra", "sane_lists"], output_format="html")
    return re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', body)


def short_date(d: str) -> str:
    return f"{int(d[5:7])}月{int(d[8:])}日"


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
        + "\n"
        + site_foot(skip={"/", "/archive.html"})
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
        reading = "｜".join(x for x in (meta.get("series"), meta.get("reading")) if x) or TYPE_LABEL[meta["type"]]
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
        + "\n"
        + site_foot(skip={"/archive.html"})
        + FOOT
    )


def changelog_page(md_text: str) -> str:
    body = re.sub(r"\A#\s+[^\n]*\n", "", md_text.lstrip())  # 标题由刊头和日期行代替
    return (
        HEAD.format(title="阅读小刊 · 更新日志", desc="阅读小刊的变化记录：栏目调整、系列开讲和讲完、网站改版")
        + masthead(True)
        + '<p class="dateline">更新日志</p>\n'
        + f'<article class="changelog">{md_html(body)}</article>\n'
        + site_foot(skip={"/changelog.html"})
        + FOOT
    )


def parse_series(path: Path) -> dict:
    """从 series/ 的大纲文件里读出名称、定位、讲目和进度表。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0].lstrip("#").strip()
    name = title.split("·", 1)[1].strip() if "·" in title else title
    blocks, current = {}, None
    for line in lines[1:]:
        if line.startswith("## "):
            current = line[3:].strip()
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line)
    items, unit = [], None
    outline = next((v for k, v in blocks.items() if "大纲" in k), [])
    for line in outline:
        if line.startswith("### "):
            unit = cn_quotes(line[4:].strip())
            continue
        m = re.match(r"(\d+)\.\s+(.+)", line.strip())
        if m:
            items.append({"n": int(m.group(1)), "title": cn_quotes(m.group(2).strip()), "unit": unit})
    done, listening = {}, []
    for line in blocks.get("进度", []):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        date = next((c for c in cells if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)), None)
        if not date:
            continue
        num = next((int(m.group(1)) for m in (re.fullmatch(r"第\s*(\d+)\s*讲", c) for c in cells) if m), None)
        if num is not None:
            done[num] = date
        elif any("聆听" in c for c in cells):
            piece = [c for c in cells if c and c != date and "聆听" not in c]
            listening.append((date, cn_quotes(piece[0]) if piece else "周日聆听"))
    # 网页只显示"简介"（写给所有读者）；"定位"是写给编辑的，不上网页
    intro_lines = [l for l in blocks.get("简介", []) if not l.startswith("网站系列页显示这一段")]
    intro = "\n".join(intro_lines).strip()
    return {"name": name, "intro": intro, "items": items, "done": done, "listening": listening}


def course_block(path: Path, when: str, issue_dates) -> str:
    s = parse_series(path)
    items, done = s["items"], s["done"]

    def title_html(it):
        d = done.get(it["n"])
        t = html.escape(it["title"])
        return f'<a href="/p/{d}.html">{t}</a>' if d in issue_dates else t

    nxt = next((it for it in items if it["n"] not in done), None)
    out = [
        f'<div class="course" id="{html.escape(path.stem)}">',
        f'<h2 class="course-name">{html.escape(s["name"])}</h2>',
        f'<p class="course-meta">{when} · 共 {len(items)} 讲 · 已刊 {len(done)} 讲</p>',
    ]
    if s["intro"]:
        out.append(f'<div class="course-intro">{md_html(s["intro"])}</div>')
    published = [it for it in items if it["n"] in done]
    if published:
        out.append('<ol class="course-list">')
        for it in published:
            out.append(
                f'<li class="done"><span class="n">第{it["n"]}讲</span><span class="t">{title_html(it)}</span>'
                f'<span class="d">{short_date(done[it["n"]])}</span></li>'
            )
        out.append("</ol>")
    if nxt:
        out.append(f'<p class="course-next">下一讲：第{nxt["n"]}讲　{html.escape(nxt["title"])}</p>')
    elif items:
        out.append('<p class="course-next">已全部讲完</p>')
    if s["listening"]:
        out.append('<p class="course-unit">周日聆听</p><ol class="course-list">')
        for d, piece in s["listening"]:
            t = html.escape(piece)
            t = f'<a href="/p/{d}.html">{t}</a>' if d in issue_dates else t
            out.append(f'<li><span class="t">{t}</span><span class="d">{short_date(d)}</span></li>')
        out.append("</ol>")
    out.append(f'<details class="course-outline"><summary>全部 {len(items)} 讲</summary>')
    opened, unit = False, None
    for it in items:
        if not opened or it["unit"] != unit:
            if opened:
                out.append("</ol>")
            unit = it["unit"]
            if unit:
                out.append(f'<p class="course-unit">{html.escape(unit)}</p>')
            out.append('<ol class="course-list">')
            opened = True
        cls = "done" if it["n"] in done else ("next" if nxt and it["n"] == nxt["n"] else "")
        out.append(f'<li class="{cls}"><span class="n">{it["n"]}</span><span class="t">{title_html(it)}</span></li>')
    if opened:
        out.append("</ol>")
    out.append("</details></div>")
    return "\n".join(out)


def series_page(issue_dates) -> str:
    blocks = []
    for fname, when in SERIES_ORDER:
        path = SERIES_DIR / fname
        if not path.exists():
            continue
        try:
            blocks.append(course_block(path, when, issue_dates))
        except Exception as e:
            print(f"警告：{fname} 没能放进系列页：{e}", file=sys.stderr)
    if not blocks:
        raise ValueError("series/ 里没有能读的系列文件")
    return (
        HEAD.format(title="阅读小刊 · 系列", desc="阅读小刊的连载系列：全部讲目和已经刊出的讲")
        + masthead(True)
        + '<p class="dateline">系列</p>\n'
        + '<p class="page-intro">阅读小刊自己写的连载课程，按星期轮换。已经刊出的讲可以直接点开读。</p>\n'
        + "\n".join(blocks)
        + "\n"
        + site_foot(skip={"/series.html"})
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
    # 更新日志页和系列页出错只警告，不挡住当天出刊
    extras = []
    if CHANGELOG.exists():
        try:
            (SITE / "changelog.html").write_text(changelog_page(CHANGELOG.read_text(encoding="utf-8")), encoding="utf-8")
            extras.append("更新日志")
        except Exception as e:
            print(f"警告：更新日志页没有生成：{e}", file=sys.stderr)
    try:
        (SITE / "series.html").write_text(series_page(set(dates)), encoding="utf-8")
        extras.append("系列")
    except Exception as e:
        print(f"警告：系列页没有生成：{e}", file=sys.stderr)
    extra = f"；另有{'、'.join(extras)}页" if extras else ""
    print(f"已构建 {len(issues)} 期，最新：{latest_meta['date']}{extra}")


if __name__ == "__main__":
    main()
