"""記事を書くための集計を出力する。記事中の数値はすべてここの出力からとる。

使い方: python scripts/stats.py            (人が読む形式)
        python scripts/stats.py --json     (JSON)
"""
import csv
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENUES = json.load(open(os.path.join(ROOT, "config/venues.json"), encoding="utf-8"))["venues"]


def load():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/costs/*.csv"))):
        rows += [r for r in csv.DictReader(open(f, encoding="utf-8")) if r["status"] == "ok"]
    return rows


def agg(rows, key, since=None):
    acc = defaultdict(list)
    for r in rows:
        if since and r["fetched_at"][:10] < since:
            continue
        if r.get(key) not in ("", None):
            acc[(r["coin"], r["type"], r["venue"])].append(float(r[key]))
    return {k: {"n": len(v), "mean": round(statistics.mean(v), 4), "min": round(min(v), 4),
                "max": round(max(v), 4)} for k, v in acc.items()}


def main():
    rows = load()
    if not rows:
        print("データなし")
        return
    latest = json.load(open(os.path.join(ROOT, "data/latest.json"), encoding="utf-8"))
    days = sorted({r["fetched_at"][:10] for r in rows})
    last = date.fromisoformat(days[-1])
    out = {
        "data_period": f"{days[0]} 〜 {days[-1]} ({len(days)}日分, 計測{len({r['fetched_at'] for r in rows})}回)",
        "latest_fetched_at": latest["fetched_at"],
        "latest_ref_mid_jpy": latest["ref_mid"],
        "latest": [{k: r.get(k) for k in ("coin", "type", "venue", "bid", "ask", "spread_pct",
                                          "rt_10000_pct", "rt_100000_pct", "fee_pct", "status")}
                   for r in latest["rows"]],
        "rt_100000_pct_last_day": agg(rows, "rt_100000_pct", since=days[-1]),
        "rt_100000_pct_7d": agg(rows, "rt_100000_pct", since=str(last - timedelta(days=6))),
        "rt_100000_pct_30d": agg(rows, "rt_100000_pct", since=str(last - timedelta(days=29))),
        "rt_10000_pct_7d": agg(rows, "rt_10000_pct", since=str(last - timedelta(days=6))),
        "fees": {v: {"name": d["name"], "taker_btc": d["exchange_fee_taker"]["BTC"], "checked": d["checked"]}
                 for v, d in VENUES.items()},
    }
    if "--json" in sys.argv:
        print(json.dumps({k: ({"|".join(kk): vv for kk, vv in v.items()} if isinstance(v, dict) and v and
                              isinstance(next(iter(v)), tuple) else v) for k, v in out.items()},
                         ensure_ascii=False, indent=1))
        return
    print("期間:", out["data_period"])
    print("最新計測:", out["latest_fetched_at"], "参照中値:", out["latest_ref_mid_jpy"])
    print("\n[最新] 銘柄 形式 会社  往復1万円%  往復10万円%  スプレッド%  手数料%")
    for r in out["latest"]:
        print(f"  {r['coin']} {r['type']:8} {VENUES[r['venue']]['name']:12} {r.get('rt_10000_pct')} "
              f"{r.get('rt_100000_pct')} {r.get('spread_pct')} {r.get('fee_pct')} [{r.get('status')}]")
    for label in ("rt_100000_pct_last_day", "rt_100000_pct_7d", "rt_100000_pct_30d", "rt_10000_pct_7d"):
        print(f"\n[{label}] 銘柄 形式 会社: 平均 / 最小 / 最大 (計測回数)")
        for (coin, typ, v), s in sorted(out[label].items(), key=lambda x: (x[0][0], x[1]["mean"])):
            print(f"  {coin} {typ:8} {VENUES[v]['name']:12} {s['mean']} / {s['min']} / {s['max']} ({s['n']})")
    print("\n10万円あたりの円換算 = 往復% × 1000 円")


if __name__ == "__main__":
    main()
