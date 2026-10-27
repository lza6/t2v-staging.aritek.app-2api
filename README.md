# AI Video Generator 1.8.8 → 2API 逆向报告

> 仓库: https://github.com/lza6/t2v-staging.aritek.app-2api
> 目标 APK: `AI Video Generator_1.8.8.apk`（包名 `ai.video.generator.text.video`，versionCode 88）
> 出品: aritek（条款 sites.google.com/view/aritek-terms）
> 分发: Telegram 魔改版（t.me/pgkj666），内置 ApkSignatureKillerEx，重打包证书为 AOSP testkey
> 分析日期: 2026-10-26 ~ 10-27

---

## 一、技术栈

原生 Kotlin + Retrofit + OkHttp + Gson。**无 Flutter、无壳、无传输加密** — 协议为明文 JSON + 自定义请求头。逆向成本极低。

`libpglarmor.so` 等是穿山甲广告 SDK 组件，`libsigner.so` 是 Adjust 反作弊，均与业务 API 无关。

## 二、端点清单（jadx 源码 `p039e/b.java`）

**Base URL**: `https://t2v-staging.aritek.app/`
（Retrofit 从 SharedPreferences `api_url` 读取，默认值即此 — 可被本地接管做 MITM/调试）

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/v2/t2v/home?v={int}` | 首页模板/trending 目录（无需登录） |
| GET | `api/v1/user/info` | bootstrap：返回 user_token (JWT) |
| GET | `api/v1/user/check-limit?type={type}` | 配额检查 |
| GET | `api/v1/redeem/check`（header Redeem-Code） | 兑换码 |
| POST | `/api/v3/video/t2v` | 文生视频 |
| POST | `/api/v3/video/i2v` | 图生视频 (multipart) |
| POST | `/api/v3/image/t2i` | 文生图 |
| POST | `/api/v3/image/i2i` | 图生图 (multipart) |
| POST | `/api/v1/generate/status` | 任务状态轮询 |
| POST | `video` | 视频创建记录 |
| POST | `/api/v1/moderation/check-input` | NSFW 输入检查 |
| POST | `/api/v1/moderation/check-output` | NSFW 输出检查 |

独立 IAP verify API: `https://android-api-verify.aritek.app`（POST，订阅收据验证，与业务无关）

## 三、请求头（`apiservice/HeaderInterceptor.java`）

```
Sign: <SHA1(APK 签名证书 DER)，小写 hex>
pt: <sp pt_>
Ctry-Target: others | <国家码>
versionCode: 88
Authorization: Bearer <user_token JWT>
Device-Id: <Settings.Secure.ANDROID_ID>
Redeem-Code: <可选>
User-Agent: okhttp/4.x
```

**⭐ Sign 正确值（上游实测验证通过）**:

```
5f349d58ed069b1810d23b71c67293818784b57b
```

= Google Play 官方证书 SHA1。原版证书 Base64 硬编码于 `IceAce/Frozen.java` 的 `killPM()` 调用中（ApkSignatureKillerEx 用它运行时伪装签名），`assets/ExData` 为同证书副本。两份证书文件已存本仓库 `certs/`。

## 四、t2v 请求体（`model/CreateVideoRequest.java`）

```json
{
  "prompt": "...",
  "versionCode": 88,
  "deviceID": "<android_id>",
  "isPremium": 0,
  "ctry_target": "others",
  "used": [],
  "aspect_ratio": "9:16",
  "ai_sound": 0
}
```

响应: `{code:0, message:"ok", data:{url:"", jobId:"<hex>"}}` → 轮询 `/api/v1/generate/status` `{jobId}` → `{status: processing|done, url}`

## 五、上游实测结论（低频 ~20 次）

| 端点 | 结果 |
|---|---|
| `GET api/v2/t2v/home?v=1` | ✅ **200** 完整模板目录 |
| `GET api/v1/user/check-limit`（假 Bearer） | ✅ 签名通过，卡 "Invalid or expired token" |
| `POST /api/v3/video/t2v`（假 Bearer） | ✅ 路由存在，卡 token |
| `GET api/v1/user/info`（各种头组合） | ❌ 401 "Invalid signature" — 此端点有额外校验 |

错误路径行为：缺 Device-Id/Ctry-Target → 400 明确提示；错 Sign → 401 Invalid signature。

**唯一缺口 = 合法 user_token（JWT，payload 含 exp）。** 获取途径：
1. 任意真机/模拟器正常跑 app 一次，从 `/data/data/ai.video.generator.text.video/shared_prefs/` 导出 `user_token`
2. 或动态抓包 `user/info` 响应（patched APK 已提供，见下）

## 六、Patch APK（`patched/` 目录）

用 apktool 2.9.3 做了两处 patch 后重打包（uber-apk-signer debug 签名）：

1. `res/xml/network_security_config.xml` → 信任用户 CA（mitmproxy 抓 HTTPS）
2. `AndroidManifest.xml` → `android:debuggable="true"`

文件: `patched/aivg-patched-aligned-debugSigned.apk`

抓包步骤（模拟器需 root）：
```powershell
# 1. 推 mitmproxy CA 到系统信任区（tmpfs 覆盖法，重启后需重做）
adb root; adb push <ca>.0 /data/local/tmp/
adb shell "mkdir -p /data/local/tmp/cacerts; cp /system/etc/security/cacerts/* /data/local/tmp/cacerts/; cp /data/local/tmp/<ca>.0 /data/local/tmp/cacerts/; chmod 644 /data/local/tmp/cacerts/*"
adb shell "mount -t tmpfs tmpfs /system/etc/security/cacerts && cp /data/local/tmp/cacerts/* /system/etc/security/cacerts/"

# 2. 全局代理指向主机 mitmproxy
adb shell "settings put global http_proxy 10.0.2.2:8080"

# 3. 主机跑 mitmproxy 后安装 patched APK 并启动
mitmdump -p 8080 -w flows.bin
adb install patched/aivg-patched-aligned-debugSigned.apk
```

⚠️ 已知问题：app 的 splash 广告 SDK 会拉起一堆 cross-promo 垃圾 app（黑马加速器 VPN、RemakeFace 等），需要 `pm uninstall --user 0` 清掉；app 在无网络广告响应时可能静默退出。token 抓取需在 splash→主页 3 秒窗口内完成。

## 七、demo 服务器（`demo_server.py`）

本地协议复刻服务器（端口 8912），端点、头校验、任务队列与上游一致：
- 完整实现 home / user-info / check-limit / redeem / t2v / t2i / status / moderation 端点
- Sign 头校验（错误 Sign 返回 401）
- t2v 异步任务（3 秒后 done + 假 URL）+ `/benchmark` 压测统计

本地压测（`benchmark.py`，200 请求 × 5 场景）: 230~346 rps，0 错误，全链路 create→poll→done 通过。

demo 网页: `demo.html`（输入 prompt → 创建 → 轮询 → 出结果）。

## 八、代码位置索引（jadx 全量源码）

| 内容 | 文件 |
|---|---|
| 端点定义 | `p039e/b.java` |
| Base URL / client 工厂 | `p039e/a.java` |
| 请求头拦截器 | `ai/video/generator/text/video/apiservice/HeaderInterceptor.java` |
| Sign 算法 | `com/bumptech/glide/d.java:331`（SHA1(签名DER)） |
| 原版证书（killer 内置） | `IceAce/Frozen.java:284` killPM() + `assets/ExData` |
| t2v 请求体 | `model/CreateVideoRequest.java` |
| token 刷新 | `p233w/f.java`（JWT `.` 分段解析 exp） |
| device_id | `SoliText2VideoApplication.java:729`（ANDROID_ID） |

## 九、new-api 对接路线

token 到手后，参照本仓库 `demo_server.py` 的协议实现即可在 new-api 挂渠道：
上游转发时固定头 `Sign`/`versionCode`/`Ctry-Target`/`Device-Id`，`Authorization: Bearer <token>`，
`POST /api/v3/video/t2v` → 轮询 `/api/v1/generate/status` → 返回 video url。

## 十、合规边界

上游为第三方生产服务器 — 只做低频功能验证，不做压测。所有压测针对本地 demo 服务器。
