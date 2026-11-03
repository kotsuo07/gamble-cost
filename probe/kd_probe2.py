import json, os, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return r.read().decode("utf-8", "replace")
def text(b): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<script.*?</script>", " ", b)))
out = {}
t = text(get("https://keirin.kdreams.jp/info/sitepolicy/"))
i = t.find("サイトポリシー")
out["sitepolicy"] = t[i:i+5000]
t = text(get("https://keirin.kdreams.jp/hofu/raceresult/63202610310400/"))
i = t.find("着")
out["result"] = t[t.find("1R"):t.find("1R")+3500]
os.makedirs("probe/out", exist_ok=True)
json.dump(out, open("probe/out/kd_probe2.json", "w"), ensure_ascii=False, indent=1)
