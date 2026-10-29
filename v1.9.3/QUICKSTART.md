# AIVG v1.9.3 (b93) 纯协议 2API

`ai.video.generator.text.video` v1.9.3 的协议级复现：**不需要 APK、模拟器、Frida、代理池**。

```text
BASE  https://t2v.aritek.app
Sign  68d6165b72a7f2d8d17b0dc6fe9691abdf77c583
号池  任意 32 位 hex Device-Id  → GET /api/v1/user/info 免鉴权签发 guest JWT(3600s)
额度  t2v 10 / t2i 3 / i2i 4 / image_enhance 100  ...（每 Device-Id，用尽换号）
```

## 快速开始

```powershell
cd D:\aivg193
python aivg193.py          # 库自测：bootstrap + 真实出片（返回 sora.aritek.app 直链）
python demo_server.py      # 本地网关 → http://127.0.0.1:8916/
python stress_test.py      # 压测 → evidence/stress_*.json
python verify_ui.py        # Playwright 浏览器验证 → evidence/ui_*.png
```

依赖：`python>=3.10`、`requests`；浏览器验证需 `playwright`；产物校验需 `ffprobe`。

## 网关接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | demo 页面 |
| POST | `/t2v` | `{"prompt":"...","aspect_ratio":"9:16","ai_sound":0}` → `{type,url,device,elapsed_ms}` |
| POST | `/t2i` | `{"prompt":"..."}` → 异步轮询后返回 `{type,url}` |
| POST | `/v1/chat/completions` | OpenAI 兼容；`model=aivg-t2v`/`aivg-t2i`，返回 `[video](url)` |
| POST | `/v1/images/generations` | OpenAI 图像协议，`n<=3` |
| GET | `/health` `/stats` | 健康 / 号池统计 |

## 库用法

```python
from aivg193 import AivgClient, DevicePool

c = AivgClient()                    # 自动生成 Device-Id
c.bootstrap()                       # guest JWT
print(c.check_limit("t2v"))         # {'allowed': True, 'remaining': 10, 'total_limit': 10}
print(c.t2v("a lighthouse in a storm, cinematic"))
print(c.t2i("an isometric greenhouse, digital art"))
print(c.i2i([("in.png", open("in.png","rb").read())]))   # multipart 字段 images

pool = DevicePool()                 # 号池：按 type 预扣额度，用尽即换新 Device-Id
d = pool.acquire("t2v")
print(d.client.t2v("a hot air balloon over a canyon"))
print(pool.snapshot())
```

## 硬约束（踩过的坑）

- `t2i` 的 `prompt` 是**数组**；`enhance` 的 multipart 字段是 `image`（单数）。
- prompt 上限 **5000 字符**（超出 `code=-6`）；空 prompt `code=-1`。
- `429 code=-22` = 单设备配额耗尽 → **换 Device-Id**，不是 IP 限流。
- `aspect_ratio` / `ai_sound` 对 guest 不生效（恒竖屏 320×576/360×640，约 4–5s，含 aac 音轨）。
- 产物 CDN `sora.aritek.app` 只挡空 UA（Cloudflare 1010），**不需要** Sign/Bearer。
- t2v 冷启动可达 90s（超时 ≥300s）；t2i 偶发僵尸 job（永不 failed，必须 deadline）。

完整逆向结论见 `REPORT.md`。
