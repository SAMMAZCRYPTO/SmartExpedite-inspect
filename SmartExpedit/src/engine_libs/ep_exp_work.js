/* ============================================================================
   SmartExpedit — Expediting workspace engine
   ----------------------------------------------------------------------------
   The expeditor's work on one order, as Mohamed Amin described it:

     LOAD      Mr. Huzaifa assigns by load — each expeditor's open POs.
     MR STUDY  the ITR and SDR read out of the MR (ep_mr_reader.js).
     LETTER    the introduction letter, generated from the order and sent on
               the portal; the vendor answers each point on the portal.
     REGISTER  the Vendor Data Register (SDR/VDR): one row per coded document.
               The SDRL code is the registration key. Both the expeditor and the
               vendor edit it; every change is marked (who, side, when, old, new);
               a deleted row stays, struck through, with its reason. It goes out
               and comes back as .xlsx with a hidden tag.
     SCHEDULE  the order's schedule (Z003): the minimum-requirement rows locked
               in, rows and columns added by either side, baseline frozen once
               accepted, forecasts moved with a reason; an itemized layout per PO
               line with weighted milestones; sub-orders with float; each issue
               becomes the next revision of Z003 in the register.

   Every function works on a record object in memory; the page saves it.
   ============================================================================ */

/* ------------------------------------------------------------------ UTILS */
function epXz(n) { return String(n).padStart(2, '0'); }
function epXToday() { const d = new Date(); return d.getFullYear() + '-' + epXz(d.getMonth() + 1) + '-' + epXz(d.getDate()); }
function epXAddDays(iso, days) {
  if (!iso || days == null) return '';
  const d = new Date(iso + 'T00:00:00'); if (isNaN(d)) return '';
  d.setDate(d.getDate() + days);
  return d.getFullYear() + '-' + epXz(d.getMonth() + 1) + '-' + epXz(d.getDate());
}
function epXDiff(a, b) {           /* b - a in days */
  if (!a || !b) return null;
  const x = new Date(a + 'T00:00:00'), y = new Date(b + 'T00:00:00');
  if (isNaN(x) || isNaN(y)) return null;
  return Math.round((y - x) / 86400000);
}
function epXId() { return 'r' + Math.random().toString(36).slice(2, 9); }
function epXNow() { return new Date().toISOString(); }

/* ------------------------------------------------------------------- LOAD
   The open-PO load each expeditor already carries. MODELLED: a fixed figure
   between 30 and 50 per person (his number: "this is how normally they
   handle work"), plus every order assigned to them here.                  */
const EP_EXP_LOAD_BASE = { Ashok:42, Arjun:37, Hesham:46, Ali:33, Soud:49, Ahmed:39, Youssef:31 };
function epExpLoadOf(name, list) {
  const base = EP_EXP_LOAD_BASE[name] || 40;
  const mine = (list || epExpLoad()).filter(function (r) { return r.assignedTo === name && !epExpIsClosed(r); }).length;
  return { base: base, mine: mine, total: base + mine };
}

/* --------------------------------------------------------------- CLIENT
   ADNOC orders use the Vendor Data Register layout (with the ADNOC document
   number); Aramco LTA orders use the Supplier Data Register layout.        */
function epExpClientKind(rec) {
  const c = String((rec && (rec.client || rec.head)) || '').toUpperCase();
  if (/ARAMCO/.test(c) || /^(7000|2790|2792)/.test(String(rec && rec.project))) return 'aramco';
  return 'adnoc';
}

/* --------------------------------------------------------------- MR STUDY */
function epExpMrKey(rec) { return String(rec.mrRef || '').replace(/\//g, '-'); }
function epExpMrExtract(rec) {
  if (rec.mrStudy && rec.mrStudy.extract) return rec.mrStudy.extract;
  const lib = (typeof window !== 'undefined' && window.EP_MR_EXTRACTS) || {};
  return lib[epExpMrKey(rec)] || null;
}
function epExpMrImage(rec, pn) {
  const x = epExpMrExtract(rec);
  if (x && x.images && x.images[pn]) return x.images[pn];
  return (rec.mrStudy && rec.mrStudy.images && rec.mrStudy.images[pn]) || '';
}

/* ================================================================ REGISTER */
const EP_REG_NPCC_STATUS = { A:'Accepted', B:'Commented as marked', C:'Not accepted', D:'Retained for information' };
const EP_REG_CO_STATUS = { 1:'Approved without comment', 2:'Approved with comments', 3:'Reviewed with comments', 4:'Information only', 5:'Rejected' };
const EP_REG_ROUTES = { smartexpedit:'In SmartExpedit', vdmsSent:'Sent to VDMS', vdmsDirect:'Submitted in VDMS' };

/* the fixed columns — the format that keeps the data constant across orders */
function epRegCols(rec) {
  const adnoc = epExpClientKind(rec) === 'adnoc';
  const c = [
    { key:'sl',       label:'Sl No.',            w:52,  ro:true },
    { key:'npcc',     label:'NPCC Document No.', w:190, ro:true },
  ];
  if (adnoc) c.push({ key:'adnoc', label:'ADNOC Document No.', w:150 });
  c.push(
    { key:'vendorNo', label:'Vendor Document No.', w:140 },
    { key:'rev',      label:'Rev.',              w:50 },
    { key:'cls',      label:'Document Class',    w:80, ro:true },
    { key:'title',    label:'Title',             w:260 },
    { key:'planned',  label:'Planned Date',      w:110, date:true },
    { key:'actual',   label:'Actual Date',       w:110, date:true },
    { key:'npccSt',   label:'NPCC Status',       w:90, npccOnly:true },
    { key:'coSt',     label:'Company Status',    w:96, npccOnly:true },
    { key:'remarks',  label:'Remarks',           w:200 },
    { key:'route',    label:'File',              w:110, ro:true });
  return c;
}

function epRegMrShort(rec) { const p = String(rec.mrRef || '').split(/[-\/]/); return p[p.length - 1] || ''; }
function epRegNpccNo(rec, code, serial) {
  return rec.project + '-' + epRegMrShort(rec) + (rec.letter || '') + '-' + code + '-' + epXz(serial).padStart(3, '0');
}
/* planned date from the SDR's "date required": 2W = issue + 14 days; FINAL and
   WM (with material) = the order's last delivery lot; blank stays blank */
function epRegPlannedFrom(rec, dateReq) {
  const base = rec.issuedOn || epXToday();
  const days = (typeof epMrSdrDays === 'function') ? epMrSdrDays(dateReq) : null;
  if (days != null) return epXAddDays(base, days);
  if (/FINAL|WM/i.test(dateReq || '')) {
    const lots = (rec.lots || []).filter(function (l) { return l.date; }).map(function (l) { return l.date; }).sort();
    return lots.length ? lots[lots.length - 1] : '';
  }
  return '';
}
function epRegInit(rec) {
  if (!rec.reg) rec.reg = { rows:[], log:[], extra:[], hidden:{ npcc:[], vendor:[] }, ver:0, createdOn:'', createdBy:'' };
  return rec.reg;
}
function epRegLog(rec, e) {
  const g = epRegInit(rec);
  e.on = e.on || epXNow();
  g.log.push(e); g.ver = (g.ver || 0) + 1;
}
function epRegRow(rec, code, serial, extra) {
  const d = (typeof epSdrl === 'function') ? epSdrl(code) : null;
  return Object.assign({ id:epXId(), code:code, serial:serial, npcc:epRegNpccNo(rec, code, serial), adnoc:'',
    vendorNo:'', rev:'', cls: d ? d.cls : '', title: d ? d.title : '', planned:'', actual:'',
    npccSt:'', coSt:'', remarks:'', route:'smartexpedit', deleted:null, x:{}, fromSdr:false, by:'' }, extra || {});
}
function epRegRenumber(rec) {
  let n = 0;
  rec.reg.rows.forEach(function (r) { r.sl = r.deleted ? '' : ++n; });
}
/* "Create register" — one row per SDR code of the MR, everything the system
   knows already filled: NPCC number, class, title, planned date. */
function epRegCreateFromSdr(rec, who, side) {
  const g = epRegInit(rec);
  const x = epExpMrExtract(rec);
  const sdr = (x && x.sdr && x.sdr.rows) || [];
  const have = {}; g.rows.forEach(function (r) { have[r.code] = true; });
  let added = 0;
  sdr.forEach(function (s) {
    if (have[s.code]) return;
    const row = epRegRow(rec, s.code, 1, { title: s.desc || '', planned: epRegPlannedFrom(rec, s.dateReq),
      fromSdr:true, sdrReq:s.dateReq || '', sdrReview:s.review || '', by:side });
    const d = epSdrl(s.code);
    if (d && d.cls) row.cls = d.cls;
    g.rows.push(row); added++;
  });
  /* the register lists itself first */
  g.rows.sort(function (a, b) { return a.code === 'A001' ? -1 : b.code === 'A001' ? 1 : 0; });
  epRegRenumber(rec);
  g.createdOn = g.createdOn || epXNow(); g.createdBy = g.createdBy || who;
  epRegLog(rec, { by:who, side:side, act:'create', txt:'Register created from the MR’s SDR — ' + added + ' row(s).' });
  return added;
}
function epRegFind(rec, id) { return (rec.reg && rec.reg.rows || []).find(function (r) { return r.id === id; }) || null; }
function epRegNextSerial(rec, code) {
  return (rec.reg.rows.filter(function (r) { return r.code === code; }).reduce(function (m, r) { return Math.max(m, r.serial || 0); }, 0)) + 1;
}
function epRegAdd(rec, code, who, side, title) {
  const g = epRegInit(rec);
  const d = epSdrl(code);
  const serial = epRegNextSerial(rec, code);
  const row = epRegRow(rec, code, serial, { title: title || (d ? d.title : ''), by:side });
  /* keep a code's serials together */
  let at = -1; g.rows.forEach(function (r, i) { if (r.code === code) at = i; });
  if (at >= 0) g.rows.splice(at + 1, 0, row); else g.rows.push(row);
  epRegRenumber(rec);
  epRegLog(rec, { by:who, side:side, act:'add', row:row.id, code:code, txt:'Added ' + row.npcc + (d ? '' : ' — code not in the SDRL master') });
  return row;
}
function epRegSet(rec, id, field, value, who, side) {
  const r = epRegFind(rec, id); if (!r) return { ok:false, msg:'no row' };
  if (r.deleted) return { ok:false, msg:'row is deleted' };
  if ((field === 'npccSt' || field === 'coSt') && side === 'Vendor') return { ok:false, msg:'review status is set by NPCC' };
  const isExtra = field.indexOf('x:') === 0;
  const old = isExtra ? (r.x[field.slice(2)] || '') : (r[field] == null ? '' : r[field]);
  value = value == null ? '' : String(value).trim();
  if (String(old) === value) return { ok:true, same:true };
  if (isExtra) r.x[field.slice(2)] = value; else r[field] = value;
  r.marks = r.marks || {};
  r.marks[field] = { by:who, side:side, on:epXNow(), old:old };
  epRegLog(rec, { by:who, side:side, act:'edit', row:id, code:r.code, field:field, old:old, val:value });
  return { ok:true };
}
function epRegDelete(rec, id, who, side, why) {
  const r = epRegFind(rec, id); if (!r || r.deleted) return { ok:false };
  if (!why) return { ok:false, msg:'a reason is required' };
  r.deleted = { by:who, side:side, on:epXNow(), why:why };
  epRegRenumber(rec);
  epRegLog(rec, { by:who, side:side, act:'delete', row:id, code:r.code, txt:'Deleted ' + r.npcc + ' — ' + why });
  return { ok:true };
}
function epRegRestore(rec, id, who, side) {
  const r = epRegFind(rec, id); if (!r || !r.deleted) return { ok:false };
  r.deleted = null; epRegRenumber(rec);
  epRegLog(rec, { by:who, side:side, act:'restore', row:id, code:r.code, txt:'Restored ' + r.npcc });
  return { ok:true };
}
function epRegAddColumn(rec, label, who, side) {
  const g = epRegInit(rec);
  label = String(label || '').trim(); if (!label) return null;
  const key = 'c' + (g.extra.length + 1) + label.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 10);
  g.extra.push({ key:key, label:label, by:who, side:side, on:epXNow() });
  epRegLog(rec, { by:who, side:side, act:'col', txt:'Added column “' + label + '” (kept apart from the fixed format)' });
  return key;
}
function epRegToggleHidden(rec, view, key) {
  const g = epRegInit(rec);
  const h = g.hidden[view] = g.hidden[view] || [];
  const i = h.indexOf(key); if (i >= 0) h.splice(i, 1); else h.push(key);
}
function epRegSetRoute(rec, id, route, who, side) {
  const r = epRegFind(rec, id); if (!r) return;
  const old = r.route; r.route = route;
  epRegLog(rec, { by:who, side:side, act:'route', row:id, code:r.code, field:'route', old:old, val:route,
                  txt:r.npcc + ' — ' + EP_REG_ROUTES[route] });
}

/* the expeditor's check: register against the MR's SDR and the SDRL master */
function epRegCheck(rec) {
  const out = [];
  const g = rec.reg; if (!g) return out;
  const live = g.rows.filter(function (r) { return !r.deleted; });
  const x = epExpMrExtract(rec);
  const sdr = (x && x.sdr && x.sdr.rows) || [];
  const inSdr = {}; sdr.forEach(function (s) { inSdr[s.code] = s; });
  const inReg = {}; live.forEach(function (r) { (inReg[r.code] = inReg[r.code] || []).push(r); });
  sdr.forEach(function (s) {
    if (!inReg[s.code]) out.push({ kind:'missing', sev:'rose', code:s.code, txt:s.code + ' ' + s.desc + ' is required by the MR’s SDR but is not on the register.' });
  });
  Object.keys(inReg).forEach(function (code) {
    const d = epSdrl(code);
    if (!d) out.push({ kind:'unknown', sev:'rose', code:code, txt:code + ' is not an SDRL code — the document cannot be registered under it.' });
    else if (sdr.length && !inSdr[code]) out.push({ kind:'extra', sev:'amber', code:code, txt:code + ' ' + d.title + ' is not in the MR’s SDR — added beyond the minimum (check it belongs).' });
    inReg[code].forEach(function (r) {
      if (d && r.cls !== '' && String(r.cls) !== String(d.cls))
        out.push({ kind:'class', sev:'amber', code:code, txt:r.npcc + ': class ' + r.cls + ' but the SDRL master says ' + d.cls + '.' });
    });
    const serials = inReg[code].map(function (r) { return r.serial; }).sort(function (a, b) { return a - b; });
    serials.forEach(function (s, i) {
      if (s !== i + 1) out.push({ kind:'serial', sev:'amber', code:code, txt:code + ': serial ' + epXz(s).padStart(3, '0') + ' with ' + epXz(i + 1).padStart(3, '0') + ' missing.' });
    });
  });
  live.forEach(function (r) {
    if (r.planned && r.actual && r.actual > r.planned) {
      const late = epXDiff(r.planned, r.actual);
      out.push({ kind:'late', sev:'amber', code:r.code, txt:r.npcc + ' submitted ' + late + ' day(s) after its planned date.' });
    } else if (r.planned && !r.actual && r.planned < epXToday()) {
      out.push({ kind:'overdue', sev:'rose', code:r.code, txt:r.npcc + ' was due ' + r.planned + ' and has not been submitted — chase.' });
    }
  });
  return out;
}
function epRegStats(rec) {
  const live = ((rec.reg && rec.reg.rows) || []).filter(function (r) { return !r.deleted; });
  return {
    total: live.length,
    submitted: live.filter(function (r) { return r.actual; }).length,
    approved: live.filter(function (r) { return /^[AD]$/.test(r.npccSt) || /^[124]$/.test(r.coSt); }).length,
    commented: live.filter(function (r) { return r.npccSt === 'B' || r.coSt === '3'; }).length,
    rejected: live.filter(function (r) { return r.npccSt === 'C' || r.coSt === '5'; }).length,
    overdue: live.filter(function (r) { return r.planned && !r.actual && r.planned < epXToday(); }).length,
  };
}

/* ---- .xlsx out: the register as the vendor fills it, tagged ------------- */
function epRegXlsxBytes(rec) {
  const cols = epRegCols(rec).filter(function (c) { return c.key !== 'route'; });
  const extra = (rec.reg.extra || []);
  const head = cols.map(function (c) { return { header:c.label, width: Math.max(10, Math.round(c.w / 7)) }; })
    .concat(extra.map(function (e) { return { header:e.label + ' *', width:18 }; }));
  const rows = rec.reg.rows.filter(function (r) { return !r.deleted; }).map(function (r) {
    return cols.map(function (c) { return r[c.key] == null ? '' : String(r[c.key]); })
      .concat(extra.map(function (e) { return r.x[e.key] || ''; }));
  });
  const kind = epExpClientKind(rec) === 'adnoc' ? 'VENDOR DATA REGISTER' : 'SUPPLIER DATA REGISTER';
  const spec = { sheetName:'SDRL', title: kind + ' — PO ' + rec.po + ' — ' + (rec.head || '') + ' — ' + (rec.supplier || '') +
                 ' — Document ' + epRegNpccNo(rec, 'A001', 1), columns: head, rows: rows };
  const sheetXml = miniBuildSheetXml(spec);
  const tag = 'SMARTEXPEDIT|' + rec.po + '|v' + (rec.reg.ver || 0);
  /* the hidden tag rides on a hidden defined name in the workbook */
  const enc = new TextEncoder();
  const bytes = miniAssembleXlsx('SDRL', sheetXml, miniStylesXml());
  return epRegRetag(bytes, tag);
}
/* rebuild the zip with a workbook.xml that carries the hidden tag */
function epRegRetag(zipBytes, tag) {
  /* xlsx_mini has no defined-name support; build our own file list the same way */
  const enc = new TextEncoder();
  const wb = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    '<sheets><sheet name="SDRL" sheetId="1" r:id="rId1"/></sheets>' +
    '<definedNames><definedName name="SMARTEXPEDIT_TAG" hidden="1">"' + miniXesc(tag) + '"</definedName></definedNames></workbook>';
  return epRegZipReplace(zipBytes, 'xl/workbook.xml', enc.encode(wb));
}
function epRegZipReplace(zipBytes, name, data) {
  /* read the stored (uncompressed) zip that miniBuildZip writes and rebuild it */
  const b = zipBytes, dv = new DataView(b.buffer, b.byteOffset, b.byteLength), dec = new TextDecoder();
  const files = []; let p = 0;
  while (p + 30 < b.length && dv.getUint32(p, true) === 0x04034b50) {
    const csize = dv.getUint32(p + 18, true), nlen = dv.getUint16(p + 26, true), elen = dv.getUint16(p + 28, true);
    const nm = dec.decode(b.subarray(p + 30, p + 30 + nlen));
    const body = b.subarray(p + 30 + nlen + elen, p + 30 + nlen + elen + csize);
    files.push({ name:nm, data: nm === name ? data : body.slice() });
    p += 30 + nlen + elen + csize;
  }
  return miniBuildZip(files);
}

/* ---- .xlsx in: map the vendor's sheet back into our format, as a preview -- */
function epRegNorm(s) { return String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]/g, ''); }
const EP_REG_HEADER_ALIASES = {
  sl:['slno','sno','serial','srno','no'], npcc:['npccdocumentno','npccdocno','contractordocumentno','nmdcdocumentno','npccdocument'],
  adnoc:['adnocdocumentno','adnocdocno','companydocumentno','clientdocumentno'],
  vendorNo:['vendordocumentno','vendordocno','supplierdocumentno','vendordocument'], rev:['rev','revision'],
  cls:['documentclass','class'], title:['title','documenttitle','description'],
  planned:['planneddate','planned'], actual:['actualdate','actual'],
  npccSt:['npccstatus','documentstatus','status'], coSt:['companystatus','clientstatus','adnocstatus'], remarks:['remarks','remark','comments'],
};
function epRegParseUpload(rec, parsed) {
  const rows = parsed.rows || [];
  let hr = -1;
  for (let i = 0; i < Math.min(rows.length, 30); i++) {
    const r = (rows[i] || []).map(epRegNorm);
    if (r.some(function (c) { return c === 'slno' || c.indexOf('npccdocument') === 0 || c.indexOf('vendordocument') === 0; })) { hr = i; break; }
  }
  if (hr < 0) return { ok:false, msg:'No header row found — the sheet needs a row with "Sl No." / "NPCC Document No.".' };
  const header = rows[hr] || [];
  const map = {}, unmapped = [], extraCols = [];
  header.forEach(function (h, ci) {
    if (h == null || h === '') return;
    const n = epRegNorm(h);
    const key = Object.keys(EP_REG_HEADER_ALIASES).find(function (k) {
      return EP_REG_HEADER_ALIASES[k].some(function (a) { return n === a || (a.length > 5 && n.indexOf(a) === 0); });
    });
    if (key && map[key] == null) map[key] = ci;
    else {
      const ex = (rec.reg.extra || []).find(function (e) { return epRegNorm(e.label) === n.replace(/\*$/, '') || epRegNorm(e.label + ' *') === n; });
      if (ex) map['x:' + ex.key] = ci; else { unmapped.push(String(h)); extraCols.push({ label:String(h).replace(/\s*\*$/, ''), ci:ci }); }
    }
  });
  const tag = parsed.names && parsed.names.SMARTEXPEDIT_TAG ? parsed.names.SMARTEXPEDIT_TAG.replace(/^"|"$/g, '') : '';
  const tp = tag.split('|');
  const res = { ok:true, header:hr, map:map, unmapped:unmapped, extraCols:extraCols, tag:tag,
                tagPo: tp[1] || '', tagVer: tp[2] ? +tp[2].replace('v', '') : null,
                changes:[], added:[], missing:[], unknown:[], rows:[] };
  const byNpcc = {}; rec.reg.rows.forEach(function (r) { if (!r.deleted) byNpcc[epRegNorm(r.npcc)] = r; });
  const seen = {};
  const val = function (row, k) {
    const ci = map[k]; if (ci == null) return '';
    let v = row[ci];
    if ((k === 'planned' || k === 'actual') && typeof v === 'number') v = epXlsxDate(v) || v;
    if ((k === 'planned' || k === 'actual') && typeof v === 'string') {
      const m = v.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{2,4})$/);
      if (m) v = (m[3].length === 2 ? '20' + m[3] : m[3]) + '-' + epXz(m[2]) + '-' + epXz(m[1]);
    }
    return v == null ? '' : String(v).trim();
  };
  for (let i = hr + 1; i < rows.length; i++) {
    const row = rows[i]; if (!row) continue;
    const npcc = val(row, 'npcc'), title = val(row, 'title');
    if (!npcc && !title) continue;
    if (/^\*|document class:|^class:|serial number to continue/i.test(String(row[0] || '') + String(row[1] || ''))) continue;
    const code = (npcc.match(/-([A-Z]\d{3})-\d{3}/) || npcc.match(/\b([A-Z]\d{3})\b/) || [])[1] || '';
    const serial = +((npcc.match(/-[A-Z]\d{3}-(\d{3})/) || [])[1] || 1);
    const incoming = { npcc:npcc, code:code, serial:serial, adnoc:val(row, 'adnoc'), vendorNo:val(row, 'vendorNo'),
      rev:val(row, 'rev'), cls:val(row, 'cls'), title:title, planned:val(row, 'planned'), actual:val(row, 'actual'),
      npccSt:val(row, 'npccSt'), coSt:val(row, 'coSt'),
      remarks:val(row, 'remarks'), x:{} };
    Object.keys(map).forEach(function (k) { if (k.indexOf('x:') === 0) incoming.x[k.slice(2)] = String(row[map[k]] == null ? '' : row[map[k]]); });
    extraCols.forEach(function (e) { incoming.x['new:' + e.label] = String(row[e.ci] == null ? '' : row[e.ci]); });
    res.rows.push(incoming);
    if (code && !epSdrl(code)) res.unknown.push(npcc || title);
    const cur = byNpcc[epRegNorm(npcc)];
    if (cur) {
      seen[cur.id] = true;
      ['adnoc', 'vendorNo', 'rev', 'cls', 'title', 'planned', 'actual', 'npccSt', 'coSt', 'remarks'].forEach(function (f) {
        if (map[f] == null) return;
        if (String(cur[f] || '') !== String(incoming[f] || '')) res.changes.push({ id:cur.id, npcc:cur.npcc, field:f, old:cur[f] || '', val:incoming[f] || '' });
      });
      Object.keys(incoming.x).forEach(function (k) {
        if (k.indexOf('new:') === 0) return;
        if (String(cur.x[k] || '') !== String(incoming.x[k] || '')) res.changes.push({ id:cur.id, npcc:cur.npcc, field:'x:' + k, old:cur.x[k] || '', val:incoming.x[k] });
      });
    } else {
      res.added.push(incoming);
    }
  }
  rec.reg.rows.forEach(function (r) { if (!r.deleted && !seen[r.id]) res.missing.push(r.npcc); });
  res.stale = res.tagVer != null && res.tagVer < (rec.reg.ver || 0);
  res.wrongPo = !!res.tagPo && res.tagPo !== rec.po;
  return res;
}
function epRegApplyUpload(rec, prev, who, side, opts) {
  opts = opts || {};
  if (side === 'Vendor') prev.changes = prev.changes.filter(function (c) { return c.field !== 'npccSt' && c.field !== 'coSt'; });
  const keyOf = {};
  (prev.extraCols || []).forEach(function (e) { keyOf[e.label] = epRegAddColumn(rec, e.label, who, side); });
  prev.changes.forEach(function (c) { epRegSet(rec, c.id, c.field, c.val, who, side); });
  prev.added.forEach(function (a) {
    if (!a.code) return;
    const row = epRegAdd(rec, a.code, who, side, a.title);
    ['adnoc', 'vendorNo', 'rev', 'planned', 'actual', 'remarks'].forEach(function (f) { if (a[f]) row[f] = a[f]; });
    Object.keys(a.x).forEach(function (k) {
      if (k.indexOf('new:') === 0) { if (keyOf[k.slice(4)]) row.x[keyOf[k.slice(4)]] = a.x[k]; }
      else row.x[k] = a.x[k];
    });
  });
  /* new-column values on existing rows */
  prev.rows.forEach(function (inc) {
    const cur = rec.reg.rows.find(function (r) { return !r.deleted && epRegNorm(r.npcc) === epRegNorm(inc.npcc); });
    if (!cur) return;
    Object.keys(inc.x).forEach(function (k) {
      if (k.indexOf('new:') === 0 && keyOf[k.slice(4)] && inc.x[k]) cur.x[keyOf[k.slice(4)]] = inc.x[k];
    });
  });
  if (opts.deleteMissing) prev.missing.forEach(function (npcc) {
    const r = rec.reg.rows.find(function (x) { return x.npcc === npcc && !x.deleted; });
    if (r) epRegDelete(rec, r.id, who, side, 'not on the uploaded sheet');
  });
  epRegLog(rec, { by:who, side:side, act:'upload', txt:'Excel uploaded — ' + prev.changes.length + ' change(s), ' + prev.added.length + ' new row(s).' });
}

/* VDMS hand-off (MODELLED): the cover-sheet data the document controller needs */
function epRegVdmsSheet(rec, r) {
  return [
    ['Project', rec.project + ' — ' + (rec.head || '')],
    ['Purchase order', rec.po],
    ['Vendor', rec.supplier],
    ['NPCC document no.', r.npcc],
    ['ADNOC document no.', r.adnoc || '(to be assigned by Document Control)'],
    ['Vendor document no.', r.vendorNo || ''],
    ['Revision', r.rev || ''],
    ['Document class', r.cls],
    ['Title', r.title],
    ['SDRL code / custodian', r.code + ' — ' + ((epSdrl(r.code) || {}).custodian || '')],
  ];
}

/* ================================================================ SCHEDULE */
const EP_SCH_MIN = [
  'PO date', 'PO acknowledgement', 'Drg, Datasheet, ITP, SVL, Schedule submission', 'Kick off meeting',
  'Drg, Datasheet, ITP, SVL approval', 'Pre-inspection meeting', 'Sub-orders placement', 'Sub-orders manufacturing',
  'Sub-orders delivery', 'Start Fabrication', 'End Fabrication', 'Assembly', 'Internal Testing',
  'Inspection notification', 'FAT / Inspection', 'Punch point closure', 'IRN issuance', 'Exw readiness',
  'FOB Port of dispatch (for FOB orders)', 'CFR Port of arrival (for CFR orders)',
  'Delivered at destination (for DDP/DDU/DAP)', 'SPIR submission (if applicable)', 'MRB submission',
];
const EP_SCH_RULES = [
  'The above rows and columns must be incorporated in any schedule, as a minimum.',
  'The Duration, Baseline start and end dates are the dates considered to meet the contractual date, and shall not change throughout the execution of the order.',
  'The sub-orders’ related activities shall be expanded separately for each critical sub-order.',
  'All Witness and HOLD points of the ITP must be included as these activities impact the schedule.',
  'Schedule in excel format is acceptable.',
];
const EP_SCH_COLS = [
  { key:'act',  label:'Activity',                 w:280 },
  { key:'resp', label:'Responsible',              w:90 },
  { key:'dur',  label:'Duration (days)',          w:80, num:true },
  { key:'bS',   label:'Baseline Start',           w:112, date:true, base:true },
  { key:'bE',   label:'Baseline End',             w:112, date:true, base:true },
  { key:'fS',   label:'Forecast / Actual Start',  w:112, date:true },
  { key:'fE',   label:'Forecast / Actual End',    w:112, date:true },
  { key:'dep',  label:'Dependency',               w:200 },
  { key:'pct',  label:'% Complete',               w:70, num:true },
];
function epSchInit(rec) {
  if (rec.sch && rec.sch.rows && rec.sch.rows.length) return rec.sch;
  const lots = (rec.lots || []).filter(function (l) { return l.date; }).map(function (l) { return l.date; }).sort();
  const lastLot = lots.length ? lots[lots.length - 1] : '';
  const inc = String(rec.incoterm || '').toUpperCase().split(' ')[0];
  rec.sch = { rows: EP_SCH_MIN.map(function (a, i) {
    const r = { id:epXId(), act:a, min:true, kind:'min', resp:'', dur:'', bS:'', bE:'', fS:'', fE:'', dep:'', pct:'', na:null, x:{}, marks:{} };
    if (i === 0) { r.bS = r.bE = rec.issuedOn || ''; r.fS = r.fE = rec.issuedOn || ''; r.pct = '100'; r.resp = 'NMDC'; }
    if (/^Delivered at destination/.test(a) && /^(DDP|DDU|DAP|DPU)$/.test(inc)) { r.bE = lastLot; }
    if (/^Exw readiness/.test(a) && /^(EXW|FCA)$/.test(inc)) { r.bE = lastLot; }
    if (/^FOB Port/.test(a) && inc === 'FOB') r.bE = lastLot;
    if (/^CFR Port/.test(a) && /^(CFR|CIF)$/.test(inc)) r.bE = lastLot;
    return r;
  }), cols:[], frozen:null, rebase:[], issues:[], log:[], ver:0,
     items:{ milestones:[], cells:{} } };
  return rec.sch;
}
/* the incoterm decides which delivery rows apply — a suggestion, the expeditor confirms */
function epSchNaSuggest(rec, row) {
  const inc = String(rec.incoterm || '').toUpperCase().split(' ')[0];
  if (/^FOB Port/.test(row.act) && inc && inc !== 'FOB') return 'Incoterm ' + inc + ' — not a FOB order';
  if (/^CFR Port/.test(row.act) && inc && !/^(CFR|CIF)$/.test(inc)) return 'Incoterm ' + inc + ' — not a CFR order';
  if (/^Delivered at destination/.test(row.act) && inc && !/^(DDP|DDU|DAP|DPU)$/.test(inc)) return 'Incoterm ' + inc + ' — delivery ends at the supplier’s works / port';
  return '';
}
function epSchLog(rec, e) { e.on = e.on || epXNow(); rec.sch.log.push(e); rec.sch.ver = (rec.sch.ver || 0) + 1; }
function epSchFind(rec, id) { return (rec.sch.rows || []).find(function (r) { return r.id === id; }) || null; }
function epSchSet(rec, id, field, value, who, side, reason) {
  const r = epSchFind(rec, id); if (!r) return { ok:false, msg:'no row' };
  const col = EP_SCH_COLS.find(function (c) { return c.key === field; });
  if (r.min && field === 'act') return { ok:false, msg:'minimum-requirement activities cannot be renamed' };
  if (col && col.base && rec.sch.frozen) return { ok:false, msg:'the baseline is frozen — only a signed re-baseline can move it' };
  const isX = field.indexOf('x:') === 0;
  const old = isX ? (r.x[field.slice(2)] || '') : (r[field] == null ? '' : String(r[field]));
  value = value == null ? '' : String(value).trim();
  if (old === value) return { ok:true, same:true };
  /* after the baseline is accepted a forecast that moves needs a reason */
  if (rec.sch.frozen && (field === 'fS' || field === 'fE') && old && !reason && !r.dep)
    return { ok:false, need:'reason', msg:'the forecast moved — say why (dependency)' };
  if (isX) r.x[field.slice(2)] = value; else r[field] = value;
  if (reason) r.dep = reason;
  if ((field === 'bS' || field === 'bE') && r.bS && r.bE && !r.dur) r.dur = String(epXDiff(r.bS, r.bE));
  r.marks = r.marks || {};
  r.marks[field] = { by:who, side:side, on:epXNow(), old:old };
  epSchLog(rec, { by:who, side:side, act:'edit', row:id, field:field, old:old, val:value, why:reason || '' });
  return { ok:true };
}
function epSchAdd(rec, afterId, act, who, side, kind, extra) {
  const rows = rec.sch.rows;
  const r = Object.assign({ id:epXId(), act:act || 'New activity', min:false, kind:kind || 'add', resp: side === 'Vendor' ? 'Vendor' : '',
    dur:'', bS:'', bE:'', fS:'', fE:'', dep:'', pct:'', na:null, x:{}, marks:{}, by:side }, extra || {});
  const i = rows.findIndex(function (x) { return x.id === afterId; });
  if (i >= 0) rows.splice(i + 1, 0, r); else rows.push(r);
  epSchLog(rec, { by:who, side:side, act:'add', row:r.id, txt:'Added “' + r.act + '”' });
  return r;
}
function epSchDelete(rec, id, who, side, why) {
  const r = epSchFind(rec, id); if (!r) return { ok:false };
  if (r.min) return { ok:false, msg:'a minimum-requirement row cannot be deleted — mark it not applicable with a reason' };
  if (!why) return { ok:false, msg:'a reason is required' };
  r.deleted = { by:who, side:side, on:epXNow(), why:why };
  epSchLog(rec, { by:who, side:side, act:'delete', row:id, txt:'Deleted “' + r.act + '” — ' + why });
  return { ok:true };
}
function epSchSetNa(rec, id, why, who, side) {
  const r = epSchFind(rec, id); if (!r) return;
  r.na = why ? { why:why, by:who, side:side, on:epXNow() } : null;
  epSchLog(rec, { by:who, side:side, act:'na', row:id, txt:(why ? 'Not applicable: ' + r.act + ' — ' + why : 'Applicable again: ' + r.act) });
}
function epSchAddColumn(rec, label, who, side) {
  label = String(label || '').trim(); if (!label) return null;
  const key = 'c' + (rec.sch.cols.length + 1) + label.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 10);
  rec.sch.cols.push({ key:key, label:label, by:who, side:side, on:epXNow() });
  epSchLog(rec, { by:who, side:side, act:'col', txt:'Added column “' + label + '”' });
  return key;
}
function epSchLive(rec) { return (rec.sch && rec.sch.rows || []).filter(function (r) { return !r.deleted; }); }
/* rule 4: the ITP's hold and witness points must sit in the schedule */
function epSchItpMissing(rec) {
  const x = epExpMrExtract(rec);
  const pts = (x && x.itr && typeof epMrItrPoints === 'function') ? epMrItrPoints(x.itr) : [];
  const live = epSchLive(rec);
  return pts.filter(function (p) {
    return !live.some(function (r) { return r.itpOf === p.activity || r.act.toLowerCase() === p.activity.toLowerCase(); });
  });
}
function epSchAddItp(rec, who, side) {
  const miss = epSchItpMissing(rec);
  /* inspection points sit before the FAT / Inspection row */
  const anchor = epSchLive(rec).find(function (r) { return /^Inspection notification/.test(r.act); });
  let after = anchor ? anchor.id : null;
  miss.forEach(function (p) {
    const r = epSchAdd(rec, after, p.activity, who, side, 'itp',
      { itp:p.kind, itpOf:p.activity, itpNpcc:p.npcc, itpCo:p.company, resp:'Vendor / NPCC Inspection' });
    after = r.id;
  });
  return miss.length;
}
function epSchFreeze(rec, who) {
  rec.sch.frozen = { by:who, on:epXNow(), rev:(rec.sch.rebase || []).length };
  epSchLog(rec, { by:who, side:'NPCC', act:'freeze', txt:'Baseline accepted and frozen' });
}
function epSchRebaseline(rec, who, why) {
  const snap = epSchLive(rec).map(function (r) { return { act:r.act, bS:r.bS, bE:r.bE }; });
  rec.sch.rebase.push({ by:who, on:epXNow(), why:why, before:snap });
  rec.sch.frozen = null;
  epSchLog(rec, { by:who, side:'NPCC', act:'rebase', txt:'Re-baseline opened (signed by ' + who + ') — ' + why });
}
/* the checks his files showed are needed */
function epSchChecks(rec) {
  const out = [];
  if (!rec.sch) return out;
  const po = rec.issuedOn || '';
  const lots = (rec.lots || []).filter(function (l) { return l.date; }).map(function (l) { return l.date; }).sort();
  const contractual = lots.length ? lots[lots.length - 1] : '';
  epSchLive(rec).forEach(function (r) {
    if (r.na) return;
    if (r.bS && r.bE && r.bE < r.bS) out.push({ sev:'rose', id:r.id, txt:r.act + ': baseline ends (' + r.bE + ') before it starts (' + r.bS + ').' });
    if (r.fS && r.fE && r.fE < r.fS) out.push({ sev:'rose', id:r.id, txt:r.act + ': forecast ends (' + r.fE + ') before it starts (' + r.fS + ').' });
    if (po && r.bS && r.bS < po && !/^PO date/.test(r.act)) out.push({ sev:'rose', id:r.id, txt:r.act + ': baseline starts ' + r.bS + ', before the PO date ' + po + ' — a baseline carried over from the bid?' });
    if (po && r.fS && r.fS < po && !/^PO date/.test(r.act)) out.push({ sev:'amber', id:r.id, txt:r.act + ': forecast starts before the PO date.' });
    if (r.fE && r.bE && r.fE > r.bE && !r.dep) out.push({ sev:'amber', id:r.id, txt:r.act + ': forecast is ' + epXDiff(r.bE, r.fE) + ' day(s) behind baseline with no dependency given.' });
    if (contractual && /^(Delivered at destination|Exw readiness|FOB Port|CFR Port)/.test(r.act) && (r.fE || r.bE) > contractual)
      out.push({ sev:'rose', id:r.id, txt:r.act + ': ' + (r.fE ? 'forecast ' + r.fE : 'baseline ' + r.bE) + ' is past the contractual delivery ' + contractual + '.' });
    const yr = /^(\d{4})/;
    [r.bS, r.bE, r.fS, r.fE].forEach(function (d) {
      if (d && po && Math.abs(+d.slice(0, 4) - +po.slice(0, 4)) > 2) out.push({ sev:'amber', id:r.id, txt:r.act + ': ' + d + ' is far from the PO year — typo?' });
    });
  });
  const missMin = epSchLive(rec).filter(function (r) { return r.min && !r.na && !r.bE && !/^PO date/.test(r.act); }).length;
  if (missMin) out.push({ sev:'amber', txt:missMin + ' minimum-requirement row(s) have no baseline end yet.' });
  const itp = epSchItpMissing(rec);
  if (itp.length) out.push({ sev:'amber', txt:itp.length + ' ITP hold / witness point(s) are not in the schedule yet (rule 4).' });
  return out;
}
/* planned vs actual, from the schedule itself — not typed */
function epSchProgress(rec, asOf) {
  asOf = asOf || epXToday();
  /* the PO date row is always complete — counting it alone would read 100% */
  const rows = epSchLive(rec).filter(function (r) { return !r.na && r.bS && r.bE && !/^PO date/.test(r.act); });
  if (!rows.length) return { planned:null, actual:null, n:0 };
  let p = 0, a = 0, w = 0;
  rows.forEach(function (r) {
    const dur = Math.max(1, epXDiff(r.bS, r.bE) + 1);
    const el = epXDiff(r.bS, asOf) + 1;
    p += dur * Math.max(0, Math.min(1, el / dur));
    a += dur * Math.max(0, Math.min(1, (+r.pct || 0) / 100));
    w += dur;
  });
  return { planned: Math.round(p / w * 100), actual: Math.round(a / w * 100), n: rows.length };
}
/* the forecast delivery the Order Head shows — from the schedule */
function epSchForecastDelivery(rec) {
  if (!rec.sch) return '';
  const r = epSchLive(rec).filter(function (x) { return !x.na && /^(Delivered at destination|CFR Port|FOB Port|Exw readiness)/.test(x.act); })
    .map(function (x) { return x.fE || x.bE; }).filter(Boolean).sort();
  return r.length ? r[r.length - 1] : '';
}
/* issue the schedule as the next revision of Z003 in the register, with its comments sheet */
function epSchIssue(rec, who, side, desc) {
  const rev = (rec.sch.issues || []).length + 1;
  rec.sch.issues.push({ rev:rev, on:epXNow(), by:who, side:side, desc:desc || 'Issued for Review',
    snap: epSchLive(rec).map(function (r) { return { act:r.act, bS:r.bS, bE:r.bE, fS:r.fS, fE:r.fE, pct:r.pct, na:!!r.na }; }),
    comments:[] });
  epRegInit(rec);
  let z = rec.reg.rows.find(function (r) { return r.code === 'Z003' && !r.deleted; });
  if (!z) z = epRegAdd(rec, 'Z003', who, side, 'Manufacturing Schedule');
  epRegSet(rec, z.id, 'rev', String(rev), who, side);
  epRegSet(rec, z.id, 'actual', epXToday(), who, side);
  epSchLog(rec, { by:who, side:side, act:'issue', txt:'Schedule issued as ' + z.npcc + ' Rev ' + rev });
  return { rev:rev, npcc:z.npcc };
}
function epSchComment(rec, rev, ref, comment, who) {
  const is = rec.sch.issues.find(function (i) { return i.rev === rev; }); if (!is) return;
  is.comments.push({ sl:is.comments.length + 1, ref:ref || '', comment:comment, by:who, on:epXNow(), response:'', respBy:'', respOn:'' });
}
function epSchRespond(rec, rev, sl, response, who) {
  const is = rec.sch.issues.find(function (i) { return i.rev === rev; }); if (!is) return;
  const c = is.comments.find(function (x) { return x.sl === sl; }); if (!c) return;
  c.response = response; c.respBy = who; c.respOn = epXNow();
}

/* ---- itemized layout: one row per PO line, weighted milestones ---------- */
function epSchDefaultMilestones(rec) {
  const pts = {};
  const x = epExpMrExtract(rec);
  ((x && x.itr && epMrItrPoints(x.itr)) || []).forEach(function (p) { pts[p.activity.toLowerCase()] = p.kind; });
  const tpi = function (name) { const k = Object.keys(pts).find(function (a) { return a.indexOf(name) >= 0; }); return k ? pts[k] : ''; };
  return [
    { key:'raw',   label:'Raw material received',      weight:15, tpi:'' },
    { key:'form',  label:'Forging / threading',        weight:20, tpi:'' },
    { key:'heat',  label:'Heat treatment',             weight:10, tpi:tpi('heat treatment') },
    { key:'mech',  label:'Mechanical / chemical test', weight:10, tpi:tpi('mechanical') },
    { key:'hard',  label:'Hardness test',              weight:5,  tpi:tpi('hardness') },
    { key:'coat',  label:'Coating / plating',          weight:15, tpi:'' },
    { key:'final', label:'Final inspection / IRN',     weight:15, tpi:tpi('inspection release') || 'H' },
    { key:'pack',  label:'Marking & packing',          weight:5,  tpi:tpi('packing') },
    { key:'exw',   label:'Ready at EXW',               weight:5,  tpi:'' },
  ];
}
function epSchItemsInit(rec) {
  epSchInit(rec);
  const it = rec.sch.items = rec.sch.items || { milestones:[], cells:{} };
  if (!it.milestones.length) it.milestones = epSchDefaultMilestones(rec);
  return it;
}
function epSchItemSet(rec, items, msKey, field, value, who, side) {
  const it = epSchItemsInit(rec);
  items.forEach(function (item) {
    const c = it.cells[item] = it.cells[item] || {};
    const m = c[msKey] = c[msKey] || { p:'', f:'', a:'' };
    m[field] = value || '';
  });
  epSchLog(rec, { by:who, side:side, act:'items', txt:it.milestones.find(function (m) { return m.key === msKey; }).label + ' — ' +
    { p:'planned', f:'forecast', a:'actual' }[field] + ' ' + (value || '(cleared)') + ' on ' + items.length + ' line(s)' });
}
function epSchItemsProgress(rec) {
  const it = rec.sch && rec.sch.items; const lines = (rec.items || []);
  if (!it || !it.milestones.length || !lines.length) return null;
  const W = it.milestones.reduce(function (s, m) { return s + (+m.weight || 0); }, 0) || 1;
  let done = 0, plan = 0; const today = epXToday();
  lines.forEach(function (l) {
    const c = it.cells[l.item] || {};
    it.milestones.forEach(function (m) {
      const v = c[m.key] || {};
      if (v.a) done += (+m.weight || 0);
      if (v.p && v.p <= today) plan += (+m.weight || 0);
    });
  });
  return { actual: Math.round(done / (W * lines.length) * 100), planned: Math.round(plan / (W * lines.length) * 100) };
}

/* ---- sub-orders with float (annexure-2 of the progress report) ---------- */
function epSubCalc(s) {
  const exw = s.exwF || (s.placeAct || s.placePlan ? epXAddDays(s.placeAct || s.placePlan, +s.lead || 0) : '');
  const expected = exw ? epXAddDays(exw, +s.transit || 0) : '';
  const float = (expected && s.required) ? epXDiff(expected, s.required) : null;
  return { exw:exw, expected:expected, float:float };
}

/* ================================================================== LETTER
   The introduction letter the expeditor used to email, generated from the
   order and sent on the portal. The vendor answers each point there.       */
function epLetterDraft(rec, who) {
  const x = epExpMrExtract(rec);
  const sdr = (x && x.sdr && x.sdr.rows) || [];
  const adnoc = epExpClientKind(rec) === 'adnoc';
  /* priority documents: the register itself, ITP, sub-order plan, schedule and mill certificates when the SDR asks */
  const want = ['A001', 'X002', 'Z002', 'Z003', 'R006'];
  return {
    who: who, clause: adnoc ? '5.0' : '4.0', system: adnoc ? 'NMDC VDMS' : 'NPCC VDMS',
    priority: want.filter(function (c) { return !sdr.length || sdr.some(function (s) { return s.code === c; }); }),
    replyBy: epXAddDays(epXToday(), 7), pbg: true,
    docController: 'Project Sr. Document Controller — NMDC Energy',
  };
}
function epLetterPoints(rec, L) {
  const pri = (L.priority || []).map(function (c) { const d = epSdrl(c); return c + ' ' + (d ? d.title : ''); });
  const pts = [
    { key:'contact', txt:'The undersigned (' + (L.who || rec.assignedTo || '') + ') will be responsible for expediting this order and shall be copied in all post-award communication, along with others as defined in the “Communication” clause of the PO.', reply:false },
    { key:'ack', txt:'Kindly forward the unconditional PO acknowledgement on top priority.', reply:'ack' },
    { key:'wo', txt:'Please provide your internal work order reference, with the contact details (desk phone / mobile / email) of your nominated Project Manager — the focal point for the timely execution of this order.', reply:'text' },
    { key:'docs', txt:'The following documents shall be submitted on priority, with planned submission dates: ' + pri.join('; ') + '.', reply:'dates', codes:L.priority || [] },
    { key:'vdms', txt:L.system + ' (Vendor Data Management System) shall be followed as per clause ' + L.clause + ' of the order. All documents and drawings shall be submitted through ' + L.system + ' with the cover sheet and templates shared by ' + L.docController + '.', reply:'confirm' },
  ];
  if (L.pbg) pts.push({ key:'pbg', txt:'PBG + ABG (if applicable) shall be submitted as per the format given in the appendices of the PO.', reply:'date' });
  return pts;
}
function epLetterSend(rec, L, who) {
  rec.intro = Object.assign({}, L, { sentOn:epXNow(), sentBy:who, points:epLetterPoints(rec, L), replies:{} });
  return rec.intro;
}
function epLetterReply(rec, key, reply, who) {
  if (!rec.intro) return;
  rec.intro.replies[key] = Object.assign({}, reply, { by:who, on:epXNow() });
  if (key === 'ack' && reply.date) rec.ackDate = reply.date;
}
function epLetterOpen(rec) {
  if (!rec.intro) return [];
  return rec.intro.points.filter(function (p) { return p.reply && !rec.intro.replies[p.key]; });
}
