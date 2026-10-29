"""AIVG v1.9.3 第三轮：全 type 权限矩阵 + 参数维度 + CDN 直链可访问性"""
import json
import sys
import time
sys.path.insert(0, r"D:\aivg193")
from probe import http, bootstrap

TYPES = ["t2v_prompt", "t2v_prompt_v2", "i2v_prompt", "i2v_lora", "i2v_swap", "i2v_dance",
         "i2v_dance_v2", "t2i_prompt", "i2i_edit", "i2i_edit_dual", "i2i_swap", "image_enhance",
         "image_aging", "open_eyes", "image_expand", "object_remover", "background_generator",
         "i2v_r2v", "i2v_r2v_v2", "i2v_r2v_dual", "i2v_r2v_fl", "i2v_r2v_ii"]


def main():
    dev, token, st, _ = bootstrap()
    print(f"# device={dev}")
    print("\n## 权限矩阵（guest）")
    for t in TYPES:
        st, b = http("GET", f"/api/v1/user/check-limit?type={t}", token)
        try:
            j = json.loads(b)
        except Exception:
            j = {}
        d = j.get("data") or {}
        print(f"{t:22s} st={st} {j.get('message','')[:40]:42s} "
              f"allowed={d.get('allowed')} remaining={d.get('remaining')}/{d.get('total_limit')}")

    print("\n## t2v 参数维度")
    for label, body in [
        ("aspect 16:9 + ai_sound=1", {"prompt": "a red sports car drifting on wet asphalt, cinematic", "aspect_ratio": "16:9", "ai_sound": 1}),
        ("aspect 1:1", {"prompt": "a blooming lotus flower in a pond", "aspect_ratio": "1:1"}),
        ("超长 prompt 9000 字符", {"prompt": "x" * 9000}),
        ("空 prompt", {"prompt": ""}),
    ]:
        t0 = time.time()
        st, b = http("POST", "/api/v4/video/t2v", token, json.dumps(body), timeout=600)
        print(f"{label:26s} st={st} {time.time()-t0:5.1f}s {b[:220].decode(errors='replace')}")

    print("\n## CDN 直链可访问性")
    st, b = http("GET", "/api/v1/user/check-limit?type=t2v_prompt", token)
    print("配额余量:", b.decode(errors="replace")[:160])


if __name__ == "__main__":
    main()
