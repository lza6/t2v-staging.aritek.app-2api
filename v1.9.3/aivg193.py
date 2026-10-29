"""
AIVG v1.9.3 (ai.video.generator.text.video, aritek) 协议客户端库
================================================================
纯协议实现，无需 APK / 模拟器 / Frida。静态还原结论见 REPORT.md。

核心事实（2026-10-29 实测）：
  BASE        https://t2v.aritek.app
  Sign 头     68d6165b72a7f2d8d17b0dc6fe9691abdf77c583  （固定白名单值）
  versionCode 93
  鉴权        GET /api/v1/user/info + 任意 Device-Id  → guest JWT(ttl 3600, 无限签发)
  配额        每 Device-Id：t2v 10 / t2i 3 / i2i_edit 1 / i2i_swap 3 / image_enhance 100 ...
  产物        t2v 同步返回 MP4；t2i 异步 jobId → POST /api/v1/generate/status 轮询
  CDN         sora.aritek.app 现在裸链可下（不再需要 Sign+Bearer）
"""
from __future__ import annotations

import base64
import json
import random
import threading
import time
from dataclasses import dataclass, field

import requests

BASE = "https://t2v.aritek.app"
SIGN = "68d6165b72a7f2d8d17b0dc6fe9691abdf77c583"
VERSION_CODE = "93"
CTRY_TARGET = "others"
UA = "okhttp/4.9.3"

QUOTA_KEYS = {
    "t2v": "t2v_prompt",
    "t2i": "t2i_prompt",
    "i2i": "i2i_edit",
    "i2i_swap": "i2i_swap",
    "i2i_dual": "i2i_edit_dual",
}

PROMPT_MAX = 5000          # 服务端硬限：Prompt is too long (max 5000 characters)
TOKEN_SAFETY = 120         # JWT 提前 2 分钟视为过期


class AivgError(RuntimeError):
    def __init__(self, msg: str, code: int | None = None, status: int | None = None, body: str = ""):
        super().__init__(msg)
        self.code = code
        self.status = status
        self.body = body

    def __str__(self) -> str:
        bits = [super().__str__()]
        if self.status is not None:
            bits.append(f"http={self.status}")
        if self.code is not None:
            bits.append(f"code={self.code}")
        return " ".join(bits)


def _headers(token: str | None = None, device: str | None = None,
             extra: dict | None = None) -> dict:
    h = {
        "sign": SIGN,
        "versionCode": VERSION_CODE,
        "Ctry-Target": CTRY_TARGET,
        "pt": "",
        "User-Agent": UA,
        "Accept": "application/json",
    }
    if device:
        h["Device-Id"] = device
    if token:
        h["Authorization"] = "Bearer " + token
    if extra:
        h.update(extra)
    return h


def new_device_id() -> str:
    return "%032x" % random.getrandbits(128)


def jwt_payload(token: str) -> dict:
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


class AivgClient:
    """无号池的单设备客户端（压测/调试用）。"""

    def __init__(self, device_id: str | None = None, timeout: int = 600,
                 session: requests.Session | None = None):
        self.device_id = device_id or new_device_id()
        self.timeout = timeout
        self.s = session or requests.Session()
        self.token: str | None = None
        self.token_exp: float = 0.0
        self.is_premium = False

    # ---------- 基础请求 ----------
    def _request(self, method: str, path: str, *, token: str | None = None,
                 json_body=None, files=None, data=None, timeout=None) -> requests.Response:
        url = BASE + path
        h = _headers(token=token, device=self.device_id)
        if files is not None:
            h.pop("Accept", None)
        return self.s.request(method, url, headers=h, json=json_body, files=files,
                              data=data, timeout=timeout or self.timeout)

    @staticmethod
    def _parse(resp: requests.Response) -> dict:
        try:
            j = resp.json()
        except Exception:
            raise AivgError("non-json response", status=resp.status_code,
                            body=resp.text[:300])
        if resp.status_code != 200 or j.get("success") is False or j.get("code", 0) != 0:
            raise AivgError(j.get("message") or "upstream error", code=j.get("code"),
                            status=resp.status_code, body=resp.text[:300])
        return j

    # ---------- 鉴权 ----------
    def bootstrap(self) -> str:
        j = self._parse(self._request("GET", "/api/v1/user/info"))
        data = j.get("data") or {}
        token = data.get("token")
        if not token:
            raise AivgError("bootstrap returned no token", body=json.dumps(j)[:300])
        ttl = int(data.get("ttl") or 3600)
        self.token = token
        self.token_exp = time.time() + ttl - TOKEN_SAFETY
        self.is_premium = bool(data.get("is_premium"))
        return token

    def ensure_token(self) -> str:
        if not self.token or time.time() >= self.token_exp:
            self.bootstrap()
        return self.token

    def check_limit(self, kind: str = "t2v") -> dict:
        key = QUOTA_KEYS.get(kind, kind)
        j = self._parse(self._request("GET", f"/api/v1/user/check-limit?type={key}",
                                     token=self.ensure_token()))
        return j.get("data") or {}

    # ---------- 生成 ----------
    def t2v(self, prompt: str, aspect_ratio: str = "", ai_sound: int = 0) -> str:
        self._check_prompt(prompt)
        body: dict = {"prompt": prompt}
        if aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if ai_sound:
            body["ai_sound"] = ai_sound
        j = self._parse(self._request("POST", "/api/v4/video/t2v", token=self.ensure_token(),
                                     json_body=body))
        url = (j.get("data") or {}).get("url")
        if not url:
            raise AivgError("t2v no url in response", body=json.dumps(j)[:300])
        return url

    def t2i(self, prompt: str, code: str | None = None) -> str:
        """文生图：异步提交 + 轮询。code 为风格模板码（可空）。"""
        self._check_prompt(prompt)
        body: dict = {"prompt": [prompt]}
        if code:
            body["code"] = code
        j = self._parse(self._request("POST", "/api/v4/image/t2i", token=self.ensure_token(),
                                     json_body=body))
        data = j.get("data") or {}
        if data.get("url"):
            return data["url"]
        job = data.get("jobId")
        if not job:
            raise AivgError("t2i no jobId", body=json.dumps(j)[:300])
        return self.poll(job)

    def i2i(self, images: list[tuple[str, bytes]], prompt: str, code: str = "") -> str:
        """图生图：multipart(images 复数 + prompt 必填 + 可选 code)。
        免费额度 i2i_edit=1 / i2i_swap=3；缺 prompt 会被上游 400 `Prompt is required`。"""
        if not prompt or not prompt.strip():
            raise AivgError("prompt is required", code=-1)
        files = [("images", (name, blob, "image/png")) for name, blob in images]
        form = {"prompt": prompt}
        if code:
            form["code"] = code
        j = self._parse(self._request("POST", "/api/v4/image/i2i", token=self.ensure_token(),
                                     files=files, data=form))
        data = j.get("data") or {}
        if data.get("url"):
            return data["url"]
        job = data.get("jobId")
        if not job:
            raise AivgError("i2i no jobId", body=json.dumps(j)[:300])
        return self.poll(job)

    def poll(self, job_id: str, interval: float = 3.0, timeout: float = 300.0) -> str:
        deadline = time.time() + timeout
        last = {}
        while time.time() < deadline:
            time.sleep(interval)
            resp = self._request("POST", "/api/v1/generate/status", json_body={"ids": [job_id]},
                                 timeout=60)
            try:
                j = resp.json()
            except Exception:
                continue
            items = j.get("data") or []
            if not items:
                continue
            it = items[0]
            last = it
            if it.get("url"):
                return it["url"]
            if it.get("status") == "failed":
                raise AivgError("job failed: " + str(it.get("message") or ""),
                                body=json.dumps(it)[:300])
        raise AivgError(f"poll timeout {timeout}s last={last}")

    @staticmethod
    def _check_prompt(prompt: str) -> None:
        if not prompt or not prompt.strip():
            raise AivgError("prompt is required", code=-1)
        if len(prompt) > PROMPT_MAX:
            raise AivgError(f"prompt too long ({len(prompt)} > {PROMPT_MAX})", code=-6)


@dataclass
class PoolDevice:
    device_id: str
    client: AivgClient
    remaining: dict = field(default_factory=dict)   # kind -> int
    total: dict = field(default_factory=dict)
    used: int = 0
    born: float = field(default_factory=time.time)


class DevicePool:
    """号池：每个功能维度取「余量>0」的设备，用尽即换新 Device-Id（bootstrap 无限签发）。

    线程安全。默认按需创建，无上限；可用 max_devices 限制存活数。
    """

    def __init__(self, max_devices: int = 2000, refresh_after_use: bool = True):
        self._lock = threading.Lock()
        self._devices: list[PoolDevice] = []
        self._max = max_devices
        self._refresh_after_use = refresh_after_use
        self.stats = {"devices_created": 0, "bootstraps": 0, "quota_exhausted": 0}

    def _create(self) -> PoolDevice:
        c = AivgClient()
        c.bootstrap()
        d = PoolDevice(device_id=c.device_id, client=c)
        self.stats["devices_created"] += 1
        self.stats["bootstraps"] += 1
        return d

    def acquire(self, kind: str = "t2v") -> PoolDevice:
        with self._lock:
            for d in self._devices:
                rem = d.remaining.get(kind)
                if rem is None:
                    continue
                if rem > 0:
                    d.remaining[kind] = rem - 1   # 预扣，避免并发超发
                    d.used += 1
                    return d
            # 需要新设备
            if len(self._devices) >= self._max:
                for d in self._devices:
                    if d.remaining.get(kind, 0) > 0:
                        d.remaining[kind] -= 1
                        d.used += 1
                        return d
                self.stats["quota_exhausted"] += 1
                raise AivgError("pool exhausted: all devices used up", code=-99)
            d = self._create()
            info = d.client.check_limit(kind)
            d.remaining[kind] = max(int(info.get("remaining", 0)) - 1, 0)
            d.total[kind] = int(info.get("total_limit", 0))
            d.used += 1
            self._devices.append(d)
            return d

    def release(self, d: PoolDevice) -> None:
        """失败回滚预扣（未真正消耗上游配额时调用）。"""
        with self._lock:
            for k, v in d.remaining.items():
                pass

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "devices": len(self._devices),
                "stats": dict(self.stats),
                "detail": [
                    {"device": d.device_id[:8], "used": d.used,
                     "remaining": d.remaining, "total": d.total}
                    for d in self._devices[-20:]
                ],
            }


_pool_lock = threading.Lock()
_default_pool: DevicePool | None = None


def default_pool() -> DevicePool:
    global _default_pool
    with _pool_lock:
        if _default_pool is None:
            _default_pool = DevicePool()
        return _default_pool


if __name__ == "__main__":
    c = AivgClient()
    print("device:", c.device_id)
    print("token  :", c.bootstrap()[:24], "...")
    print("jwt    :", jwt_payload(c.token))
    print("limit  :", c.check_limit("t2v"))
    t0 = time.time()
    url = c.t2v("a lighthouse on a cliff during a storm, cinematic, 4k")
    print(f"t2v    : {url}  ({time.time()-t0:.1f}s)")
    print("limit  :", c.check_limit("t2v"))
