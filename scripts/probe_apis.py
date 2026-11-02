"""国内暗号資産取引所の価格APIにアクセスできるかを調べるテスト用スクリプト。

GitHub Actions 上で実行し、各エンドポイントの応答(ステータス・中身の先頭)を
data/probe/ に JSON で保存する。標準ライブラリのみ使用。
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# kind: exchange = 取引所(板), dealer = 販売所
# official: 公式ドキュメントに載っているAPIかどうか
ENDPOINTS = [
    # bitFlyer
    ("bitflyer", "exchange", True, "https://api.bitflyer.com/v1/ticker?product_code=BTC_JPY"),
    ("bitflyer", "exchange", True, "https://api.bitflyer.com/v1/board?product_code=BTC_JPY"),
    ("bitflyer", "dealer", False, "https://bitflyer.com/api/echo/price?currency_pair=btc_jpy"),
    # Coincheck
    ("coincheck", "exchange", True, "https://coincheck.com/api/ticker?pair=btc_jpy"),
    ("coincheck", "exchange", True, "https://coincheck.com/api/order_books?pair=btc_jpy"),
    ("coincheck", "dealer", True, "https://coincheck.com/api/rate/btc_jpy"),
    ("coincheck", "dealer", False, "https://coincheck.com/api/exchange/orders/rate?order_type=buy&pair=btc_jpy&amount=0.01"),
    # bitbank
    ("bitbank", "exchange", True, "https://public.bitbank.cc/btc_jpy/ticker"),
    ("bitbank", "exchange", True, "https://public.bitbank.cc/btc_jpy/depth"),
    # GMOコイン
    ("gmo", "exchange", True, "https://api.coin.z.com/public/v1/ticker?symbol=BTC"),
    ("gmo", "exchange", True, "https://api.coin.z.com/public/v1/orderbooks?symbol=BTC"),
    ("gmo", "unknown", True, "https://api.coin.z.com/public/v1/ticker"),
    # OKJ
    ("okj", "exchange", True, "https://www.okcoin.jp/api/spot/v3/instruments/BTC-JPY/ticker"),
    # BitTrade
    ("bittrade", "exchange", True, "https://api-cloud.bittrade.co.jp/market/detail/merged?symbol=btcjpy"),
    # SBI VCトレード
    ("sbivc", "unknown", False, "https://api.sbivc.co.jp/v1/ticker?symbol=BTC_JPY"),
]

UA = "Mozilla/5.0 (compatible; price-probe/0.1; +https://github.com/kotsuo07/gamble-cost)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(200_000).decode("utf-8", "replace")
            status, ctype = r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read(2000).decode("utf-8", "replace")
        status, ctype = e.code, e.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001
        return {"status": None, "error": repr(e), "elapsed": round(time.time() - t0, 2)}
    out = {"status": status, "content_type": ctype, "elapsed": round(time.time() - t0, 2)}
    try:
        parsed = json.loads(body)
        out["json"] = True
        # 板データは大きいので先頭だけ残す
        if isinstance(parsed, dict):
            out["keys"] = list(parsed.keys())[:20]
        out["head"] = body[:1500]
    except ValueError:
        out["json"] = False
        out["head"] = body[:500]
    return out


def main():
    now = datetime.now(JST)
    results = []
    for ex, kind, official, url in ENDPOINTS:
        r = fetch(url)
        r.update({"exchange": ex, "kind": kind, "official": official, "url": url})
        results.append(r)
        print(f"{ex:10s} {kind:8s} {r.get('status')} {url}")
        time.sleep(1)
    os.makedirs("data/probe", exist_ok=True)
    path = f"data/probe/{now:%Y%m%d-%H%M}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": now.isoformat(), "results": results}, f, ensure_ascii=False, indent=1)
    print("saved", path)


if __name__ == "__main__":
    main()
