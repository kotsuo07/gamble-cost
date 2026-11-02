"""国内の暗号資産取引所・販売所の価格を集め、「買ってすぐ売ったら何%減るか」を計算して保存する。

- 取引所(板): 公式APIの板情報から、指定金額を成行で買って成行で売った場合の損失率を計算
  (テイカー手数料を往復分含む)
- 販売所: 各社が公開ページで使っている売値・買値から 1 - 売値/買値 を計算

出力
- data/costs/YYYY-MM.csv に1回分の行を追記
- data/latest.json に最新結果
標準ライブラリのみ。
"""
import csv
import json
import os
import statistics
import time
import urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINS = ["BTC", "ETH", "XRP"]
AMOUNTS = [10_000, 100_000]  # 円
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
FIELDS = ["fetched_at", "coin", "venue", "type", "bid", "ask", "ref_mid",
          "spread_pct", "rt_10000_pct", "rt_100000_pct", "fee_pct", "status", "note"]


def get_json(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
               "Accept-Language": "ja,en;q=0.8"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def num(x):
    return float(str(x).replace(",", ""))


# ---------- 取引所(板) ----------

def book_bitflyer():
    d = get_json("https://api.bitflyer.com/v1/board?product_code=BTC_JPY")
    return ([(b["price"], b["size"]) for b in d["bids"]], [(a["price"], a["size"]) for a in d["asks"]])


def book_coincheck():
    d = get_json("https://coincheck.com/api/order_books?pair=btc_jpy")
    return ([(num(p), num(s)) for p, s in d["bids"]], [(num(p), num(s)) for p, s in d["asks"]])


def book_bitbank():
    d = get_json("https://public.bitbank.cc/btc_jpy/depth")["data"]
    return ([(num(p), num(s)) for p, s in d["bids"]], [(num(p), num(s)) for p, s in d["asks"]])


def book_gmo():
    d = get_json("https://api.coin.z.com/public/v1/orderbooks?symbol=BTC")["data"]
    return ([(num(b["price"]), num(b["size"])) for b in d["bids"]],
            [(num(a["price"]), num(a["size"])) for a in d["asks"]])


def book_bittrade():
    d = get_json("https://api-cloud.bittrade.co.jp/market/depth?symbol=btcjpy&type=step0")["tick"]
    return ([(num(p), num(s)) for p, s in d["bids"]], [(num(p), num(s)) for p, s in d["asks"]])


BOOKS = {"bitflyer": book_bitflyer, "coincheck": book_coincheck, "bitbank": book_bitbank,
         "gmo": book_gmo, "bittrade": book_bittrade}


def roundtrip_loss(bids, asks, jpy, fee):
    """jpy円(手数料込み)で成行買い→同じ数量を成行売りしたときの損失率。板が足りなければNone。"""
    asks = sorted(asks, key=lambda x: x[0])
    bids = sorted(bids, key=lambda x: -x[0])
    budget = jpy / (1 + fee)
    qty = 0.0
    for p, s in asks:
        cost = p * s
        if cost >= budget:
            qty += budget / p
            budget = 0
            break
        qty += s
        budget -= cost
    if budget > 1e-6:
        return None
    left, proceeds = qty, 0.0
    for p, s in bids:
        take = min(left, s)
        proceeds += take * p
        left -= take
        if left <= 1e-12:
            break
    if left > 1e-12:
        return None
    proceeds *= (1 - fee)
    return 1 - proceeds / jpy


# ---------- 販売所 ----------

def dealer_bitflyer(coin, ctx):
    d = get_json(f"https://bitflyer.com/api/echo/price?currency_pair={coin.lower()}_jpy",
                 referer="https://bitflyer.com/ja-jp/bitcoin-chart")
    return num(d["bid"]), num(d["ask"])


def dealer_gmo(coin, ctx):
    if "gmo_rates" not in ctx:
        ctx["gmo_rates"] = get_json("https://coin.z.com/api/v1/master/getCurrentRate.json",
                                    referer="https://coin.z.com/jp/")["data"]
        ctx["gmo_ticker"] = {t["symbol"]: num(t["last"]) for t in
                             get_json("https://api.coin.z.com/public/v1/ticker")["data"]}
    ref = ctx["gmo_ticker"].get(coin)
    if not ref:
        raise ValueError("GMO取引所の参照価格なし")
    # 商品IDと銘柄の対応が公開されていないため、取引所の価格に最も近い商品を選ぶ
    best = None
    for r in ctx["gmo_rates"]:
        if not (r.get("bidValidFlag") and r.get("askValidFlag")):
            continue
        mid = (num(r["bid"]) + num(r["ask"])) / 2
        gap = abs(mid / ref - 1)
        if best is None or gap < best[0]:
            best = (gap, r)
    if best is None or best[0] > 0.03:
        raise ValueError("GMO販売所の該当商品が見つからない")
    # 2位候補も近い場合は取り違えの恐れがあるので不採用
    close = [r for r in ctx["gmo_rates"]
             if abs(((num(r["bid"]) + num(r["ask"])) / 2) / ref - 1) < 0.03]
    if len(close) > 1:
        raise ValueError("GMO販売所の候補が複数あり判定できない")
    return num(best[1]["bid"]), num(best[1]["ask"])


def dealer_sbivc(coin, ctx):
    if "sbi" not in ctx:
        ctx["sbi"] = get_json("https://www.sbivc.co.jp/api/get_priceFeedList_all",
                              referer="https://www.sbivc.co.jp/")["body"]["rate"]
    for e in ctx["sbi"]:
        if e and e[0] == f"EX_{coin}/JPY":
            return num(e[2][0]), num(e[3][0])
    raise ValueError("SBI VCトレードの該当銘柄なし")


DEALERS = {"bitflyer": dealer_bitflyer, "gmo": dealer_gmo, "sbivc": dealer_sbivc}


# ---------- 参照価格(取引所の中値の中央値) ----------

def ref_mids(books):
    out = {}
    btc = [(b[0][0] + a[0][0]) / 2 for b, a in
           [(sorted(bk[0], key=lambda x: -x[0]), sorted(bk[1], key=lambda x: x[0])) for bk in books.values()]
           if b and a]
    if btc:
        out["BTC"] = statistics.median(btc)
    for coin in ["ETH", "XRP"]:
        vals = []
        try:
            t = get_json(f"https://public.bitbank.cc/{coin.lower()}_jpy/ticker")["data"]
            vals.append((num(t["buy"]) + num(t["sell"])) / 2)
        except Exception:  # noqa: BLE001
            pass
        try:
            t = get_json(f"https://api.coin.z.com/public/v1/ticker?symbol={coin}")["data"][0]
            vals.append((num(t["bid"]) + num(t["ask"])) / 2)
        except Exception:  # noqa: BLE001
            pass
        try:
            t = get_json(f"https://api.bitflyer.com/v1/ticker?product_code={coin}_JPY")
            vals.append((t["best_bid"] + t["best_ask"]) / 2)
        except Exception:  # noqa: BLE001
            pass
        if vals:
            out[coin] = statistics.median(vals)
    return out


def pct(x):
    return None if x is None else round(x * 100, 4)


def main():
    venues = json.load(open(os.path.join(ROOT, "config/venues.json"), encoding="utf-8"))["venues"]
    now = datetime.now(JST).replace(microsecond=0)
    rows = []

    books = {}
    for vid, fn in BOOKS.items():
        try:
            books[vid] = fn()
        except Exception as e:  # noqa: BLE001
            rows.append({"coin": "BTC", "venue": vid, "type": "exchange", "status": "error", "note": repr(e)[:150]})
        time.sleep(0.5)
    refs = ref_mids(books)

    for vid, (bids, asks) in books.items():
        fee = venues[vid]["exchange_fee_taker"]["BTC"]
        bb = max(p for p, _ in bids)
        ba = min(p for p, _ in asks)
        row = {"coin": "BTC", "venue": vid, "type": "exchange", "bid": bb, "ask": ba,
               "ref_mid": refs.get("BTC"), "spread_pct": pct((ba - bb) / ((ba + bb) / 2)),
               "fee_pct": pct(fee), "status": "ok", "note": ""}
        for amt in AMOUNTS:
            row[f"rt_{amt}_pct"] = pct(roundtrip_loss(bids, asks, amt, fee))
        rows.append(row)

    ctx = {}
    for coin in COINS:
        for vid, fn in DEALERS.items():
            row = {"coin": coin, "venue": vid, "type": "dealer", "ref_mid": refs.get(coin), "fee_pct": 0}
            try:
                bid, ask = fn(coin, ctx)
                loss = 1 - bid / ask
                row.update({"bid": bid, "ask": ask, "spread_pct": pct((ask - bid) / ((ask + bid) / 2)),
                            "rt_10000_pct": pct(loss), "rt_100000_pct": pct(loss), "status": "ok", "note": ""})
                ref = refs.get(coin)
                # 異常値チェック: 売値>買値、差が20%超、中値が参照から5%以上ずれる
                if bid >= ask or loss > 0.2 or (ref and abs((bid + ask) / 2 / ref - 1) > 0.05):
                    row.update({"status": "suspect", "note": "異常値の可能性"})
            except Exception as e:  # noqa: BLE001
                row.update({"status": "error", "note": repr(e)[:150]})
            rows.append(row)
            time.sleep(0.5)

    stamp = now.isoformat()
    for r in rows:
        r["fetched_at"] = stamp
    os.makedirs(os.path.join(ROOT, "data/costs"), exist_ok=True)
    path = os.path.join(ROOT, f"data/costs/{now:%Y-%m}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})
    with open(os.path.join(ROOT, "data/latest.json"), "w", encoding="utf-8") as f:
        json.dump({"fetched_at": stamp, "ref_mid": refs, "rows": rows}, f, ensure_ascii=False, indent=1)

    for r in rows:
        print(f"{r['coin']:4} {r['type']:8} {r['venue']:10} {r.get('status'):7} "
              f"10k={r.get('rt_10000_pct')} 100k={r.get('rt_100000_pct')} {r.get('note', '')}")
    ok = sum(1 for r in rows if r.get("status") == "ok")
    if ok == 0:
        raise SystemExit("全ての取得に失敗")


if __name__ == "__main__":
    main()
