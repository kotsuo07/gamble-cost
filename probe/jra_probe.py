import json, re, urllib.request, urllib.parse, os
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
def post(path, cname):
    data = urllib.parse.urlencode({"cname": cname}).encode()
    req = urllib.request.Request("https://www.jra.go.jp" + path, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("shift_jis", "replace")
out = {}
t = post("/JRADB/accessS.html", "pw01sli00/AF")   # 開催一覧
out["list_len"] = len(t)
acts = re.findall(r"doAction\('(/JRADB/accessS\.html)',\s*'([^']+)'\)", t)
out["list_actions"] = acts[:15]
# 開催(日)→レース一覧→レース結果 と順にたどる
step = acts[0][1] if acts else None
for depth in range(3):
    if not step: break
    t = post("/JRADB/accessS.html", step)
    acts = [a for a in re.findall(r"doAction\('(/JRADB/accessS\.html)',\s*'([^']+)'\)", t) if a[1] != step]
    out[f"d{depth}_actions"] = acts[:8]
    out[f"d{depth}_text"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:2500]
    step = acts[0][1] if acts else None
os.makedirs("probe/out", exist_ok=True)
json.dump(out, open("probe/out/jra_probe.json", "w"), ensure_ascii=False, indent=1)
