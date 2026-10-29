"""AIVG v1.9.3 第五轮：aspect_ratio / ai_sound 真实生效性 + 增强类端点路由发现"""
import json
import subprocess
import sys
import urllib.request
import urllib.error
sys.path.insert(0, r"D:\aivg193")
from probe import http, bootstrap


def media(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/4.9.3"})
    data = urllib.request.urlopen(req, timeout=180).read()
    open(path, "wb").write(data)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height:format=duration,size",
                          "-of", "csv=p=0", path], capture_output=True, text=True)
    return out.stdout.strip().replace("\n", " | ")


def t2v_case(label, body):
    dev, token, st, _ = bootstrap()
    st, b = http("POST", "/api/v4/video/t2v", token, json.dumps(body), timeout=600)
    if st != 200:
        print(f"{label:34s} st={st} {b[:150].decode(errors='replace')}")
        return
    url = json.loads(b)["data"]["url"]
    p = rf"D:\aivg193\case_{len(label)}_{abs(hash(label))%9999}.mp4"
    try:
        info = media(url, p)
    except Exception as e:
        info = f"download fail {e}"
    print(f"{label:34s} {info}")


def main():
    base = "a dog running on the beach, golden hour, cinematic"
    print("## aspect / ai_sound 生效性（设备均为全新，配额独立）")
    t2v_case("默认(无参数)", {"prompt": base})
    t2v_case("ai_sound=0", {"prompt": base, "ai_sound": 0})
    t2v_case("ai_sound=1", {"prompt": base, "ai_sound": 1})
    t2v_case("aspect 16:9", {"prompt": base, "aspect_ratio": "16:9"})
    t2v_case("aspect 1:1", {"prompt": base, "aspect_ratio": "1:1"})
    t2v_case("aspect 9:16+ai_sound=1", {"prompt": base, "aspect_ratio": "9:16", "ai_sound": 1})

    print("\n## 增强类端点路由发现（guest token 下 404=不存在）")
    dev, token, st, _ = bootstrap()
    cands = [
        ("POST", "/api/v4/image/enhance"), ("POST", "/api/v4/image/aging"),
        ("POST", "/api/v4/image/open-eyes"), ("POST", "/api/v4/image/expand"),
        ("POST", "/api/v4/image/remove-object"), ("POST", "/api/v4/image/background"),
        ("POST", "/api/v4/image/i2i-v2"), ("POST", "/api/v4/image/enhance/aging"),
        ("POST", "/api/v5/image/enhance"), ("POST", "/api/v4/video/r2v"),
        ("GET", "/api/v4/image/types"), ("GET", "/api/v1/user/info"),
    ]
    for m, p in cands:
        st, b = http(m, p, token, json.dumps({}) if m == "POST" else None, timeout=30)
        print(f"{m:5s} {p:34s} st={st} {b[:110].decode(errors='replace')}")


if __name__ == "__main__":
    main()
