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
srl = [a[1] for a in acts if a[1].startswith("pw01srl")]
out["srl"] = srl[:5]
t = post("/JRADB/accessS.html", srl[0])
sde = list(dict.fromkeys(re.findall(r"(pw01sde[0-9A-Za-z/]+)", t)))
out["sde"] = sde[:15]
t = post("/JRADB/accessS.html", sde[0])
txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
i = txt.find("着順")
out["result_text"] = txt[i-300:i+3000]
j = txt.find("払戻金")
out["payout_text"] = txt[j:j+1200]
os.makedirs("probe/out", exist_ok=True)
json.dump(out, open("probe/out/jra_probe.json", "w"), ensure_ascii=False, indent=1)
