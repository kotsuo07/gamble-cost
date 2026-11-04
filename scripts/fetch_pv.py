"""GoatCounter API から PV 数を取得して data/pageviews.json に保存する。

必要なもの:
- config/site.json の goatcounter_code(https://<code>.goatcounter.com の <code>)
- 環境変数 GOATCOUNTER_TOKEN(GitHub リポジトリの Secret から渡す)
どちらかが無ければ何もせず終了する。
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = json.load(open(os.path.join(ROOT, "config/site.json"), encoding="utf-8"))
SINCE = "2026-11-01"  # サイト開設月の初日。これ以降の累計を「これまでのPV」とする


def api(code, token, endpoint, **params):
    url = f"https://{code}.goatcounter.com/api/v0/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "gamble-cost-pv/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def total(code, token, start, end):
    return int(api(code, token, "stats/total", start=start, end=end).get("total", 0))


def main():
    code = SITE.get("goatcounter_code", "").strip()
    token = os.environ.get("GOATCOUNTER_TOKEN", "").strip()
    if not code or not token:
        print("goatcounter_code または GOATCOUNTER_TOKEN が未設定のためスキップ")
        return 0

    now = datetime.now(JST)
    today = now.date()
    end = (today + timedelta(days=1)).isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()

    out = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "since": SINCE,
        "total": total(code, token, SINCE, end),
        "yesterday": total(code, token, yesterday, today.isoformat()),
        "last_7d": total(code, token, (today - timedelta(days=7)).isoformat(), today.isoformat()),
        "by_path": [],
    }
    hits = api(code, token, "stats/hits", start=SINCE, end=end, limit=50).get("hits", [])
    for h in hits:
        out["by_path"].append({
            "path": h.get("path"),
            "title": h.get("title"),
            "count": int(h.get("count", h.get("count_unique", 0)) or 0),
        })
    out["by_path"].sort(key=lambda x: x["count"], reverse=True)

    path = os.path.join(ROOT, "data/pageviews.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"PV: 累計 {out['total']} / 前日 {out['yesterday']} / 直近7日 {out['last_7d']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
