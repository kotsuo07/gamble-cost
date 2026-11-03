import json, os, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)
out = {}
for k, u in {"robots": "https://keirin.kdreams.jp/robots.txt", "top": "https://keirin.kdreams.jp/",
             "www_robots": "https://www.kdreams.jp/robots.txt"}.items():
    s, b = get(u)
    out[k] = {"status": s, "raw": b[:3000]}
    if k == "top":
        out["links"] = sorted(set(re.findall(r'href="([^"]+)"', b)))[:200]
cands = [l for l in out.get("links", []) if re.search(r"kiyaku|terms|rule|policy|riyou", l)]
out["term_cands"] = cands
for i, l in enumerate(cands[:4]):
    url = l if l.startswith("http") else "https://keirin.kdreams.jp" + l
    s, b = get(url)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))
    hits = [txt[max(0, m.start()-150):m.start()+250] for m in re.finditer(r"禁止|複製|転載|自動|プログラム|ロボット|クロール|スクレイピング", txt)][:12]
    out[f"term{i}"] = {"url": url, "status": s, "hits": hits}
os.makedirs("probe/out", exist_ok=True)
json.dump(out, open("probe/out/kd_probe.json", "w"), ensure_ascii=False, indent=1)
