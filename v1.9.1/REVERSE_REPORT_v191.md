# AIVG (AI Video Generator) v1.9.1 b91 逆向报告 — 全链路打通版

> 对象: `AI Video Generator v1.9.1 b91 (Premium By ElaMods).apk`（包名 `ai.video.generator.text.video`，aritek）
> 上一版: [1.8.8 报告（../README.md）](../README.md) | 解包目录: `D:/aivg191/b91-{extract,apktool,jadx}/`
> 状态: ✅ **token bootstrap 已打通，t2v/t2i 真实出片**

## 一、版本对比 1.8.8 → 1.9.1 b91

| 项 | 1.8.8 (v88) | 1.9.1 (b91) |
|---|---|---|
| API base | `t2v-staging.aritek.app` | **生产 `t2v.aritek.app`**（远程配置 `api_url_2` 可覆盖，模拟器实测 app 仍被配到 staging） |
| 协议 | v3 | **v4**（`/api/v4/video/t2v`、`/api/v4/image/t2i`、`i2v`、`i2i`） |
| 新增端点 | — | `moderation/check-output`、`api/v1/redeem/check` |
| 重打包证书 | AOSP testkey `61ed377e…` | ElaMods/HEMANT，SHA1 `1f7644d2…8004` |
| versionCode 头 | 88 | 91 |

## 二、协议核心

### Sign 头（本次最大发现 ⭐）
jadx 静态分析显示 `Sign = SHA1(运行时APK证书)`（`p247x3.a.i()`），但**服务端实际白名单校验**。模拟器（AVD API 30）+ frida-server 16 实测 App 运行时发出的请求头（okhttp 日志拦截器自打 logcat）：

```
Sign: 68d6165b72a7f2d8d17b0dc6fe9691abdf77c583   ← 白名单值（非任何已知证书 SHA1）
versionCode: 91
Ctry-Target: others
pt: (空)
Device-Id: <16位hex，任意伪造>
Authorization: Bearer <JWT 或空>
```

**只要 Sign 用这个固定值，`user/info` 免鉴权**（6 种其他证书 SHA1 全被拒 `Invalid signature`）。

### token bootstrap（1.8.8 的缺口，本次打通 ✅）
```
GET /api/v1/user/info   (headers: Sign=68d6…583 + 任意 Device-Id)
→ {"code":0,"data":{"token":"<JWT>","ttl":3600,"is_premium":false}}
```
JWT payload 解码：`user_id = device_id = <Device-Id>`, `user_type:"guest"`, `exp = iat + 3600`。
**device_id 任意伪造 → 无限 guest 号池，每次 bootstrap 一个新号。**

### 端点清单（v4，全部实测）
| 端点 | 方法 | Body/参数 | 鉴权 | 实测 |
|---|---|---|---|---|
| `/api/v1/user/info` | GET | — | Sign 白名单即免鉴权 | ✅ 签发 JWT |
| `/api/v4/video/t2v` | POST | `{"prompt":"...", "aspect_ratio":"9:16"}` | JWT | ✅ **同步返回 MP4 URL** |
| `/api/v4/image/t2i` | POST | `{"prompt":["..."]}`（**数组！**） | JWT | ✅ 异步 jobId |
| `/api/v1/generate/status` | POST | `{"ids":["<jobId>"]}` | **免鉴权** | ✅ 轮询→`succeeded`+PNG URL |
| `/api/v1/user/check-limit` | GET | `?ad_type=t2v_prompt` 等 18 种 | JWT | ✅ |
| `/api/v1/moderation/check-input` | GET/POST | `?text=...`（@q Query） | JWT | 路由需 POST multipart（Query 形式 404，留待补测） |
| `/api/v3/t2v/home` | GET | `?v=3` | **免鉴权**（Sign 完全不校验） | ✅ 模板目录 |
| `/api/v1/redeem/check` | GET | header `Redeem-Code` | 无 | 假码 400 |

### 生成结果
- t2v: `https://sora.aritek.app/generated/t2p_*.mp4`（同步，~5-30s）
- t2i: `https://sora.aritek.app/generates/YYYYMMDD/<jobId>.png`（异步，~10s）

## 三、动态环境（复用 1.8.8 搭的 SDK 环境）
- `D:/android-sdk`：emulator + platform-tools + AVD `openchat`(API 30)
- frida-server 16.x（`/data/local/tmp/fs16`，配 Python frida 16.5.9 —— 17 版不匹配会 ProtocolError）
- 本 app 无加固、okhttp 日志拦截器未删 → **其实不需要 frida，logcat 直接能看全部请求头**：
  `adb logcat -d | grep okhttp.OkHttpClient`
- 坑：jadx 显示的混淆类名（`Sb.x`、`p247x3`）与运行时一致但 frida hook 参数签名要对；hook 内反射调用崩溃会杀进程 → hook 体最小化

## 四、交付物（本目录）

| 文件 | 说明 |
|---|---|
| `demo_server.py` | **全链路 2API**（端口 8903）：自动 token bootstrap + 缓存/过期刷新、`/v1/images/generations`(t2i)、`/v1/videos/generations`(t2v)、`/v1/tasks/<id>` 轮询、`/v1/moderation`、`/native/home`、`/health` |
| `demo.html` | 中文 demo 页 |
| `stress_test.py` | 基线/边界/Sign 矩阵/并发 4 场景 |
| `verify_e2e.js` | 一键 E2E：bootstrap→check-limit→t2v→t2i |
| `hook_aivg_b91.js` | frida hook（HeaderInterceptor + MessageDigest） |

### 冒烟结果（已验证 ✅）
- `/v1/videos/generations {"prompt":"a white cat jumping"}` → 200 MP4 URL（真实出片）
- `/v1/images/generations {"prompt":"a blue coffee cup"}` → jobId → 4s 轮询线程自动拉到 `succeeded` + PNG URL
- token 自动 bootstrap：`tokens_cached` 增长，过期自动重签

## 五、与 1.8.8 结论的差异修正
1. 1.8.8 报告认为 Sign = 证书 SHA1（Play `5f34…`）"校验通过"——实测那只对 home 类不校验端点成立；**生成链路的 Sign 是服务端白名单固定值** `68d6165b…`。
2. 1.8.8 遗留的 "user/info 额外校验需动态抓包" 缺口 → 已解决：Sign 白名单值 + 任意 Device-Id 即可签发 guest JWT。
3. staging 域名 `t2v-staging` 仍存活（远程配置下发），但生产 `t2v` 是 b91 的默认。

## 六、第二轮补测（i2v/i2i + 配额 + 视频参数，全部已验证 ✅）

### i2v / i2i multipart（全部打通）
| 端点 | multipart 字段 | 实测 |
|---|---|---|
| `/api/v4/video/i2v` | `image`(文件) + `code`(模板code) + `prompt`(文本) | ✅ 200 jobId → 轮询 `succeeded` MP4 |
| `/api/v4/image/i2i` | `images`(**复数**！文件) + `code`(模板code) | ✅ 200 jobId → 轮询 `succeeded` PNG |

（注意 i2v 用单数 `image`，i2i 用复数 `images` — 服务端不对称设计）

### 免费 guest 配额（`/api/v1/user/check-limit?type=`，参数名是 `type` 不是 ad_type）
| 类型 | remaining/total | 说明 |
|---|---|---|
| t2v_prompt | 10/10 | 每 device_id 10 次文生视频 |
| t2i_prompt | 3/3 | 每 device_id 3 次文生图 |
| i2i_edit | 1/1 | 每 device_id 1 次图生图 |
| i2v_prompt | -21 Premium required | **但实测服务端不强制** — i2v 成功出片，limit 只是客户端 UI 检查 |

**号池策略**：device_id 任意伪造（32位hex）→ 配额用尽换新 ID 即可无限生成。demo_server 已内置（device_pool.json 持久化 + 自动轮换 + /health 暴露池状态）。

### 视频参数（CreateVideoRequest 全字段，已验证）
- `prompt`(str) / `aspect_ratio`("auto"/"16:9"/"9:16"，非法值静默回退) / `ai_sound`("1"→aac 音轨 ✅ 实测 4.87s 视频 / 对照无声) / `isPremium`(0/1) / `used`(模板去重列表) / `deviceID` / `versionCode` / `ctry_target`
- **无 duration 参数** — 时长由上游模型决定（ft3.1.0 ≈ 5s），客户端无此控制项

### 速率限制
- 3/6/10 并发 t2i 提交全部 200，无 429/403，P99 ~1.3s
- 无发现硬限流；稳定运营建议：≤5 并发 + 号池轮换（每 device_id 用满即换）

## 七、剩余事项
- `moderation/check-input` 正确 multipart 形态待补测（Retrofit `@q` 注解为 MultipartBody.Part）
