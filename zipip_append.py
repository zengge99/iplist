import io, zipfile, re, subprocess, concurrent.futures, urllib.request

REGIONS = ["HK", "JP", "KR"]
PORT = 443
THREADS = 100            # 联通性验证并发
SPEED_THREADS = 5        # 测速并发
CAND_PER_REGION = 20     # 每地区保留候选数(测速前)
TOP_PER_REGION = 10      # 每地区测速排名取前N
HOST = "www.cloudflare.com"      # 联通性验证目标
SPEED_HOST = "speed.zngle.de5.net"
SPEED_URL = f"https://{SPEED_HOST}/d/1.iso"
SPEED_RANGE = 8 * 1024 * 1024     # 测速下载 8MB
VERIFY_TIMEOUT = 6
SPEED_TIMEOUT = 25
ZIP_URL = "https://zip.cm.edu.kg/ip.zip"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def download():
    attempts = [
        lambda: urllib.request.urlopen(urllib.request.Request(ZIP_URL, headers={
            "User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity",
            "Referer": "https://zip.cm.edu.kg/"}), timeout=60).read(),
        lambda: urllib.request.urlopen(ZIP_URL, timeout=60).read(),
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

# 联通性: curl 指定IP访问 www.cloudflare.com
def check(ip):
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", str(VERIFY_TIMEOUT),
             "--resolve", f"{HOST}:{PORT}:{ip}", f"https://{HOST}/"],
            capture_output=True, text=True, timeout=VERIFY_TIMEOUT + 3)
        return ip, out.stdout.strip().startswith(("2", "3", "4"))
    except Exception:
        return ip, False

# 测速: curl --resolve 强制解析IP 拉取 speed.zngle.de5.net/d/1.iso 前8MB
def speedtest(ip):
    try:
        out = subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-w", "%{speed_download}", "-m", str(SPEED_TIMEOUT),
             "-r", f"0-{SPEED_RANGE-1}",
             "--resolve", f"{SPEED_HOST}:443:{ip}", SPEED_URL],
            capture_output=True, text=True, timeout=SPEED_TIMEOUT + 5)
        spd = out.stdout.strip()
        return ip, float(spd) if spd.replace('.', '', 1).lstrip('-').isdigit() else 0.0
    except Exception:
        return ip, 0.0

def main():
    print("[1] 下载 zip.cm.edu.kg/ip.zip ...")
    data = download()
    zf = zipfile.ZipFile(io.BytesIO(data))

    # 提取 IP
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

    # ① 100线程测联通，每地区保留前20候选
    print(f"[3] {THREADS}线程验证联通性 ...")
    reachable = {}   # region -> [ip, ...] 保持原始顺序
    for r in REGIONS:
        ips = ips_by_region.get(r, [])
        if not ips:
            continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as ex:
            results = list(ex.map(check, ips))
        ok = [ip for ip, ok in results if ok]
        print(f"   {r}: 联通 {len(ok)}/{len(ips)} -> 保留前{CAND_PER_REGION}")
        reachable[r] = ok[:CAND_PER_REGION]

    # ② 每地区候选 5并发 测速 speed.zngle.de5.net/d/1.iso
    print(f"[4] {SPEED_THREADS}并发测速 {SPEED_URL} ...")
    winners = {}   # region -> [(spd, ip)]
    for r, ips in reachable.items():
        if not ips:
            winners[r] = []
            continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=SPEED_THREADS) as ex:
            results = list(ex.map(speedtest, ips))
        # 按速度降序
        ranked = sorted(results, key=lambda x: x[1], reverse=True)
        top = ranked[:TOP_PER_REGION]
        winners[r] = top
        print(f"   {r}: 测速前{TOP_PER_REGION} -> " +
              ", ".join(f"{ip}={spd/1e6:.1f}MB/s" for ip, spd in top))

    # ③ 追加到 iplist.txt（去重）
    try:
        existing = set()
        with open("iplist.txt") as f:
            for line in f:
                if line.strip():
                    existing.add(line.strip())
    except FileNotFoundError:
        existing = set()

    added = 0
    print("[5] 追加测速前10到 iplist.txt ...")
    with open("iplist.txt", "a") as f:
        for r in REGIONS:
            for spd, ip in winners.get(r, []):
                entry = f"{ip}:{PORT}#{r}"
                if entry not in existing:
                    f.write(entry + "\n")
                    existing.add(entry)
                    added += 1
    print(f"[6] 新增 {added} 条 (每地区前{TOP_PER_REGION})")

if __name__ == "__main__":
    main()