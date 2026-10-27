// i2v / i2i multipart 实测 — 需要一张真实测试图
const https = require('https');
const fs = require('fs');
const SIGN = '68d6165b72a7f2d8d17b0dc6fe9691abdf77c583';
const DEV = 'deadbeef00112233445566778899aabb';
const BOUNDARY = '----aivg2api' + Date.now();

function req(path, hdr, method, bodyBuf) {
  return new Promise((res) => {
    const r = https.request({ hostname: 't2v.aritek.app', path, method: method || 'GET', headers: hdr, timeout: 60000 }, (x) => {
      let c = []; x.on('data', d => c.push(d)); x.on('end', () => res({ code: x.statusCode, body: Buffer.concat(c).toString() }));
    });
    r.on('error', e => res({ code: 'ERR', body: e.message }));
    r.on('timeout', () => { r.destroy(); res({ code: 'TIMEOUT', body: '' }); });
    if (bodyBuf) r.write(bodyBuf); r.end();
  });
}

function multipart(fields, fileField, filename, fileBuf, mime) {
  const parts = [];
  for (const [k, v] of Object.entries(fields)) {
    parts.push(Buffer.from(`--${BOUNDARY}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`));
  }
  parts.push(Buffer.from(`--${BOUNDARY}\r\nContent-Disposition: form-data; name="${fileField}"; filename="${filename}"\r\nContent-Type: ${mime}\r\n\r\n`));
  parts.push(fileBuf);
  parts.push(Buffer.from(`\r\n--${BOUNDARY}--\r\n`));
  return Buffer.concat(parts);
}

(async () => {
  const H = { 'Sign': SIGN, 'versionCode': '91', 'Ctry-Target': 'others', 'Device-Id': DEV, 'pt': '', 'User-Agent': 'okhttp/4.9.3' };
  const jwt = JSON.parse((await req('/api/v1/user/info', H)).body).data.token;
  const A = { ...H, 'Authorization': 'Bearer ' + jwt };

  // 测试图: 从 home 目录取一个模板 preview (免费 CDN) 或生成 1x1 png
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');

  // 1) i2i: 模板 code 01KT1A2KZFS5MCZ8AZ4Z58FSDF = Ghibli Style (t2i_prompt 类) — 用 i2i_edit 模板更对
  //    home 里有 i2i_edit 模板, code 取 World Pup 01KVAJ4QSV7XF6GR9WGTS0KHBX
  const mp1 = multipart({ code: '01KVAJ4QSV7XF6GR9WGTS0KHBX' }, 'image', 'test.png', png, 'image/png');
  const r1 = await req('/api/v4/image/i2i', { ...A, 'Content-Type': 'multipart/form-data; boundary=' + BOUNDARY }, 'POST', mp1);
  console.log('1) i2i 1x1px [' + r1.code + ']:', r1.body.slice(0, 250));

  // 2) i2v: 用 home 的 i2v 模板 code (从 trendings 拿一个)
  const home = JSON.parse((await req('/api/v3/t2v/home?v=3', H)).body);
  const t2vT = home.data.videos.t2v.trendings[0].items[0].code;
  const mp2 = multipart({ code: t2vT }, 'image', 'test.png', png, 'image/png');
  const r2 = await req('/api/v4/video/i2v', { ...A, 'Content-Type': 'multipart/form-data; boundary=' + BOUNDARY }, 'POST', mp2);
  console.log('2) i2v template=' + t2vT + ' [' + r2.code + ']:', r2.body.slice(0, 250));
})().catch(e => console.log('FATAL', e));
