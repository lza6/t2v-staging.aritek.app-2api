"""AIVG v1.9.3 第四轮：产物验证（音轨/分辨率/CDN 头策略）+ t2i 全链路"""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
sys.path.insert(0, r"D:\aivg193")
from probe import http, bootstrap


def cdn_get(url, token=None, sign=False):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "okhttp/4.9.3")
    if sign:
        req.add_header("sign", "68d6165b72a7f2d8d17b0dc6fe9691abdf77c583")
        req.add_header("versionCode", "93")
        req.add_header("Ctry-Target", "others")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        r = urllib.request.urlopen(req, timeout=180)
        return r.status, r.getheader("Content-Type"), r.getheader("Content-Length"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, None, None, e.read()[:200]
    except Exception as e:
        return -1, None, None, str(e).encode()


def probe_media(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height,nb_frames:format=duration,size",
                          "-of", "json", path], capture_output=True, text=True)
    return out.stdout or out.stderr


def main():
    dev, token, st, _ = bootstrap()
    print(f"# device={dev}")

    print("\n## t2v 16:9 + ai_sound=1 产物")
    st, b = http("POST", "/api/v4/video/t2v", token,
                 json.dumps({"prompt": "a neon-lit tokyo street at night, rain, cinematic",
                             "aspect_ratio": "16:9", "ai_sound": 1}), timeout=600)
    j = json.loads(b)
    url = j["data"]["url"]
    print("url:", url)
    for label, kw in [("裸访问", {}), ("仅 Bearer", {"token": token}), ("仅 Sign", {"sign": True}),
                      ("Sign+Bearer", {"sign": True, "token": token})]:
        st2, ct, cl, data = cdn_get(url, **kw)
        print(f"CDN {label:12s} st={st2} ct={ct} len={cl}")
        if st2 == 200 and isinstance(data, bytes) and len(data) > 1000:
            open(r"D:\aivg193\t2v_16x9_sound.mp4", "wb").write(data)
            print("  ffprobe:", probe_media(r"D:\aivg193\t2v_16x9_sound.mp4").replace("\n", " ")[:400])
            break

    print("\n## t2i 全链路")
    st, b = http("POST", "/api/v4/image/t2i", token,
                 json.dumps({"prompt": ["a cute corgi puppy wearing sunglasses, studio light"]}), timeout=120)
    print(f"submit st={st} {b[:200].decode(errors='replace')}")
    job = json.loads(b)["data"].get("jobId")
    print("jobId:", job)
    for i in range(20):
        time.sleep(3)
        st, b = http("POST", "/api/v1/generate/status", None, json.dumps({"ids": [job]}), timeout=60)
        print(f"  poll{i} st={st} {b[:220].decode(errors='replace')}")
        try:
            j = json.loads(b)
        except Exception:
            continue
        items = j.get("data") or []
        if items and (items[0].get("url") or items[0].get("status") in ("succeeded", "failed")):
            print("  终态:", items[0])
            break


if __name__ == "__main__":
    main()
