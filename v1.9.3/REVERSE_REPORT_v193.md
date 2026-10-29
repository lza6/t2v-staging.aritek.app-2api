# AI Video Generator v1.9.3 (b93) 逆向 + 2API 第一轮交付报告

- 分析对象：`AI_Video_Generator_v1.9.3_(93)_Mod.apk`（60.9 MB，ElaMods 重打包）
- 包名 / 版本：`ai.video.generator.text.video` · versionName `1.9.3` · versionCode `93`（apktool 解码 `apktool.yml`）
- 上游：`https://t2v.aritek.app`（生产域名，v4 协议；`android-api-verify.aritek.app` 仅用于订阅校验）
- 分析时间：2026-10-29（本机 Windows，jadx 1.5.x 反编译 + 纯协议实测）
- 结论标签：`已验证`=实际运行观察 · `静态确认`=读反编译代码确认 · `待验证`=缺条件

---

## 0. 一句话结论

**v1.9.3 与 v1.9.1 的客户端协议完全同构，零协议破坏**：`Sign` 白名单值、`versionCode` 头、v4 路由、bootstrap→guest JWT 号池全部沿用即可用；
真正的变化发生在**服务端**——(a) 配额/能力矩阵大幅扩张（11 个功能对匿名 guest 免费），(b) 产物 CDN 去掉了 Sign/Bearer 校验（只剩 UA 墙），(c) `aspect_ratio` / `ai_sound` 参数**不生效**（恒竖屏 ~4.9s + 音轨），(d) prompt 硬限从 10KB 收敛为 **5000 字符**。
第一轮本地压测全绿：t2v 并发 8/8、bootstrap 并发 30/30、t2i 并发 4/4，单设备配额精确 10 次后 429。

---

## 1. 静态还原（`静态确认`）

### 1.1 关键类

| 位置 | 作用 |
|---|---|
| `ai.video.generator.text.video.apiservice.HeaderInterceptor` | 注入全部请求头：`Sign` / `pt` / `Ctry-Target` / `versionCode=93` / `Authorization: Bearer <user_token>` / `Device-Id` / `Redeem-Code` |
| `S4.e`（混淆类，即 ApkSignatureKiller 的 `killPM`） | `Sign` 值的唯一来源：字段初值 `""`，运行时由 `com.bumptech.glide.d.f(context)` 从**内嵌原版证书**算 SHA1 回填 |
| `e.b`（Retrofit 接口） | 11 个端点（见 1.2） |
| `e.a` | OkHttp 客户端 3 套（超时 60s/60s/10s，`addInterceptor(HeaderInterceptor)`，`pc.b` = 日志拦截器 level 4） |
| `ai.video.generator.text.video.model.*` | 请求/响应模型（CreateVideoRequest / TextToImageBody / GenVideo / Limit / User …） |
| `utils.okhttp.LoggingCDNInterceptor` / `LoggingWorkerApiInterceptor` | 调试日志拦截器**未删除**（这也是 v1.9.1 能靠 `logcat | grep okhttp` 抓包的根因） |

`api_url` 走 SharedPreferences 覆盖，默认值写死 `https://t2v.aritek.app/`（`e.a.b()` / `e.a.c()`）。

### 1.2 端点全表（Retrofit 注解，`E/b.java`）

| 方法 | 路径 | 用途 | guest 可用 |
|---|---|---|---|
| GET | `/api/v1/user/info` | 免鉴权 bootstrap → guest JWT（ttl 3600） | ✅ |
| GET | `/api/v1/user/check-limit?type=` | 配额查询（`type` 是 **query 参数**） | ✅ |
| POST | `/api/v4/video/t2v` | 文生视频，**同步**返回 MP4 url | ✅ 10/设备 |
| POST | `/api/v4/video/i2v` | 图生视频（单图 `c(@q z)` / 多图 `e(@q List<z>)`，multipart） | ❌ 402 premium |
| POST | `/api/v4/image/t2i` | 文生图，body `{"prompt":["..."],"code"?}` → `jobId` | ✅ 3/设备 |
| POST | `/api/v4/image/i2i` | 图生图（multipart `images` 复数） | ✅ i2i_edit 1 / i2i_swap 3 / i2i_edit_dual 3 |
| POST | `/api/v1/generate/status` | 轮询 `{"ids":[jobId]}`，**免鉴权** | ✅ |
| POST | `/api/v1/moderation/check-input` | 输入审核（multipart 图） | ✅ |
| POST | `/api/v1/moderation/check-output` | 输出审核（multipart 图） | ✅ |
| GET | `/api/v1/redeem/check` | 兑换码（`Redeem-Code` 头） | ✅ |
| GET | `/api/v4/t2v/home?v=N` | 首页模板目录（152 KB，v=4/v=5 同返回） | ✅ |

### 1.3 请求模型（服务端字段名以实测为准）

- **t2v body**：`{"prompt": str, "aspect_ratio"?: str, "ai_sound"?: int}` —— 实测最小 body `{"prompt":...}` 即可成功。
- 客户端还有一个 `CreateVideoRequest{prompt, versionCode, deviceID, isPremium, ctry_target, used[], aspect_ratio, ai_sound}` 模型，属于模板/复刻链路（`used` = 已用模板 code 列表），**guest 的 t2v 不需要它**（传了也 200，服务端以 `prompt` 为准）。
- **t2i body**：`{"prompt": ["str"], "code"?: 模板码}` —— ⚠️ `prompt` 是**数组**，这是 v4 协议最容易踩的坑。
- **i2i**：multipart，文件字段 `images`（复数）+ 文本 **`prompt`（必填！缺则 400 `Prompt is required`）** + 可选 `code`。
- **JWT payload**（实测解码）：`{user_id, is_premium:false, device_id, sign, ctry_target:"others", user_type:"guest", subscriptionPlan:"unknown", iat, exp}`。
  `user_id == device_id == 我们自己编的 Device-Id`，`sign` 字段回显白名单值 —— **号池即「随机 Device-Id 池」**，无任何注册成本。

### 1.4 关键常量

```text
BASE          https://t2v.aritek.app
Sign 头       68d6165b72a7f2d8d17b0dc6fe9691abdf77c583
versionCode   93  （服务端不校验，见 3.3）
Ctry-Target   others            pt  （空串）
User-Agent    okhttp/4.9.3
```

---

## 2. 动态实测：配额与能力矩阵（`已验证`）

同一 guest JWT 下逐个 type 查 `/api/v1/user/check-limit`（2026-10-29）：

| type | 结果 | 额度/设备 |
|---|---|---|
| `t2v_prompt` | 200 allowed | **10** |
| `t2i_prompt` | 200 allowed | **3** |
| `i2i_edit` | 200 allowed | **1** |
| `i2i_edit_dual` | 200 allowed | **3** |
| `i2i_swap` | 200 allowed | **3** |
| `image_enhance` | 200 allowed | **100**（同一后端！见 §6） |
| `image_aging` | 200 allowed | **100** |
| `open_eyes` | 200 allowed | 10 |
| `image_expand` / `object_remover` / `background_generator` | 200 allowed | 各 5 |
| `t2v_prompt_v2` | **402 Premium required** | — |
| `i2v_prompt` / `i2v_lora` / `i2v_swap` / `i2v_dance` / `i2v_dance_v2` | **402** | — |
| `i2v_r2v` / `i2v_r2v_v2` / `i2v_r2v_dual` / `i2v_r2v_fl` / `i2v_r2v_ii` | **402** | — |

> type 白名单由服务端一次性回吐（`Invalid or missing type param. Allowed: ...`），共 22 个，说明 `t2v.aritek.app` 是 **aritek 家族多 App 共用后端**：本 APK 只用其中 11 个路由，`image_enhance` 等属于同门「图片增强」产品线。

**号池容量推算（每设备）**：t2v 10 + t2i 3 + i2i 4 + enhance 200 + 其它 20 ≈ **237 次免费生成**；
换算成 t2v 口径：**10 次/设备**，bootstrap 无 IP 限流（§5 R2：8.9s 内 30 次签发零失败），因此**理论吞吐只受上游生成队列约束**。

### 2.1 错误码表（`已验证`）

| HTTP | code | message | 触发条件 |
|---|---|---|---|
| 400 | -1 | `Prompt is required` | prompt 空 |
| 400 | -6 | `Prompt is too long (max 5000 characters)` | prompt 超 5000 字符 |
| 400 | -1 | `Invalid or missing type param. Allowed: ...` | check-limit 的 type 非法 |
| 400 | -1 | `Device-Id, Sign, and Ctry-Target headers are required` | 缺头 |
| 401 | -2 | `Missing or invalid Authorization header` | 生成类端点缺 JWT |
| 402 | -21 | `Premium subscription required` | premium 类型（i2v 全系 / t2v_prompt_v2） |
| 404 | -4 | `Route not found` + `data.resource` | 路由不存在（可用于路由发现） |
| 429 | -22 | `Rate limit exceeded` | **单设备配额耗尽**（不是 IP 限流） |
| 500 | -10 | `Internal server error` | 路由存在但 body 形态不对（JSON↔multipart 走错） |

配额耗尽后 `check-limit` 会带 **`retry_after`（秒，实测 32733 ≈ 9.1 小时）**，即按自然日/滚动 24h 重置 —— 号池轮换是唯一即时恢复手段。

---

## 3. 参数与语义实测（`已验证`）

### 3.1 `aspect_ratio` / `ai_sound` 对 guest **不生效**

三组不同 prompt + 不同参数，产物用 ffprobe 校验：

| 请求 | 实际产物 |
|---|---|
| `aspect_ratio=16:9, ai_sound=1` | 360×640（竖屏）· h264 + **aac** · 4.87s |
| `aspect_ratio=9:16, ai_sound=0` | 360×640 · h264 + **aac** · 4.08s |
| `aspect_ratio=1:1, ai_sound=1` | 320×576 · h264 + **aac** · 4.87s |

结论：**输出恒为竖屏短片（320×576 / 360×640，约 4–5s，始终带 AAC 音轨）**；`ai_sound=0` 也照样有音轨，说明这两个字段只在 premium/v2 通道被消费。→ 网关层不要把它们当作「确定性参数」向用户承诺。

### 3.2 同 prompt 命中结果缓存

同一 prompt 连续请求返回**完全相同的 url / 文件大小**（586430 bytes 复现多次），说明服务端按 prompt 做了产物缓存。
影响：压测/复用场景下「不同 prompt」才代表真实成本，同 prompt 会把延迟与额度推算失真。

### 3.3 `versionCode` 服务端不校验

`versionCode` 分别取 `91` / `93` / `1` / `999`：bootstrap 与真实 t2v **全部 200**。→ 该头只是埋点/风控信号，升级 APK 不会因版本号被墙；仍建议与 APK 对齐取 `93`。

### 3.4 t2v 延迟分布（同步出片）

| 场景 | 实测 |
|---|---|
| 热池并发 8（独立设备） | p50 3.80s / p90 5.30s / avg 3.96s |
| 单请求冷启动 | 7.6s / 38.3s / **90.3s**（抖动极大） |
| 库自测单发 | 2.0–4.1s |

→ 网关侧 t2v 超时必须 ≥ 300s（现有 `aivg` 渠道正好 300s，无需改）。

### 3.5 t2i 异步链路存在「僵尸 job」

`POST /api/v4/image/t2i` → `jobId` → `/api/v1/generate/status` 轮询：
- 正常：3–18s 变 `succeeded`；
- 异常：**观察到 1 个 job 轮询 4 分钟后仍 `processing`，永不失败**（同一 device 后续请求正常）。
→ 客户端必须有 deadline 且按超时失败，绝不能无界等待（渠道层 180s 轮询上限保留是正确设计）。

---

## 4. 产物 CDN 策略变更（`已验证`）

`sora.aritek.app` 直链访问矩阵（mp4 + png 各测一遍，结论一致）：

| 请求头 | 结果 |
|---|---|
| 空 UA（`Python-urllib/3.x`） | **403 `error code: 1010`**（Cloudflare UA 拦截） |
| 任意 UA（`okhttp/4.9.3` / 浏览器） | 200 |
| 仅 Sign / 仅 Bearer / Sign+Bearer | 200（**与签名无关**） |

→ v1.9.1 时代「CDN 必须带 Sign+Bearer 否则 403」的坑**已消失**，现在只剩 Cloudflare 空 UA 墙：浏览器直接打开、播放器直连、`new-api` 前端渲染都没问题。若用脚本下载，记得带 UA。

---

## 5. 第一轮本地压测（`已验证`，证据 `evidence/stress_20261029-222255.json`）

环境：本机直连（无代理），`requests` 客户端，每请求独立 Device-Id。

| 场景 | 并发 | 结果 | 延迟 |
|---|---|---|---|
| **R1 t2v** | 8 | **8/8 成功（100%）**，wall 5.3s | p50 3.80s / p90 5.30s / avg 3.96s |
| **R2 bootstrap** | 30（worker 15） | **30/30 成功（100%）**，wall 8.9s | p50 2.61s / p99 5.85s |
| **R3 t2i（异步+轮询）** | 4 | **4/4 成功（100%）**，wall 17.7s | p50 12.46s / p90 17.69s |
| **R4 单设备打尽配额** | 串行 12 | **前 10 次 200 出片，第 11 次 429 `code=-22`** | 1.65–3.03s |

R4 是配额语义的**决定性证据**：`t2v` 额度精确 = 10 次/设备，第 11 次被拒（不是 429 IP 限流，因为同 IP 其它设备不受影响）。
号池策略结论：**用尽即换 Device-Id** 是唯一正确的扩容方式，无需代理池。

---

## 6. 意外发现：同后端「图片增强」对 guest 免费 100 次/设备

`image_enhance` / `image_aging` 在 check-limit 中显示 `remaining 100/100`，且路由真实存在：

```http
POST https://t2v.aritek.app/api/v4/image/enhance
headers: sign / versionCode / Ctry-Target / Authorization: Bearer <guest JWT> / Device-Id
body:    multipart/form-data  —— 文件字段名 = image（单数）
resp:    {"code":0,"data":{"jobId":"..."}}   → /api/v1/generate/status → .jpg
```

实测：上传一张 1 MB PNG → **3 秒内** 产出增强 JPG（`sora.aritek.app/generates/.../*.jpg`，496 KB），额度 100/设备/天。
同一 multipart 用字段 `images`（复数）会被判 `400 Image is required`，用 JSON body 直接 `500` —— 字段形态极其严格。

其余免费类型（`open_eyes` / `image_expand` / `object_remover` / `background_generator` / `i2i_swap`）的路由**不在** `/api/v4/image/*` 命名空间下（逐个 404 排除），属于家族里另一个 App 的客户端路径，需要装那个 APK 才能静态还原 —— 本机 `AI Video Enhancer - Utool v1.202.84` 已确认**不是** aritek 系（dex 内无 aritek 域名、无 api/v4 路由），是第三方产品，不能用于此线索。

> 价值判断：这条线把「每设备免费额度」从 13 次（t2v+t2i+i2i）拉到 **200+ 次图片类**，若要做图片增强渠道，是比 t2v 更肥的池子。**需要你拍板是否开一条独立的 `aivg-enhance` 渠道**。

---

## 7. 交付物

| 文件 | 说明 | 状态 |
|---|---|---|
| `aivg193.py` | 协议客户端库：`AivgClient`（bootstrap/check-limit/t2v/t2i/i2i/poll）+ `DevicePool`（线程安全号池，按 type 预扣额度、用尽换号） | 已验证 |
| `demo_server.py` | 本地网关 `:8916`：`/t2v` `/t2i` `/v1/chat/completions` `/v1/images/generations` `/health` `/stats` | 已验证 |
| `demo.html` | 单页 demo（深色 UI，4 种接口切换、实时号池面板、耗时/设备/日志） | 浏览器已验证（3 条路径 + 截图 `evidence/ui_*.png`，控制台 0 error） |
| `stress_test.py` | 第一轮 4 场景压测（R1–R4），输出 JSON 证据 | 已验证 |
| `stress_test2.py` | 第二轮 6 场景压测（S1–S6：50 并发签发 / 20 并发出片 / 僵尸率 / i2i / prompt 边界 / 配额独立性） | 已验证 |
| `verify_ui.py` | Playwright 真实浏览器路径验证 | 已验证 |
| `probe.py` … `probe5.py` | 协议探针（bootstrap/配额矩阵/参数维度/路由发现/CDN 头策略） | 已验证 |
| `evidence/` | `stress_*.json`、`ui_*.png`、`ev_*.mp4/.png` | — |

复现：

```powershell
cd D:\aivg193
python aivg193.py            # 库自测：bootstrap + 真实出片
python demo_server.py        # 起网关  http://127.0.0.1:8916/
python stress_test.py        # 4 场景压测 → evidence/stress_*.json
python verify_ui.py          # Playwright 浏览器验证 → evidence/ui_*.png
```

---

## 8. new-api 渠道同步（已改，定向测试通过）

`relay/channel/aivg/` + `plugins/tasks/aivg/plugin.js` 按 v1.9.3 事实修正（**协议无破坏性变更**，只是把常量与上限对齐实测）：

| 文件 | 变更 | 依据 |
|---|---|---|
| `relay/channel/aivg/adaptor.go` | `versionCode` `91` → `93`；包注释补 v1.9.3 复测结论（Sign 不变 / 版本不校验 / 5000 字符 / aspect 不生效 / CDN 只挡 UA） | §1.4 §3.1 §3.3 §4 |
| `relay/channel/aivg/do_request.go` | prompt 预限 `4096` → `5000` 字符（原注释「上游 10KB 拒收」与实测不符） | §2.1 code=-6 |
| `plugins/tasks/aivg/plugin.js` | `VERSION_CODE` `91` → `93` | §1.4 |

验证：`go test ./relay/channel/aivg/` → **2 passed**（`TestDeviceID` / `TestExtractPrompt`）。
未跑全量构建：本次仅改常量与注释，风险 L1；如需上线再走 `scripts/staging.ps1 verify` + 蓝绿。

---

## 9. 已知坑清单（v1.9.3 版）

1. **t2i 的 `prompt` 是数组**，传字符串直接 400/500。
2. **`enhance` 的 multipart 字段是 `image` 单数**，`images` 复数会被拒。
2b. **`i2i` 的 `prompt` 是必填文本字段**，只传 `images` 会 `400 Prompt is required`。
3. **CDN 空 UA = 403**（Cloudflare 1010），脚本下载必须带 UA；不需要 Sign/Bearer。
4. **同 prompt 命中缓存**，压测要用不同 prompt。
5. **t2i 会出现永不完成的僵尸 job**，必须有 deadline。
6. **429 `-22` 是配额耗尽，不是 IP 限流** —— 换 Device-Id 即可，别浪费时间上代理池。
7. **t2v 冷启动可达 90s**，超时阈值 ≥ 300s。
8. `aspect_ratio` / `ai_sound` 对 guest 无效，别当卖点。
9. `check-limit` 的 `type` 是 query 参数（jadx 注解陷阱，老坑复现）。
10. 服务端会回吐 22 个 type，**其中 11 个 premium 402**，不要按名猜额度，先查 check-limit。

---

## 10. 下一步（等你拍板）

1. **是否把 enhance/aging 做成独立渠道**（100 次/设备、3s 出图，性价比远高于 t2v）——需要新增 `relay/channel/aivgenh` + 模型定价。
2. **是否补 i2i 进现有 aivg 渠道**（guest 可用，额度 1+3+3/设备，multipart 已探明）。
3. **是否把本报告 + demo/压测脚本推到 GitHub**（`lza6/t2v-staging.aritek.app-2api` 的 `v1.9.3/` 子目录，与 `v1.9.1/` 并列）。
4. 第二轮压测可加：50 并发号池压力、i2i 真实上传链路、t2i 僵尸 job 概率统计（100 次采样）。

---

## 11. 第二轮压测（更深，`已验证`，证据 `evidence/stress2_20261029-224737.json`）

| 场景 | 规模 | 结果 | 关键数据 |
|---|---|---|---|
| **S1 bootstrap 签发天花板** | 50 并发（worker 25） | **50/50（100%）**，wall 11.2s | p50 3.73s / p90 5.74s / max 9.47s —— **签发侧无 IP 限流** |
| **S2 t2v 高并发出片** | 20 并发（独立设备） | **20/20（100%）**，wall 8.2s | p50 **7.04s** / p90 8.09s（并发 8 时 p50 3.80s → **排队带来的延迟退化约 1.9×**） |
| **S3 t2i 僵尸 job 概率** | 20 采样，120s deadline | 19 成功 / **1 卡死（5%）** | p50 27.7s / p90 33.4s（比单发 12.5s 明显变慢） |
| **S4 i2i 真实上传** | 2 次 | 修正后 **通过**（见下） | 上传 1 MB PNG + prompt → 3s 内出图，额度 1→0，`retry_after=32793` |
| **S5 prompt 边界** | 4999 / 5000 / 5001 | 4999 ✅ 5000 ✅ **5001 ✗ `code=-6`** | 硬限精确落在 **5000 字符** |
| **S6 跨 type 配额独立性** | 同设备打 t2v/t2i/i2i | t2v ✅ t2i ✅ i2i ✅ | `10/3/1 → 9/2/1` —— **三类计数彼此独立**，互不占用 |

### S4 的坑与修正（重要）

首轮 S4 用「只传 `images` 不传 prompt」的方式调 i2i，被上游 `400 Prompt is required` 拒绝；补上 `prompt` 文本字段后一次通过：

```python
# ❌ 只传图
files = [("images", ("in.png", png, "image/png"))]; data = {}
# ✅ 图 + prompt 必填
files = [("images", ("in.png", png, "image/png"))]
data  = {"prompt": "turn it into an oil painting, thick brush strokes"}
# → {"code":0,"data":{"jobId":"..."}} → /api/v1/generate/status → *.png
```

`aivg193.py` 的 `AivgClient.i2i()` 已把 `prompt` 改为必填参数并做本地校验，回归实测：
`i2i ok: https://sora.aritek.app/generates/20261029/1793285650805_5d1ed81f4b5c49f4.png`，随后 `check-limit` 返回 `allowed=false, remaining=0, retry_after=32733`。

### 第二轮得出的运营结论

1. **号源不是瓶颈**（50 并发签发零失败），**生成队列才是**（20 并发出片 p50 从 3.8s 涨到 7.0s）。
2. **t2i 有 5% 僵尸率**，渠道层必须靠 deadline 失败并归还配额，不能无限等。
3. 建议线上并发上限 **≤10**（p50 仍 < 5s，且不给上游制造排队），号池按 type 分别计数（S6 已证独立）。

