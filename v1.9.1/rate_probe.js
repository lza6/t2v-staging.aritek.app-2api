// 速率限制压测 — 递增并发探测 (t2i 轻量端点, 每档间隔大, 探测即停)
const https = require('https');
const SIGN = '68d6165b72a7f2d8d17b0dc6fe9691abdf77c583';
function req(path, hdr, method, body) {
  return new Promise((res) => {
    const r = https.request({ hostname: 't2v.aritek.app', path, method: method || 'GET', headers: hdr, timeout: 30000 }, (x) => {
      let c = []; x.on('data', d => c.push(d)); x.on('end', () => res({ code: x.statusCode, body: Buffer.concat(c).toString() }));
    });
    r.on('error', e => res({ code: 'ERR', body: e.message }));
    r.on('timeout', () => { r.destroy(); res({ code: 'TIMEOUT', body: '' }); });
    if (body) r.write(body); r.end();
  });
}
async function bootstrap(dev) {
  const H = { 'Sign': SIGN, 'versionCode': '91', 'Ctry-Target': 'others', 'Device-Id': dev, 'pt': '', 'User-Agent': 'okhttp/4.9.3' };
  return JSON.parse((await req('/api/v1/user/info', H)).body).data.token;
}
(async () => {
  const DEV = 'poolstress' + Date.now().toString(16);
  const jwt = await bootstrap(DEV);
  const A = { 'Sign': SIGN, 'versionCode': '91', 'Ctry-Target': 'others', 'Device-Id': DEV, 'pt': '', 'User-Agent': 'okhttp/4.9.3', 'Authorization': 'Bearer ' + jwt, 'Content-Type': 'application/json' };

  for (const conc of [3, 6, 10]) {
    const t0 = Date.now();
    const results = await Promise.all(Array.from({ length: conc }, (_, i) =>
      req('/api/v4/image/t2i', A, 'POST', JSON.stringify({ prompt: [`stress test flower ${i}`] }))));
    const codes = results.map(r => r.code);
    const bodies = results.map(r => { try { return JSON.parse(r.body).code; } catch { return 'x'; } });
    console.log(`并发 ${conc}: http=[${codes}] api=[${bodies}] ${Date.now() - t0}ms`);
    if (codes.some(c => c === 429 || c === 403)) { console.log('→ 触发限流, 停止加压'); break; }
    await new Promise(r => setTimeout(r, 8000));
  }
  // 检查 limit 端点对速率的说法
  const cl = await req('/api/v1/user/check-limit?ad_type=t2i_prompt', A);
  console.log('check-limit t2i:', cl.body.slice(0, 250));
})().catch(e => console.log('FATAL', e));
