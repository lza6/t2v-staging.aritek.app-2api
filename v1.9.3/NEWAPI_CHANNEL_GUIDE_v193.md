# new-api 渠道接入文档 — AIVG (AI Video Generator v1.9.3, aritek)

> 目标读者：要在 new-api-Max 里落 AIVG 渠道的会话。**type 69 已实现**（`relay/channel/aivg/`，v1.9.1 时落地），
> v1.9.3 只做常量对齐，本文档给的是「v1.9.3 复测后的事实基线 + 已实现的映射」。
> 逆向依据：本目录 `REVERSE_REPORT_v193.md`（全部数据为 2026-10-29 实测）。

## 一、上游协议速查（全部实测 ✅）

| 项 | 值 |
|---|---|
| Base URL | `https://t2v.aritek.app` |
| Sign 头（固定白名单值） | `68d6165b72a7f2d8d17b0dc6fe9691abdf77c583` |
| 其他公共头 | `versionCode: 93`（服务端**不校验**，91/1/999 均通过）、`Ctry-Target: others`、`pt: `（空）、`User-Agent: okhttp/4.9.3`、`Device-Id: <32位hex>`、`Authorization: Bearer <JWT>` |
| Token bootstrap | `GET /api/v1/user/info`（免鉴权，任意 Device-Id）→ `{"data":{"token":"<JWT>","ttl":3600,"is_premium":false}}`；JWT payload 内 `user_id == device_id == Device-Id`、`user_type=guest` |
| 免费配额/号（guest） | t2v 10 · t2i 3 · i2i_edit 1 · i2i_edit_dual 3 · i2i_swap 3 · **image_enhance 100 · image_aging 100** · open_eyes 10 · expand/remover/bg 各 5；i2v 全系与 t2v_prompt_v2 = **Premium 402** |
| 号池扩容 | 配额耗尽返回 `429 / code=-22`，**换 Device-Id 即可**（bootstrap 无限签发，实测 50 并发签发零限流，无需代理池） |

### 端点与参数

| 能力 | 端点 | Body | 响应 | guest |
|---|---|---|---|---|
| 文生视频 | `POST /api/v4/video/t2v` | `{"prompt":"...", "aspect_ratio"?:"9:16"/"16:9"/"1:1", "ai_sound"?:0/1}` | **同步** `{"data":{"url":"…mp4"}}` | ✅ 10 |
| 文生图 | `POST /api/v4/image/t2i` | `{"prompt":["..."]}` ⚠️**数组**，可带 `code`(模板码) | 异步 `{"data":{"jobId":"…"}}` | ✅ 3 |
| 图生图 | `POST /api/v4/image/i2i` | multipart: `images`（**复数**）+ **`prompt`（必填）** + 可选 `code` | 异步 jobId | ✅ 1–3 |
| 图生视频 | `POST /api/v4/video/i2v` | multipart: `image`+`code`(+`prompt`) | 异步 jobId | ❌ 402 |
| 图片增强 | `POST /api/v4/image/enhance` | multipart: **`image`（单数!）** | 异步 jobId → `.jpg` | ✅ **100** |
| 图片变老 | `POST /api/v4/image/aging` | multipart: **`image`（单数）** | 异步 jobId | ✅ **100** |
| 轮询（免鉴权） | `POST /api/v1/generate/status` | `{"ids":["<jobId>"]}` | `data[].status: processing→succeeded/failed`、`data[].url` | ✅ |
| 配额查询 | `GET /api/v1/user/check-limit?type=<type>` | JWT 头 | `{"data":{"allowed","remaining","total_limit"}}` | ✅ |
| 模板目录（免鉴权） | `GET /api/v4/t2v/home?v=4` | — | 152 KB 模板/trending（`v=4`/`v=5` 同返回） | ✅ |
| 兑换码 | `GET /api/v1/redeem/check` | 头 `Redeem-Code` | — | ✅ |

- `type` 白名单（服务端报错回吐，共 22 个）：`t2v_prompt, t2v_prompt_v2, i2v_prompt, i2v_lora, i2v_swap, i2v_dance, i2v_dance_v2, t2i_prompt, i2i_edit, i2i_edit_dual, i2i_swap, image_enhance, image_aging, open_eyes, image_expand, object_remover, background_generator, i2v_r2v, i2v_r2v_v2, i2v_r2v_dual, i2v_r2v_fl, i2v_r2v_ii`
- 产物：视频 `sora.aritek.app/generated/*.mp4`（h264，320×576 或 360×640，4–5s，**恒带 aac 音轨**）；图片 `sora.aritek.app/generates/YYYYMMDD/<jobId>.png|jpg`
- **CDN 访问策略（v1.9.3 变更）**：不再校验 Sign/Bearer，只挡空 UA（Cloudflare `error code: 1010`）。浏览器/播放器直连可用；脚本下载需带任意 UA。
- `aspect_ratio` / `ai_sound` 对 guest **不生效**（三组参数对照 ffprobe 一致），不要作为卖点或计费维度。

## 二、已实现的 new-api 映射（type 69）

| 项 | 值 |
|---|---|
| 渠道 type | `69`（`constant.ChannelTypeAIVG`，名称 `AIVG`） |
| 适配器 | `relay/channel/aivg/`（`adaptor.go` + `do_request.go`） |
| JS 任务插件 | `plugins/tasks/aivg/plugin.js`（task 平台 video 生成） |
| 模型名 | `aivg-t2v`（同步视频）· `aivg-t2i`（异步图） |
| 上游常量 | `baseURL=https://t2v.aritek.app`、`signValue=68d6165b…c583`、`versionCode=93`、`UA=okhttp/4.9.3` |
| prompt 预限 | **5000 字符**（上游硬限，超出 `code=-6`） |
| 号池 | 每请求 `deviceID()` 随机 32 位 hex → `bootstrap()` 拿 JWT → 调生成端点；1.9.3 无需持久化号池（签发零成本） |
| 渲染 | 视频 `[video](url)`、图片 `[image](url)`；同时 `common.AddMediaArtifact` 登记媒体直链 |
| 超时 | t2v 同步 300s（实测冷启动最慢 90.3s）；t2i 轮询 5s×36=180s |

### 变更记录（v1.9.1 → v1.9.3）

```diff
- versionCode = "91"
+ versionCode = "93"          # 服务端不校验，仅与 APK 对齐
- if len(prompt) > 4096 { prompt = prompt[:4096] }   // 注释：上游 10KB 拒收
+ if len(prompt) > 5000 { prompt = prompt[:5000] }   // 实测硬限 5000 字符 code=-6
```

`plugins/tasks/aivg/plugin.js` 的 `VERSION_CODE` 同步 `91 → 93`。
验证：`go test ./relay/channel/aivg/` → 2 passed。

## 三、号池与容量规划

| 口径 | 数值 |
|---|---|
| 单设备 t2v | 10 次（实测第 11 次 `429 code=-22`） |
| 单设备全类型合计 | ≈ 237 次（t2v 10 + t2i 3 + i2i 4 + enhance 200 + 其它 20） |
| bootstrap 成本 | 1 次 GET ≈ 2.6s（p50），无 IP 限流（30 并发 8.9s、50 并发零失败） |
| t2v 吞吐 | 并发 8 → 8/8，p50 3.8s / p90 5.3s；并发 20 见 `evidence/stress2_*.json` |
| 结论 | **吞吐只受上游生成队列约束，不受号源约束** → 不需要代理池，不需要预养号 |

## 四、错误码 → new-api 处理建议

| 上游 | 建议处理 |
|---|---|
| `400 code=-1 Prompt is required` | 直接 400 回客户端（参数错误，不消耗额度） |
| `400 code=-6 Prompt is too long (max 5000)` | 网关层已预截断到 5000，不应出现 |
| `402 code=-21 Premium subscription required` | 该 type 不对 guest 开放 → 渠道配置里不要挂 i2v 模型 |
| `429 code=-22 Rate limit exceeded` | **单设备配额耗尽** → 换号重试（不是 IP 限流，不要上代理） |
| `401 code=-2 Missing or invalid Authorization` | JWT 失效 → 重新 bootstrap 后重试 |
| `404 code=-4 Route not found` | 路径写错，不要重试 |
| `500 code=-10 Internal server error` | body 形态错（JSON↔multipart 走错）或上游抖动 → 重试 1 次后失败 |

## 五、验收清单（照抄即可）

1. `GET /api/v1/user/info`（带 Sign/versionCode/Ctry-Target/Device-Id）返回 `data.token`。
2. `GET /api/v1/user/check-limit?type=t2v_prompt` 返回 `remaining=10`。
3. `POST /api/v4/video/t2v {"prompt":"..."}` 返回 `data.url` 且**裸 UA 可下载**。
4. `POST /api/v4/image/t2i {"prompt":["..."]}` → jobId → 轮询 `succeeded` 并有 url。
5. 同一 Device-Id 连打 11 次 t2v：第 11 次 `429/-22`（证明号池轮换是必需的）。
6. 换 Device-Id 后立刻恢复 200（证明号源不是瓶颈）。

## 六、待办（未实施，需拍板）

- `image_enhance` / `image_aging`（100 次/设备，3s 出 JPG，multipart 字段 `image` 单数）**尚未接入渠道**，性价比高于 t2v，建议独立 `aivgenh` 渠道。
- i2i（guest 1–3 次/设备）尚未接进 `aivg` 渠道；multipart 字段已实测：`images`(复数) + `prompt`(必填, 缺则 400) + 可选 `code`。
