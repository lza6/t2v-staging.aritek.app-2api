// AIVG v1.9.1 b91 — 全链路验证: bootstrap + check-limit + moderation + t2v 提交
const https = require('https');
const SIGN = '68d6165b72a7f2d8d17b0dc6fe9691abdf77c583';
const DEV = 'deadbeef00112233445566778899aabb';

function req(path, hdr, method, body) {
  return new Promise((res) => {
    const r = https.request({ hostname: 't2v.aritek.app', path, method: method || 'GET', headers: hdr, timeout: 30000 }, (x) => {
      let d = ''; x.on('data', c => d += c); x.on('end', () => res({ code: x.statusCode, body: d }));
    });
    r.on('error', e => res({ code: 'ERR', body: e.message }));
    r.on('timeout', () => { r.destroy(); res({ code: 'TIMEOUT', body: '' }); });
    if (body) r.write(body); r.end();
  });
}

(async () => {
  const H = { 'Sign': SIGN, 'versionCode': '91', 'Ctry-Target': 'others', 'Device-Id': DEV, 'pt': '', 'User-Agent': 'okhttp/4.9.3' };
  // 1) fresh device bootstrap
  let r = JSON.parse((await req('/api/v1/user/info', H)).body);
  console.log('1) fresh device bootstrap:', r.code === 0 ? 'OK ttl=' + r.data.ttl : 'FAIL ' + JSON.stringify(r).slice(0, 150));
  const jwt = r.data.token;
  const A = { ...H, 'Authorization': 'Bearer ' + jwt, 'Content-Type': 'application/json; charset=UTF-8' };
  // 2) check-limit
  console.log('2) check-limit:', (await req('/api/v1/user/check-limit?ad_type=t2v_prompt', A)).body.slice(0, 250));
  // 3) moderation check-input (query param per @q)
  console.log('3) moderation:', (await req('/api/v1/moderation/check-input?text=beautiful%20sunset', A)).body.slice(0, 250));
  // 4) t2v submit
  const t2v = await req('/api/v4/video/t2v', A, 'POST', JSON.stringify({ prompt: 'a cute orange cat walking in a sunny garden', aspect_ratio: '9:16' }));
  console.log('4) t2v submit [' + t2v.code + ']:', t2v.body.slice(0, 300));
  // 5) t2i submit
  const t2i = await req('/api/v4/image/t2i', A, 'POST', JSON.stringify({ prompt: 'a red apple on a wooden table', aspect_ratio: '1:1' }));
  console.log('5) t2i submit [' + t2i.code + ']:', t2i.body.slice(0, 300));
})().catch(e => console.log('FATAL', e));
