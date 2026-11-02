"""販売所の売値・買値が各社の公開ページ(ログイン不要)から読めるかを調べるテスト。

Playwright でページを開き、
- 通信で受け取ったJSONのうち BTC 価格帯の数値を含むもの
- 画面の文字のうち BTC 価格帯の数値を含む行
を data/probe/dealer-*.json に保存する。
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

JST = timezone(timedelta(hours=9))

PAGES = {
    "bitflyer": "https://bitflyer.com/ja-jp/bitcoin-chart",
    "coincheck": "https://coincheck.com/ja/",
    "coincheck_rate": "https://coincheck.com/ja/exchange/rates",
    "gmo": "https://coin.z.com/jp/",
    "gmo_price": "https://coin.z.com/jp/corp/information/btc-market/",
    "sbivc": "https://www.sbivc.co.jp/",
    "sbivc_price": "https://www.sbivc.co.jp/prices",
    "bitbank": "https://bitbank.cc/",
    "bittrade": "https://www.bittrade.co.jp/ja-jp/",
    "rakuten": "https://www.rakuten-wallet.co.jp/",
    "binancejp": "https://www.binance.com/ja/price/bitcoin",
}


def ref_mid():
    with urllib.request.urlopen("https://api.bitflyer.com/v1/ticker?product_code=BTC_JPY", timeout=15) as r:
        d = json.load(r)
    return (d["best_bid"] + d["best_ask"]) / 2


NUM = re.compile(r"\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?|\d{7,9}(?:\.\d+)?")


def in_band(text, lo, hi):
    vals = []
    for m in NUM.findall(text):
        try:
            v = float(m.replace(",", ""))
        except ValueError:
            continue
        if lo <= v <= hi:
            vals.append(v)
    return vals


def main():
    mid = ref_mid()
    lo, hi = mid * 0.85, mid * 1.15
    out = {"fetched_at": datetime.now(JST).isoformat(), "ref_mid": mid, "pages": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ja-JP", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"))
        for name, url in PAGES.items():
            rec = {"url": url, "json_hits": [], "text_hits": []}
            page = ctx.new_page()

            def on_resp(resp, rec=rec):
                try:
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    body = resp.text()
                    vals = in_band(body, lo, hi)
                    if vals and len(rec["json_hits"]) < 15:
                        rec["json_hits"].append({"url": resp.url[:300], "vals": vals[:10], "head": body[:800]})
                except Exception:  # noqa: BLE001
                    pass

            page.on("response", on_resp)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                rec["status"] = resp.status if resp else None
                page.wait_for_timeout(8000)
                text = page.inner_text("body")
                for line in text.splitlines():
                    line = line.strip()
                    if line and in_band(line, lo, hi) and len(rec["text_hits"]) < 30:
                        rec["text_hits"].append(line[:200])
                # 数値と同じ行にない「買」「売」ラベルも拾えるよう前後の文脈も少し保存
                rec["text_sample"] = re.sub(r"\s+", " ", text)[:3000]
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)[:300]
            page.close()
            out["pages"][name] = rec
            print(name, rec.get("status"), len(rec["json_hits"]), len(rec["text_hits"]), rec.get("error", ""))
        browser.close()
    os.makedirs("data/probe", exist_ok=True)
    path = f"data/probe/dealer-{datetime.now(JST):%Y%m%d-%H%M}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("saved", path)


if __name__ == "__main__":
    main()
