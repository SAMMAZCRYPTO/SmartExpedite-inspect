/* ============================================================================
   ep_xlsx_read.js — read a .xlsx in the browser with no library.
   An .xlsx is a zip of XML. The zip's central directory says where each part
   is; parts are stored or deflated, and the browser's own DecompressionStream
   ('deflate-raw') inflates them. We read the shared strings, the first sheet's
   cells (inline strings, shared strings, numbers, booleans) and the workbook's
   defined names (the hidden SmartExpedit tag rides on one).
   Old binary .xls is NOT read — the portal hands out .xlsx to fill instead.
   ============================================================================ */

async function epXlsxInflate(bytes) {
  const ds = new DecompressionStream('deflate-raw');
  const out = new Response(new Blob([bytes]).stream().pipeThrough(ds));
  return new Uint8Array(await out.arrayBuffer());
}

async function epXlsxUnzip(buf) {
  const b = new Uint8Array(buf), dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  let eocd = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('Not a .xlsx file (no zip directory). Save it as .xlsx and upload again.');
  const n = dv.getUint16(eocd + 10, true);
  let p = dv.getUint32(eocd + 16, true);
  const dec = new TextDecoder();
  const files = {};
  for (let k = 0; k < n; k++) {
    if (dv.getUint32(p, true) !== 0x02014b50) break;
    const method = dv.getUint16(p + 10, true), csize = dv.getUint32(p + 20, true);
    const nlen = dv.getUint16(p + 28, true), elen = dv.getUint16(p + 30, true), clen = dv.getUint16(p + 32, true);
    const off = dv.getUint32(p + 42, true);
    const name = dec.decode(b.subarray(p + 46, p + 46 + nlen));
    const lnlen = dv.getUint16(off + 26, true), lelen = dv.getUint16(off + 28, true);
    const data = b.subarray(off + 30 + lnlen + lelen, off + 30 + lnlen + lelen + csize);
    files[name] = { method: method, data: data };
    p += 46 + nlen + elen + clen;
  }
  const text = async function (name) {
    const f = files[name]; if (!f) return '';
    const raw = f.method === 0 ? f.data : await epXlsxInflate(f.data);
    return dec.decode(raw);
  };
  return { names: Object.keys(files), text: text };
}

function epXlsxUnesc(s) {
  return String(s).replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'").replace(/&#(\d+);/g, function (m, d) { return String.fromCharCode(+d); })
    .replace(/&amp;/g, '&');
}
function epXlsxColIdx(ref) {
  const m = ref.match(/^([A-Z]+)/); let n = 0;
  for (const ch of m[1]) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}
/* Excel serial date -> yyyy-mm-dd */
function epXlsxDate(v) {
  if (typeof v !== 'number' || v < 20000 || v > 80000) return null;
  const d = new Date(Math.round((v - 25569) * 86400000));
  return d.toISOString().slice(0, 10);
}

async function epXlsxRead(buf) {
  const z = await epXlsxUnzip(buf);
  const sst = [];
  const ss = await z.text('xl/sharedStrings.xml');
  (ss.match(/<si>[\s\S]*?<\/si>/g) || []).forEach(function (si) {
    sst.push(epXlsxUnesc((si.match(/<t[^>]*>([\s\S]*?)<\/t>/g) || []).map(function (t) { return t.replace(/<[^>]+>/g, ''); }).join('')));
  });
  const wb = await z.text('xl/workbook.xml');
  const names = {};
  (wb.match(/<definedName[^>]*>[\s\S]*?<\/definedName>/g) || []).forEach(function (d) {
    const nm = (d.match(/name="([^"]+)"/) || [])[1];
    names[nm] = epXlsxUnesc(d.replace(/<[^>]+>/g, ''));
  });
  const sheetName = z.names.find(function (n) { return /^xl\/worksheets\/sheet\d+\.xml$/.test(n); }) || 'xl/worksheets/sheet1.xml';
  const xml = await z.text(sheetName);
  const rows = [];
  (xml.match(/<row[\s\S]*?<\/row>/g) || []).forEach(function (rx) {
    const r = +((rx.match(/<row[^>]*\br="(\d+)"/) || [])[1] || rows.length + 1);
    const row = [];
    (rx.match(/<c\b[^>]*?(?:\/>|>[\s\S]*?<\/c>)/g) || []).forEach(function (cx) {
      const ref = (cx.match(/\br="([A-Z]+\d+)"/) || [])[1]; if (!ref) return;
      const t = (cx.match(/\bt="([^"]+)"/) || [])[1] || '';
      let v = null;
      if (t === 'inlineStr') v = epXlsxUnesc((cx.match(/<t[^>]*>([\s\S]*?)<\/t>/) || [])[1] || '');
      else {
        const raw = (cx.match(/<v>([\s\S]*?)<\/v>/) || [])[1];
        if (raw == null) v = null;
        else if (t === 's') v = sst[+raw];
        else if (t === 'b') v = raw === '1';
        else if (t === 'str') v = epXlsxUnesc(raw);
        else v = isNaN(+raw) ? epXlsxUnesc(raw) : +raw;
      }
      row[epXlsxColIdx(ref)] = v;
    });
    rows[r - 1] = row;
  });
  return { rows: rows, names: names };
}
