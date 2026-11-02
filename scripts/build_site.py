"""data/ と content/ から静的サイトを _site/ に生成する。"""
import csv
import glob
import html
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
SITE = json.load(open(os.path.join(ROOT, "config/site.json"), encoding="utf-8"))
VENUES = json.load(open(os.path.join(ROOT, "config/venues.json"), encoding="utf-8"))["venues"]
TYPE_JA = {"dealer": "販売所", "exchange": "取引所"}
SERIES = [("bitflyer", "var(--s1)"), ("gmo", "var(--s2)"), ("sbivc", "var(--s3)")]


def u(path):
    return SITE["base_path"] + path


def load_rows():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/costs/*.csv"))):
        with open(f, encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def daily_avg(rows, coin="BTC", key="rt_100000_pct"):
    """{(date, venue, type): 平均%}"""
    acc = defaultdict(list)
    for r in rows:
        if r["coin"] != coin or r["status"] != "ok":
            continue
        v = fnum(r.get(key))
        if v is None:
            continue
        d = r["fetched_at"][:10]
        acc[(d, r["venue"], r["type"])].append(v)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def yen(x):
    return f"{x:,.0f}"


def chart_svg(rows):
    avg = daily_avg(rows)
    dates = sorted({k[0] for k in avg})[-30:]
    if not dates:
        return "<p class='note'>データ蓄積中です。</p>"
    series = []
    for vid, color in SERIES:
        pts = [(d, avg.get((d, vid, "dealer"))) for d in dates]
        series.append((f"{VENUES[vid]['name']} 販売所", color, "", pts))
    ex_pts = []
    for d in dates:
        vals = [v for (dd, _, t), v in avg.items() if dd == d and t == "exchange"]
        ex_pts.append((d, min(vals) if vals else None))
    series.append(("取引所(最安)", "var(--neutral)", "6 4", ex_pts))

    W, H, L, R, T, B = 440, 260, 34, 10, 10, 28
    vmax = max([v for *_, pts in series for _, v in pts if v is not None] + [1])
    top = (int(vmax) + 1) if vmax > 1 else 1
    n = len(dates)

    def x(i):
        return L + (W - L - R) * (i / (n - 1) if n > 1 else 0.5)

    def y(v):
        return T + (H - T - B) * (1 - v / top)

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="過去30日の往復コスト推移">']
    step = 1 if top <= 8 else 2
    for g in range(0, top + 1, step):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="var(--line)" stroke-width="1"/>')
        parts.append(f'<text x="{L - 6}" y="{y(g) + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)">{g}%</text>')
    for i, d in enumerate(dates):
        if n <= 6 or i % max(1, n // 5) == 0 or i == n - 1:
            parts.append(f'<text x="{x(i):.1f}" y="{H - 10}" text-anchor="middle" font-size="11" fill="var(--muted)">{d[5:].replace("-", "/")}</text>')
    for name, color, dash, pts in series:
        segs, cur = [], []
        for i, (d, v) in enumerate(pts):
            if v is None:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append((i, v))
        if cur:
            segs.append(cur)
        for seg in segs:
            if len(seg) > 1:
                p = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in seg)
                parts.append(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="2" '
                             f'stroke-linejoin="round" stroke-dasharray="{dash}"/>')
        for i, v in [(i, v) for i, (_, v) in enumerate(pts) if v is not None]:
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{color}" stroke="var(--surface)" '
                         f'stroke-width="2"><title>{html.escape(name)} {dates[i]}: {v:.2f}%</title></circle>')
    parts.append("</svg>")
    legend = "".join(f'<span><i style="background:{c}"></i>{html.escape(nm)}</span>' for nm, c, _, _ in series)
    return f'<div class="legend">{legend}</div>' + "".join(parts) + \
        '<p class="note">1日の計測値の平均。点に触れると値が出ます。</p>'


def latest_view(latest):
    rows = [r for r in latest["rows"] if r.get("status") == "ok" and r["coin"] == "BTC"
            and r.get("rt_100000_pct") is not None]
    ranking = []
    for r in sorted(rows, key=lambda r: r["rt_100000_pct"]):
        p = r["rt_100000_pct"]
        ranking.append({"name": VENUES[r["venue"]]["name"], "type_ja": TYPE_JA[r["type"]],
                        "pct": f"{p:.3f}" if p < 1 else f"{p:.2f}", "left": yen(100000 * (1 - p / 100)),
                        "fee": "スプレッドのみ" if r["type"] == "dealer" else f"{r['fee_pct']:.2f}%"})
    missing = [f"{VENUES[r['venue']]['name']}({TYPE_JA[r['type']]})" for r in latest["rows"]
               if r["coin"] == "BTC" and r.get("status") != "ok"]
    dealers = [r["rt_100000_pct"] for r in rows if r["type"] == "dealer"]
    exs = [r for r in rows if r["type"] == "exchange"]
    hero = None
    if dealers and exs:
        best = min(exs, key=lambda r: r["rt_100000_pct"])
        dp = sum(dealers) / len(dealers)
        ep = best["rt_100000_pct"]
        hero = {"dealer_pct": f"{dp:.2f}", "dealer_yen": yen(1000 * dp), "dealer_left": yen(100000 - 1000 * dp),
                "ex_name": VENUES[best["venue"]]["name"], "ex_pct": f"{ep:.3f}", "ex_yen": yen(1000 * ep),
                "ex_left": yen(100000 - 1000 * ep), "diff_yen": yen(1000 * (dp - ep))}
    dealer_venues = [vid for vid, _ in SERIES]
    table = []
    for coin in ["BTC", "ETH", "XRP"]:
        cells = []
        for vid in dealer_venues:
            m = [r for r in latest["rows"] if r["coin"] == coin and r["venue"] == vid and r["type"] == "dealer"]
            cells.append(f"{m[0]['spread_pct']:.2f}%" if m and m[0].get("status") == "ok" else "—")
        table.append({"coin": coin, "cells": cells})
    t = datetime.fromisoformat(latest["fetched_at"])
    return {"ranking": ranking, "missing": "、".join(missing), "hero": hero,
            "dealer_venues": [VENUES[v]["name"] for v in dealer_venues], "dealer_table": table,
            "latest_time": f"{t:%Y年%-m月%-d日 %H:%M}"}


def load_md(path):
    text = open(path, encoding="utf-8").read()
    meta = {}
    if text.startswith("---"):
        _, fm, text = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
    return meta, body


def write(path, content):
    full = os.path.join(OUT, path.lstrip("/"))
    if full.endswith("/"):
        full += "index.html"
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "templates")), autoescape=True)
    now = datetime.now(JST)
    common = {"site": SITE, "u": u, "year": now.year}

    posts = []
    for f in glob.glob(os.path.join(ROOT, "content/posts/*.md")):
        meta, body = load_md(f)
        if meta.get("draft"):
            continue
        slug = os.path.splitext(os.path.basename(f))[0]
        posts.append({"slug": slug, "path": f"/posts/{slug}/", "title": meta["title"],
                      "date": str(meta["date"]), "updated": str(meta.get("updated") or ""),
                      "description": meta.get("description", ""), "tags": meta.get("tags", []), "body": body})
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)

    for p in posts:
        related = [q for q in posts if q is not p and set(q["tags"]) & set(p["tags"])][:5] or \
                  [q for q in posts if q is not p][:5]
        jsonld = json.dumps({"@context": "https://schema.org", "@type": "Article", "headline": p["title"],
                             "datePublished": p["date"], "dateModified": p["updated"] or p["date"],
                             "author": {"@type": "Person", "name": SITE["operator"]}}, ensure_ascii=False)
        write(p["path"], env.get_template("post.html").render(
            **common, title=p["title"], description=p["description"], path=p["path"], is_post=True,
            date=p["date"], updated=p["updated"], body=p["body"], related=related, jsonld=jsonld))

    for f in glob.glob(os.path.join(ROOT, "content/pages/*.md")):
        meta, body = load_md(f)
        slug = os.path.splitext(os.path.basename(f))[0]
        write(f"/{slug}/", env.get_template("page.html").render(
            **common, title=meta["title"], description=meta.get("description"), path=f"/{slug}/", body=body))

    write("/posts/", env.get_template("posts.html").render(**common, title="記事一覧", path="/posts/", posts=posts))

    rows = load_rows()
    latest_path = os.path.join(ROOT, "data/latest.json")
    view = latest_view(json.load(open(latest_path, encoding="utf-8"))) if os.path.exists(latest_path) else \
        {"ranking": [], "hero": None, "dealer_table": [], "dealer_venues": [], "missing": "", "latest_time": "—"}
    write("/", env.get_template("index.html").render(**common, title=None, path="/", posts=posts,
                                                      chart=chart_svg(rows), **view))

    # データのダウンロード用コピー
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    for f in glob.glob(os.path.join(ROOT, "data/costs/*.csv")):
        shutil.copy(f, os.path.join(OUT, "data", os.path.basename(f)))

    urls = ["/", "/posts/"] + [p["path"] for p in posts] + \
           [f"/{os.path.splitext(os.path.basename(f))[0]}/" for f in glob.glob(os.path.join(ROOT, "content/pages/*.md"))]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{SITE['site_url']}{x}</loc></url>" for x in urls]
    sm.append("</urlset>")
    write("/sitemap.xml", "\n".join(sm))
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE['site_url']}/sitemap.xml\n")

    items = []
    for p in posts[:20]:
        d = datetime.fromisoformat(p["date"]).replace(tzinfo=JST)
        items.append(f"<item><title>{html.escape(p['title'])}</title><link>{SITE['site_url']}{p['path']}</link>"
                     f"<guid>{SITE['site_url']}{p['path']}</guid><pubDate>{format_datetime(d)}</pubDate>"
                     f"<description>{html.escape(p['description'])}</description></item>")
    write("/feed.xml", f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
                       f"<title>{html.escape(SITE['name'])}</title><link>{SITE['site_url']}/</link>"
                       f"<description>{html.escape(SITE['description'])}</description>{''.join(items)}</channel></rss>")
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print(f"built {len(posts)} posts, {len(rows)} data rows")


if __name__ == "__main__":
    main()
