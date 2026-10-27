# new-api 渠道接入文档 — AIVG (AI Video Generator v1.9.1, aritek)

> 目标读者：新会话直接照此文档在 new-api-Max 里实现 type=67（建议值）渠道。
> 参考实现：`relay/channel/imagerator/`（type 66，同为"号池型 2API 渠道"，结构最接近，照抄骨架即可）。
> 逆向依据：`lza6/t2v-staging.aritek.app-2api` 仓库 `v1.9.1/REVERSE_REPORT_v191.md`。

## 一、上游协议速查（全部实测 ✅）

| 项 | 值 |
|---|---|
| Base URL | `https://t2v.aritek.app` |
| Sign 头（固定白名单值） | `68d6165b72a7f2d8d17b0dc6fe9691abdf77c583` |
| 其他公共头 | `versionCode: 91`、`Ctry-Target: others`、`pt: `（空）、`User-Agent: okhttp/4.9.3`、`Device-Id: <32位hex>`、`Authorization: Bearer <JWT>` |
| Token bootstrap | `GET /api/v1/user/info`（免鉴权，任意 Device-Id）→ `{"data":{"token":"<JWT>","ttl":3600}}`，user_id=device_id=Device-Id |
| 免费配额/号 | t2v 10、t2i 3、i2i 1（`check-limit?type=`），用尽换 Device-Id 即可（服务端不强制 i2v 的 Premium 检查） |

### 端点与参数（Body 全部 JSON 除注明 multipart）

| 能力 | 端点 | Body | 响应 |
|---|---|---|---|
| 文生视频 | `POST /api/v4/video/t2v` | `{"prompt":"...", "aspect_ratio":"9:16"\|"16:9"\|"auto", "ai_sound":"0"\|"1"}` | **同步** `{"data":{"url":"…mp4"}}` |
| 文生图 | `POST /api/v4/image/t2i` | `{"prompt":["..."]}` ⚠️**数组** | 异步 `{"data":{"jobId":"…"}}` |
| 图生视频 | `POST /api/v4/video/i2v` | multipart: `image`(文件)+`code`(模板code)+`prompt` | 异步 jobId |
| 图生图 | `POST /api/v4/image/i2i` | multipart: `images`(**复数**)+`code` | 异步 jobId |
| 轮询（免鉴权） | `POST /api/v1/generate/status` | `{"ids":["<jobId>"]}` | `data[].status: processing→succeeded/failed`，`data[].url` |
| 模板目录（免鉴权） | `GET /api/v3/t2v/home?v=3` | — | i2v/i2i 模板 code 源 |
| 配额查询 | `GET /api/v1/user/check-limit?type=t2v_prompt` | header 带 JWT | `{"data":{"allowed","remaining","total_limit"}}` |

- 产物域名：视频 `sora.aritek.app/generated/*.mp4`（≈5s，无 duration 参数，时长由模型 ft3.1.0 决定）；图片 `sora.aritek.app/generates/YYYYMMDD/<jobId>.png`
- `ai_sound=1` 实测带 aac 音轨；非法 aspect_ratio 静默回退不报错
- 限流：10 并发无 429；运营建议 ≤5 并发 + 号池轮换

## 二、建议的 new-api 映射

### 渠道定义（type=67，名字 `aivg`）
- `relay/channel/aivg/adaptor.go`：照抄 `imagerator/adaptor.go` 骨架（提交+轮询收敛在 DoRequest 内）
- `relay/channel/aivg/pool.go`：照抄 imagerator 三级号池（本地池 → bootstrap 新号 → 持久化 JSON/DB）
- `meta.ChannelMeta` 建议存 BaseURL + Sign（Sign 是常量，也可硬编码）

### 模型映射（模型名由我们自定义，客户端任意起）
| new-api 模型名 | 上游 | 模式 |
|---|---|---|
| `aivg-t2v` | `/api/v4/video/t2v` | 同步 |
| `aivg-t2i` | `/api/v4/image/t2i` | 异步轮询 |
| `aivg-i2v` | `/api/v4/video/i2v` | multipart 异步 |
| `aivg-i2i` | `/api/v4/image/i2i` | multipart 异步 |

### 关键实现点（防踩坑）
1. **t2i 的 prompt 是数组**（`["…"]`），t2v 是字符串 — 不要统一
2. i2v 字段 `image` 单数、i2i 字段 `images` 复数 — 服务端不对称
3. token 有 1h TTL：池内每号存 token+exp，提前 120s 刷新；bootstrap 失败（偶发 WinError 10054 类连接重置）重试一次
4. 计数扣减：**成功响应才扣**（`code==0`），失败不扣防止配额虚耗
5. `check-limit` 参数名是 `type`（不是 ad_type；ad_type 是 jadx 里 `@t(KEY_AD_TYPE)` 常量误导，实际值 `"type"`）
6. 轮询间隔 4-8s，最多 ~15 次（t2i 实测 ≤10s 出图，i2v 最长 ~1min）
7. 上游偶发返回 `code:0` 但 URL 空 → 视为 failed 重试一次（换号）
8. 计费：按次计费。参考 `pkg/billingexpr` 或简单 PerCall 价格；t2v 建议价 > t2i（上游成本 10:3 配额比反推）

### 安全红线（AGENTS.md 硬性要求）
- 计费乘数边界：prompt 长度上限（实测 10KB 会被上游拒，建议 4KB 预限）、图片大小上限（App 客户端限制 ~10MB，建议 8MB）
- quota 换算一律走 `common/quota_math.go` helpers，禁止裸 cast
- 渠道密钥字段存 Sign 白名单值 + 可选代理池（出站 IP 可能被 CF 关联，多号同 IP 高频需观察）

## 三、验证清单（实现后逐条跑）
1. `cd relaykit && GOWORK=off go build ./...`（若动了 relaykit）
2. 三库兼容：不动表结构可只跑 SQLite；若加号池表则按 AGENTS.md 三库矩阵
3. 真实 E2E：`aivg-t2i` 出 PNG URL、`aivg-t2v` 出 MP4 URL（各 ≥2 次）
4. 号池轮换：同号连发 4 次 t2i → 第 4 次自动换号
5. `/health` 或管理页能看到池状态
