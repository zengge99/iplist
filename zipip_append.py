import io, zipfile, re, subprocess, concurrent.futures, urllib.request

REGIONS = ["HK", "JP", "KR"]
PORT = 443
THREADS = 100
HOST = "www.cloudflare.com"
TIMEOUT = 6
ZIP_URL = "https://zip.cm.edu.kg/ip.zip"

# 1) 下载
print("[1] 下载 zip.cm.edu.kg/ip.zip ...")
req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "curl/8"})
data = urllib.request.urlopen(req, timeout=40).read()
zf = zipfile.ZipFile(io.BytesIO(data))

# 2) 提取 443/HK,JP,KR
ips_by_region = {}
for r in REGIONS:
    name = f"443/{r}.txt"
    try:
        content = zf.read(name).decode("utf-8", "replace")
    except KeyError:
        print(f"  !! 缺 {name}")
        continue
    lst = [ln.strip() for ln in content.splitlines()
           if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ln.strip())]
    ips_by_region[r] = lst
    print(f"[2] {name}: {len(lst)} IPs")

# 3) 100线程 curl 验证
def check(ip):
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", str(TIMEOUT),
             "--resolve", f"{HOST}:{PORT}:{ip}", f"https://{HOST}/"],
            capture_output=True, text=True, timeout=TIMEOUT + 3)
        code = out.stdout.strip()
        return ip, code.startswith(("2", "3", "4"))
    except Exception:
        return ip, False

good = []
for r in REGIONS:
    ips = ips_by_region.get(r, [])
    if not ips:
        continue
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as ex:
        results = list(ex.map(check, ips))
    ok = [ip for ip, ok in results if ok]
    print(f"[3] {r}: {len(ok)}/{len(ips)} reachable")
    for ip in ok:
        good.append(f"{ip}:{PORT}#{r}")

# 4) 追加到 iplist.txt（去重）
print(f"[4] 联通 {len(good)} 条，准备追加去重 ...")
try:
    existing = set()
    with open("iplist.txt") as f:
        for line in f:
            if line.strip():
                existing.add(line.strip())
except FileNotFoundError:
    existing = set()

added = 0
with open("iplist.txt", "a") as f:
    for entry in good:
        if entry not in existing:
            f.write(entry + "\n")
            existing.add(entry)
            added += 1
print(f"[5] 新增 {added} 条，原有 {len(good)-added} 条已存在/跳过")