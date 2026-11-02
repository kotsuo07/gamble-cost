"""公営競技データの取得可否テスト(使い捨て)"""
import json, os, subprocess, urllib.request, glob
from datetime import datetime, timedelta, timezone
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
out = {}
def get(url, n=400):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read()
            return {"status": r.status, "len": len(b), "ctype": r.headers.get("Content-Type"), "head": b[:n].decode("utf-8", "replace")}, b
    except Exception as e:
        return {"error": repr(e)[:300]}, None
d = datetime.now(JST) - timedelta(days=1)
# ボートレース公式の競走成績(K)・番組表(B)ダウンロード
for kind in ["K", "B"]:
    url = f"https://www1.mbrace.or.jp/od2/{kind}/{d:%Y%m}/{kind.lower()}{d:%y%m%d}.lzh"
    info, body = get(url, 0)
    out[f"boat_{kind}"] = {"url": url, **info}
    if body:
        os.makedirs("probe/tmp", exist_ok=True)
        p = f"probe/tmp/{kind}.lzh"; open(p, "wb").write(body)
        r = subprocess.run(["lha", "xw=probe/tmp", p], capture_output=True, text=True)
        out[f"boat_{kind}"]["lha"] = (r.returncode, r.stdout[-300:], r.stderr[-300:])
        out[f"boat_{kind}"]["files"] = os.listdir("probe/tmp")
        for f in [x for x in glob.glob("probe/tmp/*") if not x.endswith(".lzh")]:
            if os.path.isdir(f): continue
            txt = open(f, "rb").read().decode("cp932", "replace")
            out[f"boat_{kind}"]["sample"] = txt[:1500]
            out[f"boat_{kind}"]["lines"] = txt.count("\n")
for name, url in {
    "boat_web_result": f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd=04&hd={d:%Y%m%d}",
    "keirin_top": "https://keirin.jp/pc/top",
    "keirin_robots": "https://keirin.jp/robots.txt",
    "jra_top": "https://www.jra.go.jp/",
    "jra_robots": "https://www.jra.go.jp/robots.txt",
    "jra_result": "https://www.jra.go.jp/JRADB/accessS.html",
    "boat_robots": "https://www.boatrace.jp/robots.txt",
}.items():
    info, _ = get(url, 1500)
    out[name] = {"url": url, **info}
import re, traceback
try:
  info, body = get("https://www.jra.go.jp/keiba/", 0)
  if body:
    t = body.decode("shift_jis", "replace")
    out["jra_cnames"] = re.findall(r"doAction\('([^']+)',\s*'([^']+)'\)", t)[:20]
except Exception:
  out["jra_err"] = traceback.format_exc()[-500:]
os.makedirs("probe/out", exist_ok=True)
json.dump(out, open("probe/out/race_probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: (v.get("status"), v.get("len"), v.get("error")) for k, v in out.items()}, ensure_ascii=False))
