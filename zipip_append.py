import io, zipfile, re, subprocess, concurrent.futures, urllib.request

REGIONS = ["HK", "JP", "KR"]
PORT = 443
THREADS = 100
HOST = "www.cloudflare.com"
TIMEOUT = 6
ZIP_URL = "https://zip.cm.edu.kg/ip.zip"

# 浏览器 UA + 跟随重定向，降低被 403/反爬拦截概率
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def download():
    # 多级回退，提高在 GH runner/IP 受限环境下的成功率
    attempts = [
        # 1) urllib + 浏览器 UA
        lambda: urllib.request.urlopen(urllib.request.Request(ZIP_URL, headers={
            "User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity",
            "Referer": "https://zip.cm.edu.kg/"}), timeout=60).read(),
        # 2) urllib 普通 UA
        lambda: urllib.request.urlopen(ZIP_URL, timeout=60).read(),
        # 3) curl CLI（走真实 HTTP 栈，跟随重定向）
        lambda: subprocess.run(["curl", "-sL", "-m", "60", "-A", UA,
                                "-H", "Referer: https://zip.cm.edu.kg/", ZIP_URL],
                               capture_output=True, timeout=70).stdout,
    ]
    last = None
    for fn in attempts:
        try:
            b = fn()
            if b and len(b) > 1000 and b[:2] == b"PK":
                return b
            last = f"bad payload (len={len(b) if b else 0})"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    raise RuntimeError(f"download failed: {last}")

print("[1] 下载 zip.cm.edu.kg/ip.zip ...")
data = download()
zf = zipfile.ZipFile(io.BytesIO(data))

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

def check(ip):
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", str(TIMEOUT),
             "--resolve", f"{HOST}:{PORT}:{ip}", f"https://{HOST}/"],
            capture_output=True, text=True, timeout=TIMEOUT + 3)
        return ip, out.stdout.strip().startswith(("2", "3", "4"))
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
print(f"[5] 新增 {added} 条，原有 {len(good)-added} 已存在/跳过")