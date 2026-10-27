# AI Video Generator 1.8.8 逆向报告

APK: `ai.video.generator.text.video` (versionCode 88 / versionName 1.8.8)
出品: aritek (条款 https://sites.google.com/view/aritek-terms)，非 Flutter，纯原生 Kotlin + Retrofit + OkHttp
分发渠道: Telegram 魔改版 (t.me/pgkj666)，含 `ApkSignatureKillerEx`，签名 = AOSP testkey
指纹 SHA1: `61ed377e85d386a8dfee6b864bd85b0bfaa5af81` → 即请求头 `Sign`

## 关键结论

1. **无加密层** — 与 OpenChat 1.3.4 的 AES 协议不同，本 app 全部为明文 JSON + 自定义请求头。逆向成本极低。
2. **可本地接管** — Retrofit base url 从 SharedPreferences `api_url` 读取，默认 `https://t2v-staging.aritek.app/`，可被重定向到本地 mock。
3. **鉴权弱** — `Sign` 是 APK 签名证书的 SHA1（静态常量），`Authorization: Bearer <user_token>` 来自服务端登录，`Device-Id` 客户端自生成。无 Play Integrity。

## ⭐ 上游真实验证结论（2025 实测）

**正确 Sign = `5f349d58ed069b1810d23b71c67293818784b57b`**
（= Google Play 官方证书 SHA1。原版证书 Base64 硬编码于 `IceAce/Frozen.java` 的 `killPM()` 调用中 — ApkSignatureKillerEx 用它在运行时伪装签名。`assets/ExData` 是另一份同证书副本）

注意：本 APK 的 repackage 证书是 AOSP testkey（SHA1 61ed377e…），app 内 d.j() 用 PM 拿到的是被 killer 伪装后的 Play 证书，所以服务端 Sign 校验的是 Play 证书指纹。

### 实测结果（低频，~15 次请求）

| 端点 | 结果 |
|---|---|
| GET `api/v2/t2v/home?v=1` | ✅ **200** 完整 JSON（trendings/prompt 模板目录） |
| GET `api/v1/user/check-limit?type=video`（带假 Bearer） | ✅ 签名校验通过，卡在 "Invalid or expired token" — 服务端会验 JWT |
| POST `api/v3/video/t2v`（带假 Bearer） | ✅ 路由存在，同样卡 token |
| GET `api/v1/user/info` | ❌ 401 "Invalid signature" — 此端点有**额外校验**（可能要求 JWT 为空时特殊签名，或 Sign 之外还有动态签名，需动态抓包确认） |
| 错误 Sign | 401 "Invalid signature" |
| 缺 Device-Id/Ctry-Target | 400 明确报缺失 |

**结论：staging 端点存活，协议 100% 复现可行；唯一缺口是合法 user_token（JWT）的 bootstrap。**
token 是 JWT（代码里按 `.` 分隔解析 payload.exp）。获取途径二选一：
1. 动态抓包/模拟器运行 app 抓真实 `user/info` 请求（看它的完整头差异）
2. 用 Frida hook `p233w/f.java` 拿返回 token

JWT payload 含 `exp`，服务端验证过期 — 不是本地可伪造的空壳。

## 端点清单（Retrofit 接口 e/b.java）

Base: `https://t2v-staging.aritek.app/`（sp key `api_url` 可覆盖）

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/v2/t2v/home?v={int}` | 首页模板/素材目录 (Home) |
| GET | `api/v1/user/info` | 用户信息 (UserInfo) |
| GET | `api/v1/user/check-limit?{type}` | 次数/配额检查 (CheckLimit) |
| GET | `api/v1/redeem/check` (header Redeem-Code) | 兑换码校验 |
| POST | `/api/v3/video/t2v` | 文生视频，body={prompt,...} → GenVideoResponse{code,message,data{url,jobId}} |
| POST | `/api/v3/video/i2v` | 图生视频 (multipart) |
| POST | `/api/v3/image/t2i` | 文生图，body={prompt:[...], code} |
| POST | `/api/v3/image/i2i` | 图生图 (multipart) |
| POST | `/api/v1/generate/status` | 任务状态轮询 |
| POST | `video` | 视频创建 (VideoCreateResponse) |
| POST | `/api/v1/moderation/check-input` | NSFW 输入检测 |
| POST | `/api/v1/moderation/check-output` | NSFW 输出检测 |

Verify API（独立）: `https://android-api-verify.aritek.app`（收据/完整性校验）

## 请求头（HeaderInterceptor）

```
Sign: 61ed377e85d386a8dfee6b864bd85b0bfaa5af81   (固定常量)
pt: <sp key pt_>                                  (付费/渠道标记)
Ctry-Target: others | <sp ctry_target>
versionCode: 88
Authorization: Bearer <user_token>
Device-Id: <device_id>
Redeem-Code: <redeem_code>   (可选)
```

## t2v 请求体 (CreateVideoRequest)

```json
{
  "prompt": "...",
  "versionCode": 88,
  "deviceID": "...",
  "isPremium": 0,
  "ctry_target": "others",
  "used": [],
  "aspect_ratio": "...",
  "ai_sound": 0
}
```

## 图片相关

- 图片生成直接走 `https://image.pollinations.ai/prompt/...`（免费通道，无鉴权）
- 官方开发者: TechInforTainment (techinfortainment.com)

## 代码位置

- jadx 全量源码: `D:/aivg188/jadx-out/`
- 关键文件: `p039e/b.java`(端点), `p039e/a.java`(base url), `apiservice/HeaderInterceptor.java`(请求头), `com/bumptech/glide/d.java:331`(Sign 算法), `model/CreateVideoRequest.java`

## 压测边界

t2v-staging.aritek.app 为第三方生产服务器 — 只允许低频功能验证（≤几次请求），禁止高频压测。压测应对本地 demo 服务器进行。


## 动态分析记录（模拟器会话 2026-10-27）

环境: openchat AVD (android-13 x86_64) + frida 17.24.3 (fs17) + frida-java-bridge bundle

成果:
- Frida Java bridge 打通（frida 17 需 npm frida-java-bridge + frida-compile 打包）
- HeaderInterceptor hook 成功注册（HOOKED v5）
- 发现 okhttp/okio 已混淆 (Pb.*)，response body = Pb.N.f6451g.string()

阻塞点:
- AIVG 内置 libpglarmor.so（腾讯 PGL 加固）在 frida 注入后 SSL 握手 SIGSEGV (conscrypt OpenSSLRSAPublicKey) → 进程死
- attach 模式无法存活到 bootstrap 请求完成
- AVD 快照反复回滚出垃圾 app 干扰 UI，需冷启动后立即操作

未解: user/info 端点 "Invalid signature"（401 code -2）— Sign(Play 证书 SHA1) 在 check-limit/t2v 均通过，
唯独 user/info 拒绝。推测该端点有额外校验（可能校验 device_id HMAC 或无 Authorization 时的特殊签名），
必须动态抓包对比 app 真实请求头。下一步: spawn 模式 + Java.enumerateLoadedClasses 轮询等 HeaderInterceptor 加载后再 hook，
或用 Objection patch APK 去除 PGL 加固。

结论: 2api 对接可先绕开 user/info——若能从一台真机/模拟器正常运行的 app 里导出一次 user_token（sp 里的 JWT），
即可在有效期内用本报告的协议直接调 t2v（Sign 正确已验证）。JWT 过期后再导一次。


## 十一、Patch v2 与 MITM 会话复盘（2026-10-27 第二轮，10h+ 实战）

### 修复清单
1. **v2 patch 关键修复**：原版 manifest 根本没有 `android:networkSecurityConfig` 引用！只改 NSC 文件没用。v2 在 `<application>` 加上 `android:networkSecurityConfig="@xml/network_security_config"` + 保留 debuggable。产物 `patched/aivg-patched2-aligned-debugSigned.apk`
2. **MITM 正确姿势**（全套打通验证）：
   - 模拟器启动加 `-http-proxy 127.0.0.1:8080`（emulator 层强制，比 guest iptables/DNAT/reverse 可靠——iptables REDIRECT/DNAT 在 AVD NAT 环境下命中却到不了 host）
   - mitmdump `--listen-port 8080 --set connection_strategy=lazy --set ssl_insecure=true -w flows.bin`
   - CA 安装：`subject_hash_old` 命名 `c8750f0d.0`，tmpfs mount `/system/etc/security/cacerts` 后 cp；**adb push 必须 `MSYS_NO_PATHCONV=1`**（Git Bash 路径转换毁 /data 路径）
   - **CA 生效需要 framework 级重启**（`adb shell stop; start` 或 reboot），仅 force-stop app 不够
   - 认证链路验证成功：mitm 日志出现 `Client TLS handshake failed ... for t2v-staging.aritek.app` = 网络路径全通，只差信任

### 卡住的最后一环（如实记录）
- 原版 APK 在模拟器能跑到 MainActivity（Android 13 AVD，`remakeface` API33）
- patched v2 修复 Firebase 崩溃后也能到 MainActivity（之前"静默退出"真因 = `FirebaseCrashlytics component is not present` NPE，`pm uninstall` 全新安装可解）
- **最后一卡点：app 不信任 mitmproxy CA**（Client TLS handshake failed: certificate unknown）。system cacerts 已放 CA + framework 重启过仍失败。
  待验证假设：① AVD `google_apis` 镜像的 CA 加载路径特殊 ② NSC `src="user"` 与 system 区 CA 语义不符，需要真正装进 KeyChain 用户区（headless 可试 `android.credentials.INSTALL` intent + UI 自动化，走到一半被模拟器崩溃打断）
- 抓包窗口确认存在：点 Generate 会触发 `user/info`→`check-limit`→`t2v` 全链路（早前在代理生效窗口看到 aritek TLS 握手到达）

### 复现最快路径（下次直接执行）
1. 冷启动：`emulator -avd remakeface -http-proxy 127.0.0.1:8080 -no-snapshot ...`
2. host: `mitmdump --listen-port 8080 --set connection_strategy=lazy --set ssl_insecure=true -w flows.bin`
3. guest: MSYS_NO_PATHCONV=1 adb push CA → tmpfs cacerts → `stop; start`
4. 装 `patched2` APK → 启动 → **UI 点 Generate**（坐标用 uiautomator dump 取 "Generate" 按钮）
5. 若 CA 仍不被信 → 走 CertInstaller UI 装用户证书（intent 已验证能拉起 UI）
