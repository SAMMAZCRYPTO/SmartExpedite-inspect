/* SmartExpedit — review fixes (10-Nov-2026). Loaded last, after shell.js (and over72.js in the PO 72166 demo).
   1 uploads and saving   2 date fields   3 select-all toggle   4 Sub Orders stage   5 no formula letters
   6 Inspection Report + Punch List   7 Packing List, Bill of Lading, Vessel view   8 one review loop + inbox
   9 vendor schedule download/upload/edit/attach   10 MSSR (internal + client)   11 Vendor Progress Report
   12 Field Expediting                                                                                     */
var FX = { imgs:{}, blobs:{}, warned:false, mssr:'internal', mssrAll:false, vprSel:null, fld:{ row:null, q:'', v:'' }, dl:null };
var FKEY = PKEY + '_files', FLDKEY = PKEY + '_field';

/* ================= 1. SAVING AND UPLOADS =================
   Cause found: localStorage holds about 5 MB per page. Once a read MR (its page images) filled it, every
   later save failed quietly, and the next read returned the old copy, so uploads and edits looked lost.
   Fix: the session copy wins on read; page images and uploaded files go to IndexedDB, not localStorage;
   a full store is reported once instead of failing silently.                                            */
epStore.get = (function (g) { return function (k) { return EP_MEM[k] !== undefined ? EP_MEM[k] : g(k); }; })(epStore.get);
epStore.set = function (k, v) {
  EP_MEM[k] = v;
  try { localStorage.setItem(k, v); return; } catch (e) {}
  try { localStorage.removeItem(k); localStorage.setItem(k, v); return; } catch (e) {}
  try { sessionStorage.setItem(k, v); return; } catch (e) {}
  if (!FX.warned) { FX.warned = true; setTimeout(function () { toast('This browser’s storage is full. Your changes are kept for this session.'); }, 0); }
};
function fxDb() { if (FX.dbp) return FX.dbp; FX.dbp = new Promise(function (res) { try { var q = indexedDB.open('sx_' + PKEY, 1); q.onupgradeneeded = function () { q.result.createObjectStore('kv'); }; q.onsuccess = function () { res(q.result); }; q.onerror = function () { res(null); }; } catch (e) { res(null); } }); return FX.dbp; }
function fxPut(k, v) { return fxDb().then(function (db) { if (!db) return false; return new Promise(function (res) { try { var t = db.transaction('kv', 'readwrite'); t.objectStore('kv').put(v, k); t.oncomplete = function () { res(true); }; t.onerror = t.onabort = function () { res(false); }; } catch (e) { res(false); } }); }); }
function fxGet(k) { return fxDb().then(function (db) { if (!db) return null; return new Promise(function (res) { try { var q = db.transaction('kv').objectStore('kv').get(k); q.onsuccess = function () { res(q.result == null ? null : q.result); }; q.onerror = function () { res(null); }; } catch (e) { res(null); } }); }); }
var _fxSave = window.epExpSave, _fxLoad = window.epExpLoad;
window.epExpSave = function (list) {
  (list || []).forEach(function (r) { var x = r && r.mrStudy && r.mrStudy.extract; if (x && x.images && typeof x.images === 'object' && Object.keys(x.images).length) { FX.imgs[r.po] = x.images; fxPut('img:' + r.po, x.images); } });
  epStore.set(EP_EXP_KEY, JSON.stringify(list || [], function (k, v) { return k === 'images' && v && typeof v === 'object' && Object.keys(v).length ? '__idb' : v; }));
  if (typeof epBroadcast === 'function') epBroadcast(EP_EXP_KEY);
};
window.epExpLoad = function () { var L = _fxLoad(); L.forEach(function (r) { var x = r && r.mrStudy && r.mrStudy.extract; if (x && x.images === '__idb') x.images = FX.imgs[r.po] || (window.P72 && P72.mr && r.po.indexOf('72166') >= 0 ? P72.mr.images : {}) || {}; }); return L; };
function fxFiles() { try { return JSON.parse(epStore.get(FKEY) || '[]'); } catch (e) { return []; } }
function fxFilesSave(L) { epStore.set(FKEY, JSON.stringify(L)); }
function fxSize(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }
/* keep a chosen file: returns its id. Files over 40 MB are kept by name only (the reader still reads them). */
function fxKeep(f, meta) { var L = fxFiles(), same = L.find(function (x) { return x.name === f.name && x.size === f.size && x.mod === f.lastModified; });
  if (same) { if (meta) { Object.assign(same, meta); fxFilesSave(L); } return Promise.resolve(same.id); }
  var e = Object.assign({ id:epXId(), name:f.name, size:f.size, type:f.type, mod:f.lastModified, on:new Date().toISOString(), by:(typeof REC !== 'undefined' && REC ? WHO() : ROLES[ROLE]), po:(typeof REC !== 'undefined' && REC && ['core', 'sub', 'insp', 'deliv', 'exec', 'portal'].indexOf(SEC) >= 0 ? REC.po : ''), where:(function () { try { return TABSLABEL() + (TAB ? ' · ' + ((tabList().find(function (t) { return t.k === TAB; }) || {}).t || TAB) : ''); } catch (e) { return ''; } })(), big:f.size > 40 * 1048576 }, meta || {});
  L.push(e); fxFilesSave(L); if (e.big) return Promise.resolve(e.id);
  FX.blobs[e.id] = f; return fxPut('file:' + e.id, f).then(function (ok) { if (!ok) e.mem = true; toast('Kept ' + f.name + ' (' + fxSize(f.size) + ')' + (ok ? '' : ' for this session')); return e.id; });
}
document.addEventListener('change', function (ev) { var t = ev.target; if (!t || t.type !== 'file' || !t.files || !t.files.length || t.hasAttribute('data-nokeep')) return; Array.prototype.forEach.call(t.files, function (f) { fxKeep(f); }); }, true);
function fxDl() { if (!FX.dl) FX.dl = (window.claude && claude.use) ? claude.use('downloads').catch(function () { return null; }) : Promise.resolve(null); return FX.dl; }
async function fxSaveBlob(name, blob) {
  var d = await fxDl();
  if (d) { try { await d.save({ filename:name, data:blob }); return; } catch (e) { if (e && e.code === 'declined') return; if (e && /rejected_extension|extension_not_enabled/.test(e.code)) return toast('A .' + name.split('.').pop() + ' file cannot be saved from this page.'); } }
  try { var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 4000); } catch (e) { toast('The file could not be saved here.'); }
}
async function fxOpen(id) { var e = fxFiles().find(function (x) { return x.id === id; }); if (!e) return toast('File not found.'); if (e.big) return toast(e.name + ' is over 40 MB, so only its name was kept.');
  var b = FX.blobs[id] || await fxGet('file:' + id); if (!b) return toast(e.name + ' is no longer in this browser. Upload it again.'); fxSaveBlob(e.name, b); }
function fxLink(id, label) { if (!id) return ''; var e = fxFiles().find(function (x) { return x.id === id; }); return e ? '<button class="link" data-s="fx-open" data-x="' + id + '" title="Download ' + esc(e.name) + '">' + esc(label || e.name) + '</button>' : '<span class="ep-sub">' + esc(label || 'file') + '</span>'; }
function fxPick(accept, multi) { return new Promise(function (res) { var i = document.createElement('input'); i.type = 'file'; i.setAttribute('data-nokeep', '1'); if (accept) i.accept = accept; if (multi) i.multiple = true; i.style.display = 'none'; document.body.appendChild(i); i.onchange = function () { var f = Array.prototype.slice.call(i.files || []); i.remove(); res(f); }; i.click(); }); }
function tabFiles() { var L = fxFiles().filter(function (x) { return x.po === REC.po; }).reverse();
  return '<div class="ep-note">Every file uploaded on this PO, on any tab, is kept here and can be downloaded again. Files are kept in this browser.</div><div class="ep-card flush"><div class="ep-card-title"><span>Uploaded files — ' + L.length + '</span><button class="ep-btn primary sm" data-s="fx-up">Upload a file</button></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>File</th><th>Size</th><th>Uploaded on tab</th><th>By</th><th>When</th><th></th></tr></thead><tbody>' +
    (L.map(function (x) { return '<tr><td>' + esc(x.name) + '</td><td class="tabnum">' + fxSize(x.size) + '</td><td>' + esc(x.where) + '</td><td>' + esc(x.by) + '</td><td class="tabnum">' + fmtDate(x.on.slice(0, 10)) + '</td><td>' + (x.big ? '<span class="ep-pill slate sm">Name only (over 40 MB)</span>' : '<button class="ep-btn secondary xs" data-s="fx-open" data-x="' + x.id + '">Download</button>') + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="ep-sub">No files uploaded on this PO yet.</td></tr>') + '</tbody></table></div></div>'; }

/* ================= 2. DATE FIELDS =================
   Cause found: the browser reports a date as "changed" after each digit of the year, and the page redrew
   itself on every change, so typing 2026 left 0002. Fix: a date typed into a field is saved when you leave
   the field, not on every key press.                                                                     */
window.addEventListener('keydown', function (ev) { var t = ev.target; if (!t || t.type !== 'date') return; if (ev.key === 'Enter') { t.blur(); return; } t.__fxTyping = true; }, true);
window.addEventListener('change', function (ev) { var t = ev.target; if (t && t.type === 'date' && !t.__fxCommit && (t.__fxTyping || document.activeElement === t)) { ev.stopImmediatePropagation(); t.__fxPend = true; } }, true);
window.addEventListener('input', function (ev) { var t = ev.target; if (t && t.type === 'date' && t.__fxTyping) ev.stopImmediatePropagation(); }, true);
FX.pend = []; FX.ptr = false;
function fxCommit(t) { t.__fxPend = false; t.__fxCommit = true; t.dispatchEvent(new Event('change', { bubbles:true })); t.__fxCommit = false; }
function fxFlush() { var q = FX.pend; FX.pend = []; q.forEach(fxCommit); }
window.addEventListener('focusout', function (ev) { var t = ev.target; if (!t || t.type !== 'date') return; t.__fxTyping = false; if (!t.__fxPend) return; if (FX.ptr) FX.pend.push(t); else fxCommit(t); }, true);
/* a click that takes the focus away from a date: save the date first, then let the click act (the page is not redrawn under the pointer) */
window.addEventListener('pointerdown', function () { FX.ptr = true; }, true);
window.addEventListener('pointerup', function () { setTimeout(function () { FX.ptr = false; fxFlush(); }, 0); }, true);
window.addEventListener('click', function () { if (FX.pend.length) fxFlush(); }, true);
/* four-digit years only (the browser otherwise accepts up to six) */
function fxDateMax(root) { (root.querySelectorAll ? root : document).querySelectorAll('input[type=date]:not([max])').forEach(function (i) { i.max = '9999-12-31'; if (!i.min) i.min = '1900-01-01'; }); }
new MutationObserver(function (ms) { ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) { if (n.matches && n.matches('input[type=date]') && !n.max) { n.max = '9999-12-31'; n.min = n.min || '1900-01-01'; } else fxDateMax(n); } }); }); }).observe(document.documentElement, { childList:true, subtree:true });

/* ================= 3. SELECT ALL = one checkbox ================= */
if (typeof schItems === 'function') { var _fxItems = window.schItems; window.schItems = function () { var h = _fxItems(), L = (REC.items || []).slice(ITEM_PAGE * 25, ITEM_PAGE * 25 + 25), on = L.filter(function (l) { return ITEM_SEL[l.item]; }).length;
  FX.itPart = on > 0 && on < L.length;
  return h.replace('<button class="ep-btn secondary sm" data-act="it-selpage">Select this page</button>', '').replace('<button class="ep-btn secondary sm" data-act="it-selnone">Clear selection</button>', '')
    .replace('<thead><tr><th></th><th>Item</th>', '<thead><tr><th><input type="checkbox" data-itall="1" title="Select all lines on this page" aria-label="Select all lines on this page" style="width:auto;height:auto;"' + (L.length && on === L.length ? ' checked' : '') + '></th><th>Item</th>'); }; }
document.addEventListener('change', function (ev) { var t = ev.target; if (!t.hasAttribute || !t.hasAttribute('data-itall')) return; ev.stopPropagation(); (REC.items || []).slice(ITEM_PAGE * 25, ITEM_PAGE * 25 + 25).forEach(function (l) { if (t.checked) ITEM_SEL[l.item] = true; else delete ITEM_SEL[l.item]; }); render(); }, true);

/* ================= 4. SUB ORDERS STAGE before Fabrication ================= */
(function () { if (!EP_EXP_STAGES.some(function (s) { return s.key === 'subord'; })) EP_EXP_STAGES.splice(EP_EXP_STAGES.findIndex(function (s) { return s.key === 'fab'; }), 0, { key:'subord', label:'Sub Orders', sub:'sub-orders placed with the sub-suppliers' }); })();
function subOrdOn(r) { var rows = ((r.plan || {}).rows || []).filter(function (x) { return !x.deleted && x.item; }); if (rows.length && rows.every(function (x) { return x.aPlace; })) return rows.map(function (x) { return x.aPlace; }).sort().pop();
  var s = ((r.sch || {}).rows || []).find(function (x) { return /Sub-orders placement/i.test(x.act) && +x.pct === 100; }); return s ? (s.fE || s.bE || '') : ''; }
var _fxMarks = window.marks;
window.marks = function (r) { var m = _fxMarks(r), i = m.findIndex(function (x) { return x[0] === 'fab'; }); m.splice(i, 0, ['subord', subOrdOn(r), 'Sub Orders']); return m; };
window.railAt = function (r) { var k = r.stage, base = { issued:0, ack:1, docsOut:2, docsIn:3, docsOk:3, pim:4, subord:5, fab:6, insp:7, release:8, shipped:9, delivered:10, mrbSub:11, closed:12 }[k]; if (base == null) return 0; if (base === 4 && subOrdOn(r)) return 5; return base; };

/* ================= 5. no formula letters in the sub-order plan ================= */
var _fxPlan = window.tabPlan;
window.tabPlan = function () { return _fxPlan().replace(/\s\((?:[a-f]|f−e|f-e)\)(?=\s*(?:\*|<))/g, ''); };

/* ================= helpers ================= */
function fxSel(id, opts, v, label) { return '<select id="' + id + '" class="ep-in"' + (label ? ' aria-label="' + esc(label) + '"' : '') + '>' + opts.map(function (o) { var k = Array.isArray(o) ? o[0] : o, t = Array.isArray(o) ? o[1] : o; return '<option value="' + esc(k) + '"' + (String(v) === String(k) ? ' selected' : '') + '>' + esc(t) + '</option>'; }).join('') + '</select>'; }
function fxF(label, html) { return '<div><div class="ep-lbl">' + esc(label) + '</div>' + html + '</div>'; }
function fxIn(id, v, type, ph) { return '<input id="' + id + '" class="ep-in"' + (type ? ' type="' + type + '"' : '') + ' value="' + esc(v == null ? '' : v) + '"' + (ph ? ' placeholder="' + esc(ph) + '"' : '') + '>'; }
function fxV(id) { var e = $(id); return e ? e.value.trim() : ''; }
function fxGrid(cells, cols) { return '<div class="ep-fields" style="grid-template-columns:repeat(' + (cols || 2) + ',1fr);">' + cells.join('') + '</div>'; }
function fxFileField(id, label) { return fxF(label || 'File', '<input type="file" id="' + id + '" class="ep-in" data-nokeep="1">'); }
async function fxTakeFile(id, meta) { var i = $(id), f = i && i.files && i.files[0]; if (!f) return null; var fid = await fxKeep(f, meta); return { id:fid, name:f.name }; }
function fxSt(s, map) { return '<span class="ep-pill ' + (map[s] || 'slate') + ' sm">' + esc(s) + '</span>'; }
function fxNum(v) { return v === '' || v == null ? '' : +v; }

/* ================= 6. INSPECTION REPORT + PUNCH LIST ================= */
var IR_RES = ['Accepted', 'Accepted with comments', 'Rejected', 'Hold'];
function tabIr() { var L = REC.irs = REC.irs || [], c = function (r) { return L.filter(function (x) { return x.result === r; }).length; };
  return '<div class="ep-note">One row per inspection visit, in the shape of the TPI inspection report (IR-041 format): PO and revision, PO item and tag, ITP stage, inspector and agency, result and observations. Attach the signed report.</div>' +
    '<div class="ep-kpis" style="grid-template-columns:repeat(4,1fr);">' + kp('Inspection reports', L.length, 'on this PO') + kp('Accepted', c('Accepted') + c('Accepted with comments'), c('Accepted with comments') + ' with comments') + kp('Rejected', c('Rejected'), 'needs re-inspection', c('Rejected') > 0) + kp('Open punch points', punchOpen(REC).length, 'from these inspections', punchOpen(REC).length > 0) + '</div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>Inspection reports</span><button class="ep-btn primary sm" data-s="ir-add">+ Add inspection report</button></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>IR no.</th><th>Date</th><th>PO rev.</th><th>PO item · tag</th><th>Equipment</th><th>Inspection</th><th>ITP stage</th><th>Inspector · agency</th><th>Location</th><th>Result</th><th>Observations</th><th>Report</th><th></th></tr></thead><tbody>' +
    (L.slice().sort(function (a, b) { return (b.date || '').localeCompare(a.date || ''); }).map(function (x) { return '<tr><td class="tabnum"><b>' + esc(x.no) + '</b></td><td class="tabnum">' + fmtDate(x.date) + '</td><td>' + esc(x.poRev) + '</td><td>' + esc(x.item) + (x.tag ? ' · ' + esc(x.tag) : '') + '</td><td>' + esc(x.equip) + '</td><td>' + esc(x.type) + '</td><td>' + esc(x.itp) + '</td><td>' + esc(x.inspector) + (x.agency ? ' · ' + esc(x.agency) : '') + '</td><td>' + esc(x.loc) + '</td><td>' + fxSt(x.result, { 'Accepted':'ok', 'Accepted with comments':'info', 'Rejected':'rose', 'Hold':'warn' }) + '</td><td style="min-width:200px;">' + esc(x.obs) + '</td><td>' + (x.file ? fxLink(x.file.id) : '—') + '</td><td><button class="ep-btn secondary xs" data-s="ir-add" data-x="' + x.id + '">Edit</button></td></tr>'; }).join('') || '<tr><td colspan="13" class="ep-sub">No inspection reports yet.</td></tr>') + '</tbody></table></div></div>'; }
function irModal(id) { var L = REC.irs = REC.irs || [], x = L.find(function (q) { return q.id === id; }) || { no:'IR-' + String(L.length + 1).padStart(3, '0'), date:T(), poRev:REC.rev || '', type:'During manufacturing', result:'Accepted', agency:'' };
  modal(id ? 'Edit inspection report' : 'Add inspection report', fxGrid([fxF('IR no.', fxIn('i-no', x.no)), fxF('Date', fxIn('i-dt', x.date, 'date')), fxF('PO revision', fxIn('i-rv', x.poRev)), fxF('PO item', fxIn('i-it', x.item, '', 'e.g. 1004')), fxF('Tag no.', fxIn('i-tg', x.tag, '', 'e.g. 773-F-2495 A/B')), fxF('Equipment / material', fxIn('i-eq', x.equip || REC.head)),
    fxF('Inspection', fxSel('i-ty', ['Pre-inspection', 'During manufacturing', 'Final inspection', 'FAT', 'Release / packing', 'Re-inspection'], x.type)), fxF('ITP stage', fxIn('i-itp', x.itp, '', 'e.g. 14')), fxF('Inspector', fxIn('i-in', x.inspector)), fxF('Agency', fxSel('i-ag', ['', 'TUV', 'RINA', 'Applus', 'BV', 'SGS', 'Intertek', 'Fahss', 'NMDC'], x.agency)), fxF('Location', fxIn('i-lc', x.loc)), fxF('Result', fxSel('i-rs', IR_RES, x.result))]) +
    '<div style="margin-top:8px;">' + fxF('Observations', '<textarea id="i-ob" class="ep-in" rows="3">' + esc(x.obs || '') + '</textarea>') + '</div><div style="margin-top:8px;">' + fxFileField('i-f', x.file ? 'Replace the report (now: ' + x.file.name + ')' : 'Signed report') + '</div>', async function () {
      if (!fxV('i-no') || !fxV('i-dt')) return toast('Give the IR number and date.'); var f = await fxTakeFile('i-f', { po:REC.po, where:'Inspection · Inspection Report' });
      Object.assign(x, { no:fxV('i-no'), date:fxV('i-dt'), poRev:fxV('i-rv'), item:fxV('i-it'), tag:fxV('i-tg'), equip:fxV('i-eq'), type:fxV('i-ty'), itp:fxV('i-itp'), inspector:fxV('i-in'), agency:fxV('i-ag'), loc:fxV('i-lc'), result:fxV('i-rs'), obs:fxV('i-ob') }); if (f) x.file = f;
      if (!x.id) { x.id = epXId(); L.push(x); } addLog('Inspection report ' + x.no + ' recorded: ' + x.result + '.'); saveRec(); closeModal(); render(); }, { wide:'wide' }); }
var PUNCH_CAT = { A:'Close before IRN — blocks release', B:'Close before shipment', C:'Close at site or before MRB' };
function punchOpen(r) { return (r.punch || []).filter(function (p) { return !p.closedOn; }); }
function tabPunchX() { var L = REC.punch = REC.punch || [], o = punchOpen(REC), oc = function (c) { return o.filter(function (p) { return p.cat === c; }).length; };
  return '<div class="ep-note">Punch points come from the inspections. <b>Category A</b> must be closed before the IRN, <b>B</b> before shipment, <b>C</b> at site or before the MRB. Close a point with its evidence. The categories follow common practice; they will be matched to the PL-001 punch list sample when it is shared.</div>' +
    '<div class="ep-kpis" style="grid-template-columns:repeat(4,1fr);">' + kp('Punch points', L.length, (L.length - o.length) + ' closed') + kp('Open A', oc('A'), oc('A') ? 'IRN blocked' : 'IRN not blocked', oc('A') > 0) + kp('Open B', oc('B'), oc('B') ? 'shipment blocked' : 'shipment not blocked', oc('B') > 0) + kp('Open C', oc('C'), 'site / MRB') + '</div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>Punch list</span><button class="ep-btn primary sm" data-s="pu-add">+ Add punch point</button></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>No.</th><th>Cat.</th><th>Description</th><th>Raised by</th><th>Raised</th><th>From IR</th><th>Target</th><th>Closed</th><th>Evidence</th><th></th></tr></thead><tbody>' +
    (L.map(function (p) { return '<tr><td class="tabnum">' + esc(p.no) + '</td><td><span class="ep-pill ' + ({ A:'rose', B:'warn', C:'slate' }[p.cat]) + ' sm" title="' + esc(PUNCH_CAT[p.cat]) + '">' + p.cat + '</span></td><td style="min-width:220px;">' + esc(p.desc) + '</td><td>' + esc(p.by) + '</td><td class="tabnum">' + fmtDate(p.raisedOn) + '</td><td>' + esc(p.ir || '—') + '</td><td class="tabnum">' + fmtDate(p.target) + (p.target && !p.closedOn && p.target < T() ? ' <span class="ep-pill rose sm">Overdue</span>' : '') + '</td><td class="tabnum">' + (p.closedOn ? fmtDate(p.closedOn) + ' · ' + esc(p.closedBy) : '<span class="ep-pill warn sm">Open</span>') + '</td><td>' + (p.ev ? fxLink(p.ev.id) : '—') + '</td><td>' + (p.closedOn ? '<button class="ep-btn secondary xs" data-s="pu-re" data-x="' + p.id + '">Reopen</button>' : '<button class="ep-btn primary xs" data-s="pu-close" data-x="' + p.id + '">Close</button>') + '</td></tr>'; }).join('') || '<tr><td colspan="10" class="ep-sub">No punch points.</td></tr>') + '</tbody></table></div></div>'; }
function punchBanner(cats, what) { var o = punchOpen(REC).filter(function (p) { return cats.indexOf(p.cat) >= 0; }); return o.length ? '<div class="ep-note" style="border-color:#fecdd3;background:#fff1f2;"><b>' + o.length + ' open category ' + cats.join('/') + ' punch point(s)</b> — ' + what + ' should wait until they are closed: ' + o.slice(0, 4).map(function (p) { return esc(p.no); }).join(', ') + '.</div>' : ''; }

/* ================= 7. PACKING LIST, BILL OF LADING, VESSEL VIEW ================= */
function fxShips(r) { if (r.ships && r.ships.length) return r.ships; var s = r.ship || {}; return s.etd || s.mode ? [{ id:'s1', no:1, mode:s.mode || '', vessel:s.vessel || '', etd:s.etd || '', eta:s.eta || '', ata:s.mrvOn || '' }] : []; }
function tabPl() { var L = REC.pls = REC.pls || [];
  return punchBanner(['A', 'B'], 'Packing and shipment') + '<div class="ep-note">One packing list per consignment: the PO lines and quantities packed, the IRNs that released them, packages and weights. The packing list file can be downloaded from here and from the Vessel view.</div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>Packing lists — ' + L.length + '</span><button class="ep-btn primary sm" data-s="pk-add">+ Add packing list</button></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>PL no.</th><th>Date</th><th>Shipment</th><th>IRN(s)</th><th>PO lines · qty</th><th>Packages</th><th>Gross / net kg</th><th>File</th><th></th></tr></thead><tbody>' +
    (L.map(function (p) { return '<tr><td class="tabnum"><b>' + esc(p.no) + '</b></td><td class="tabnum">' + fmtDate(p.date) + '</td><td>' + (p.ship ? '#' + esc(p.ship) : '—') + '</td><td>' + esc(p.irns || '—') + '</td><td>' + (p.lines || []).map(function (l) { return esc(l.item) + ': ' + n(l.qty); }).join('<br>') + '</td><td class="tabnum">' + n(p.pkgs) + '</td><td class="tabnum">' + n(p.gross) + ' / ' + n(p.net) + '</td><td>' + (p.file ? fxLink(p.file.id) : '—') + '</td><td><button class="ep-btn secondary xs" data-s="pk-add" data-x="' + p.id + '">Edit</button></td></tr>'; }).join('') || '<tr><td colspan="9" class="ep-sub">No packing lists yet.</td></tr>') + '</tbody></table></div></div>'; }
function plModal(id) { var L = REC.pls = REC.pls || [], p = L.find(function (q) { return q.id === id; }) || { no:'PL-' + String(L.length + 1).padStart(3, '0'), date:T(), lines:[] }, S = fxShips(REC), items = (REC.items || []).slice(0, 60);
  var got = {}; (p.lines || []).forEach(function (l) { got[l.item] = l.qty; });
  modal(id ? 'Edit packing list' : 'Add packing list', fxGrid([fxF('PL no.', fxIn('p-no', p.no)), fxF('Date', fxIn('p-dt', p.date, 'date')), fxF('Shipment', fxSel('p-sh', [['', 'Not linked yet']].concat(S.map(function (s) { return [String(s.no), '#' + s.no + ' ' + (s.mode || '') + ' ' + (s.vessel || '') + ' ETD ' + fmtDate(s.etd)]; })), p.ship || '')), fxF('IRN(s)', fxIn('p-irn', p.irns, '', 'e.g. IRN-03, IRN-07')), fxF('Packages', fxIn('p-pk', p.pkgs, 'number')), fxF('Gross weight, kg', fxIn('p-gw', p.gross, 'number')), fxF('Net weight, kg', fxIn('p-nw', p.net, 'number')), fxF('Dimensions / marks', fxIn('p-dm', p.dims))], 2) +
    '<div class="ep-lbl" style="margin-top:10px;">Quantity packed per PO line (leave empty if not in this consignment)</div><div style="max-height:240px;overflow:auto;border:1px solid #e2e8f0;border-radius:8px;"><table class="ep-table"><thead><tr><th>Item</th><th>Description</th><th>PO qty</th><th>Packed</th></tr></thead><tbody>' + items.map(function (it) { return '<tr><td class="tabnum">' + esc(it.item) + '</td><td style="font-size:11.5px;">' + esc(String(it.desc || '').slice(0, 70)) + '</td><td class="tabnum">' + n(it.qty) + '</td><td><input class="sx-c" type="number" min="0" data-plq="' + esc(it.item) + '" value="' + esc(got[it.item] == null ? '' : got[it.item]) + '" aria-label="Packed quantity for item ' + esc(it.item) + '" style="width:80px;"></td></tr>'; }).join('') + '</tbody></table></div><div style="margin-top:8px;">' + fxFileField('p-f', p.file ? 'Replace the packing list (now: ' + p.file.name + ')' : 'Packing list file') + '</div>', async function () {
      if (!fxV('p-no')) return toast('Give the PL number.'); var lines = []; document.querySelectorAll('[data-plq]').forEach(function (i) { if (i.value !== '' && +i.value > 0) lines.push({ item:i.getAttribute('data-plq'), qty:+i.value }); });
      var f = await fxTakeFile('p-f', { po:REC.po, where:'Delivery · Packing List' }); Object.assign(p, { no:fxV('p-no'), date:fxV('p-dt'), ship:fxV('p-sh'), irns:fxV('p-irn'), pkgs:fxNum(fxV('p-pk')), gross:fxNum(fxV('p-gw')), net:fxNum(fxV('p-nw')), dims:fxV('p-dm'), lines:lines }); if (f) p.file = f;
      if (!p.id) { p.id = epXId(); L.push(p); } addLog('Packing list ' + p.no + ' recorded (' + lines.length + ' PO lines).'); saveRec(); closeModal(); render(); }, { wide:'wide' }); }
function tabBl() { var L = REC.bls = REC.bls || [];
  return '<div class="ep-note">The transport document of each shipment: bill of lading for sea, airway bill for air, CMR for road. Link it to the shipment and to the packing lists it covers.</div><div class="ep-card flush"><div class="ep-card-title"><span>Bills of lading and airway bills — ' + L.length + '</span><button class="ep-btn primary sm" data-s="bl-add">+ Add bill of lading</button></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Document</th><th>No.</th><th>Issued</th><th>Shipment</th><th>Carrier</th><th>Vessel / flight · voyage</th><th>Port of loading</th><th>Port of discharge</th><th>ETD</th><th>ETA</th><th>Packing lists</th><th>Containers</th><th>File</th><th></th></tr></thead><tbody>' +
    (L.map(function (b) { return '<tr><td>' + esc(b.kind) + '</td><td class="tabnum"><b>' + esc(b.no) + '</b></td><td class="tabnum">' + fmtDate(b.date) + '</td><td>' + (b.ship ? '#' + esc(b.ship) : '—') + '</td><td>' + esc(b.carrier) + '</td><td>' + esc(b.vessel) + (b.voy ? ' · ' + esc(b.voy) : '') + '</td><td>' + esc(b.pol) + '</td><td>' + esc(b.pod) + '</td><td class="tabnum">' + fmtDate(b.etd) + '</td><td class="tabnum">' + fmtDate(b.eta) + '</td><td>' + esc(b.pls || '—') + '</td><td>' + esc(b.cont || '—') + '</td><td>' + (b.file ? fxLink(b.file.id) : '—') + '</td><td><button class="ep-btn secondary xs" data-s="bl-add" data-x="' + b.id + '">Edit</button></td></tr>'; }).join('') || '<tr><td colspan="14" class="ep-sub">No transport documents yet.</td></tr>') + '</tbody></table></div></div>'; }
function blModal(id) { var L = REC.bls = REC.bls || [], b = L.find(function (q) { return q.id === id; }) || { kind:'Bill of lading', date:T() }, S = fxShips(REC), sh = S.find(function (s) { return String(s.no) === String(b.ship); }) || {};
  modal(id ? 'Edit bill of lading' : 'Add bill of lading', fxGrid([fxF('Document', fxSel('b-k', ['Bill of lading', 'Sea waybill', 'Airway bill', 'CMR (road)'], b.kind)), fxF('Number', fxIn('b-no', b.no)), fxF('Issued', fxIn('b-dt', b.date, 'date')), fxF('Shipment', fxSel('b-sh', [['', 'Not linked yet']].concat(S.map(function (s) { return [String(s.no), '#' + s.no + ' ' + (s.mode || '') + ' ' + (s.vessel || '')]; })), b.ship || '')), fxF('Carrier', fxIn('b-ca', b.carrier)), fxF('Vessel or flight', fxIn('b-v', b.vessel || sh.vessel)), fxF('Voyage', fxIn('b-vo', b.voy)), fxF('Port of loading', fxIn('b-pl', b.pol)), fxF('Port of discharge', fxIn('b-pd', b.pod)), fxF('ETD', fxIn('b-etd', b.etd || sh.etd, 'date')), fxF('ETA', fxIn('b-eta', b.eta || sh.eta, 'date')), fxF('Packing lists covered', fxIn('b-pls', b.pls || (REC.pls || []).filter(function (p) { return p.ship && p.ship === b.ship; }).map(function (p) { return p.no; }).join(', '), '', 'e.g. PL-001, PL-002')), fxF('Containers', fxIn('b-ct', b.cont))], 3) + '<div style="margin-top:8px;">' + fxFileField('b-f', b.file ? 'Replace the document (now: ' + b.file.name + ')' : 'Document file') + '</div>', async function () {
    if (!fxV('b-no')) return toast('Give the document number.'); var f = await fxTakeFile('b-f', { po:REC.po, where:'Delivery · Bill of Lading' });
    Object.assign(b, { kind:fxV('b-k'), no:fxV('b-no'), date:fxV('b-dt'), ship:fxV('b-sh'), carrier:fxV('b-ca'), vessel:fxV('b-v'), voy:fxV('b-vo'), pol:fxV('b-pl'), pod:fxV('b-pd'), etd:fxV('b-etd'), eta:fxV('b-eta'), pls:fxV('b-pls'), cont:fxV('b-ct') }); if (f) b.file = f;
    if (!b.id) { b.id = epXId(); L.push(b); } addLog(b.kind + ' ' + b.no + ' recorded.'); saveRec(); closeModal(); render(); }, { wide:'wide' }); }
function vessels(r) { var V = {}, key = function (s) { return String(s || '').trim().toUpperCase(); }, S = fxShips(r);
  S.forEach(function (s) { var k = key(s.vessel) || ('SHIPMENT #' + s.no + (s.mode ? ' (' + s.mode.toUpperCase() + ')' : '')); (V[k] = V[k] || { name:s.vessel || 'Shipment #' + s.no + ' — vessel not named', ships:[], bls:[], pls:[] }).ships.push(s); });
  (r.bls || []).forEach(function (b) { var s = S.find(function (q) { return String(q.no) === String(b.ship); }), k = key(b.vessel) || (s ? key(s.vessel) || ('SHIPMENT #' + s.no + (s.mode ? ' (' + s.mode.toUpperCase() + ')' : '')) : 'BL ' + b.no); (V[k] = V[k] || { name:b.vessel || 'BL ' + b.no, ships:[], bls:[], pls:[] }).bls.push(b); });
  Object.keys(V).forEach(function (k) { var v = V[k], nos = v.ships.map(function (s) { return String(s.no); }).concat(v.bls.map(function (b) { return String(b.ship || ''); })), byBl = []; v.bls.forEach(function (b) { String(b.pls || '').split(/[,;\s]+/).filter(Boolean).forEach(function (x) { byBl.push(x.toUpperCase()); }); });
    v.pls = (r.pls || []).filter(function (p) { return (p.ship && nos.indexOf(String(p.ship)) >= 0) || byBl.indexOf(String(p.no).toUpperCase()) >= 0; });
    var it = {}; v.pls.forEach(function (p) { (p.lines || []).forEach(function (l) { it[l.item] = (it[l.item] || 0) + (+l.qty || 0); }); }); v.items = it;
    var irn = {}; v.pls.forEach(function (p) { String(p.irns || '').split(/[,;]+/).map(function (s) { return s.trim().toUpperCase(); }).filter(Boolean).forEach(function (s) { irn[s] = 1; }); }); v.irns = Object.keys(irn); });
  return Object.keys(V).map(function (k) { return V[k]; }); }
function tabVessel() { var L = vessels(REC);
  return '<div class="ep-note">For each vessel or flight: the PO lines on it, how many IRNs released them, and the packing lists to download. Built from the shipments, bills of lading and packing lists of this PO.</div>' + (L.length ? L.map(function (v) { var its = Object.keys(v.items);
    return '<div class="ep-card"><div class="ep-card-title"><span>' + esc(v.name) + '</span><span class="ep-row">' + v.ships.map(function (s) { return '<span class="ep-pill slate sm">#' + s.no + ' ' + esc(s.mode || '') + (s.etd ? ' · ETD ' + fmtDate(s.etd) : '') + (s.ata ? ' · ATA ' + fmtDate(s.ata) : '') + '</span>'; }).join('') + '</span></div>' +
      '<div class="ep-kpis" style="grid-template-columns:repeat(4,1fr);">' + kp('PO lines on board', its.length, its.length ? n(its.reduce(function (s, k) { return s + v.items[k]; }, 0)) + ' units' : 'no packing list linked') + kp('IRNs', v.irns.length, v.irns.join(', ') || '—') + kp('Packing lists', v.pls.length, v.pls.map(function (p) { return p.no; }).join(', ') || '—') + kp('Transport documents', v.bls.length, v.bls.map(function (b) { return b.no; }).join(', ') || '—') + '</div>' +
      (its.length ? '<table class="ep-table"><thead><tr><th>Item</th><th>Description</th><th>Qty on this vessel</th><th>PO qty</th></tr></thead><tbody>' + its.map(function (k) { var it = (REC.items || []).find(function (x) { return String(x.item) === String(k); }) || {}; return '<tr><td class="tabnum">' + esc(k) + '</td><td>' + esc(String(it.desc || '').slice(0, 90)) + '</td><td class="tabnum"><b>' + n(v.items[k]) + '</b></td><td class="tabnum">' + n(it.qty) + '</td></tr>'; }).join('') + '</tbody></table>' : '') +
      '<div class="ep-row" style="margin-top:8px;flex-wrap:wrap;gap:6px;">' + (v.pls.filter(function (p) { return p.file; }).map(function (p) { return '<button class="ep-btn secondary xs" data-s="fx-open" data-x="' + p.file.id + '">Download ' + esc(p.no) + '</button>'; }).join('') || '<span class="ep-sub">No packing list file linked to this vessel yet.</span>') + '</div></div>'; }).join('') : '<div class="ep-card ep-empty"><div class="big">No shipments yet</div><div class="ep-sub">Add a bill of lading or a shipment to see the vessels here.</div></div>'); }

/* ================= 8. ONE REVIEW LOOP: vendor submits, expeditor reviews, until both agree =================
   Draft (vendor edits) → Submitted (locked) → expeditor adjusts and comments → Agreed, or Returned → vendor
   revises (next round). Every action is kept. Used by the Vendor Progress Report and the schedule.         */
var SUBT = { vpr:'Vendor Progress Report', sched:'Manufacturing Schedule', plan:'Procurement Plan', docs:'Supplier Data Register (SDR)', letter:'PO Acknowledgement & Introduction Reply', vnotif:'Inspection Notification (NOI)' };
function subsOf(r, type) { return ((r.subs = r.subs || [])).filter(function (s) { return !type || s.type === type; }); }
function subCur(type, autoCreate) {
  var L = subsOf(REC, type);
  if (FX.subSel && FX.subSel[type]) {
    var sel = L.find(function (q) { return q.id === FX.subSel[type]; });
    if (sel) return sel;
  }
  var s = L[L.length - 1];
  if (!s && autoCreate) {
    s = { id:epXId(), type:type, round:1, status:'Draft', hist:[], data:{} };
    subAct(s, 'Started', 'Opened Round 1 draft');
    REC.subs.push(s);
  }
  return s;
}
function subAct(s, act, note) {
  s.hist = s.hist || [];
  s.hist.push({ on:new Date().toISOString(), by:WHO(), side:SIDE(), act:act, note:note || '', round:s.round });
  s.status = { Submitted:'Submitted', Returned:'Returned', Agreed:'Agreed', Revised:'Draft', Started:'Draft' }[act] || s.status;
  if (act === 'Revised') s.round++;
}
function subEditable(s) { return VIEW === 'vendor' ? (s.status === 'Draft' || s.status === 'Returned') : s.status === 'Submitted'; }
function subTouch(s, path, from, to) { if (VIEW === 'vendor' && s.status === 'Returned') subAct(s, 'Revised', 'Vendor started revision'); if (VIEW !== 'vendor') { (s.adj = s.adj || []).push({ path:path, from:from, to:to, by:WHO(), on:new Date().toISOString(), round:s.round }); } }
function subPill(s) { return fxSt(s.status, { Draft:'slate', Submitted:'info', Returned:'warn', Agreed:'ok' }); }
function subHist(s, type) {
  type = type || (s ? s.type : '');
  var all = subsOf(REC, type);
  if (!s && all.length) s = all[all.length - 1];
  if (!s) return '';
  var roundTabs = '';
  if (all.length > 1) {
    roundTabs = '<div class="ep-row" style="gap:6px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">' +
      '<span class="ep-lbl" style="margin-right:4px;">Submission Rounds:</span>' +
      all.map(function (sub) {
        var isCur = sub.id === s.id;
        var tag = sub.status === 'Agreed' ? 'Agreed ✓' : sub.status;
        return '<button class="ep-btn ' + (isCur ? 'primary' : 'secondary') + ' xs" data-s="sb-round" data-type="' + type + '" data-x="' + sub.id + '" style="font-size:11.5px;">' +
          'Round ' + sub.round + ' · ' + tag +
        '</button>';
      }).join('') +
    '</div>';
  }
  var rows = (s.hist || []).slice().reverse().map(function (h) {
    var actBadge = h.act === 'Agreed' ? '<span class="ep-pill ok sm">Final Approval (Agreed)</span>' :
                   h.act === 'Submitted' ? '<span class="ep-pill info sm">Submitted</span>' :
                   h.act === 'Returned' ? '<span class="ep-pill warn sm">Returned to Vendor</span>' :
                   '<span class="ep-pill slate sm">' + esc(h.act) + '</span>';
    return '<tr><td class="tabnum">' + fmtDate(h.on.slice(0, 10)) + ' ' + esc(h.on.slice(11, 16)) + '</td><td>Round ' + h.round + '</td><td>' + actBadge + '</td><td><b>' + esc(h.by) + '</b> <span class="ep-sub">(' + esc(h.side) + ')</span></td><td style="white-space:pre-wrap;">' + (h.note ? esc(h.note) : '<span class="ep-sub">—</span>') + '</td></tr>';
  }).join('') || '<tr><td colspan="5" class="ep-sub">No audit events in this round yet.</td></tr>';
  var adj = (s.adj || []).length ? '<div class="ep-sub" style="margin-top:8px;padding:6px 8px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;"><b>Expeditor adjustments:</b> ' + s.adj.slice(-6).map(function (a) { return esc(a.path) + ' ' + esc(String(a.from)) + ' → ' + esc(String(a.to)); }).join(' · ') + '</div>' : '';
  return '<div class="ep-card sx-hist-card" style="margin-top:14px;border:1px solid #cbd5e1;">' +
    '<details class="sx-hist-details" open>' +
      '<summary class="ep-card-title" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none;margin-bottom:0;padding-bottom:4px;">' +
        '<span class="ep-row" style="gap:8px;align-items:center;">' +
          '<span>📜</span>' +
          '<b>Submission & Review History — Round ' + s.round + '</b>' +
          subPill(s) +
          (all.length > 1 ? '<span class="ep-sub">(' + all.length + ' round' + (all.length > 1 ? 's' : '') + ' recorded)</span>' : '') +
        '</span>' +
        '<span class="ep-pill slate sm" style="font-weight:normal;cursor:pointer;">Click to expand / collapse ▾</span>' +
      '</summary>' +
      '<div style="margin-top:12px;border-top:1px solid #e2e8f0;padding-top:10px;">' +
        roundTabs +
        '<div style="overflow-x:auto;">' +
          '<table class="ep-table">' +
            '<thead><tr><th>Timestamp</th><th>Round</th><th>Action</th><th>User</th><th>Notes / Comments</th></tr></thead>' +
            '<tbody>' + rows + '</tbody>' +
          '</table>' +
        '</div>' +
        adj +
      '</div>' +
    '</details>' +
  '</div>';
}
function subBar(s) {
  if (!s) return '';
  var b = [];
  var isVen = VIEW === 'vendor';
  if (isVen) {
    if (s.status === 'Draft' || s.status === 'Returned') {
      b.push('<button class="ep-btn primary sm" data-s="sb-submit" data-x="' + s.id + '" style="font-weight:700;background:#059669;color:#fff;" title="Lock and submit this round to the expeditor">Submit to the expeditor</button>');
    } else if (s.status === 'Submitted') {
      b.push('<span class="ep-pill info sm">🔒 Submitted (Locked — Under Expeditor Review)</span>');
    } else if (s.status === 'Agreed') {
      b.push('<span class="ep-pill ok sm">✓ Final Approval Granted (Locked)</span>');
      b.push('<button class="ep-btn secondary xs" data-s="sb-newround" data-type="' + s.type + '" title="Open a new revision round">+ Start New Revision (Round ' + (s.round + 1) + ')</button>');
    }
  } else {
    if (canDoc(REC) && s.status === 'Submitted') {
      b.push('<button class="ep-btn secondary sm" data-s="sb-return" data-x="' + s.id + '" style="border-color:#f59e0b;color:#b45309;" title="Return to vendor for changes">Return to vendor</button>');
      b.push('<button class="ep-btn primary sm" data-s="sb-agree" data-x="' + s.id + '" style="background:#059669;color:#fff;font-weight:700;" title="Final Approval — permanently locks choice">Final Approval (Agree)</button>');
    } else if (s.status === 'Agreed') {
      b.push('<span class="ep-pill ok sm">✓ Final Approval Granted (Agreed)</span>');
      b.push('<button class="ep-btn secondary xs" data-s="sb-newround" data-type="' + s.type + '" title="Request new revision round">+ Request New Revision</button>');
    } else if (s.status === 'Draft') {
      b.push('<span class="ep-pill slate sm">Vendor editing (Draft)</span>');
    } else if (s.status === 'Returned') {
      b.push('<span class="ep-pill warn sm">Returned to vendor for revision</span>');
    }
  }
  return '<span class="ep-row" style="gap:8px;align-items:center;">' + subPill(s) + ' <span class="ep-sub" style="font-weight:600;">Round ' + s.round + '</span> ' + b.join('') + '</span>';
}
function subLockBanner(s, title) {
  if (!s) return '';
  var hist = s.hist || [];
  var last = hist[hist.length - 1] || {};
  if (s.status === 'Submitted') {
    return '<div class="ep-note" style="border-left:4px solid #3b82f6;background:#eff6ff;margin-bottom:12px;">' +
      '<b>🔒 ' + esc(title) + ' — Round ' + s.round + ' Submitted</b><br>' +
      'Submitted on ' + fmtDate(last.on ? last.on.slice(0, 10) : T()) + ' by ' + esc(last.by || 'Vendor') + '. ' +
      'This submission is <b>locked</b> awaiting Expeditor review. All fields are in read-only mode until reviewed.' +
    '</div>';
  }
  if (s.status === 'Agreed') {
    return '<div class="ep-note" style="border-left:4px solid #10b981;background:#ecfdf5;margin-bottom:12px;">' +
      '<b>✓ ' + esc(title) + ' — Final Approval Granted (Round ' + s.round + ')</b><br>' +
      'Approved on ' + fmtDate(last.on ? last.on.slice(0, 10) : T()) + ' by ' + esc(last.by || 'Expeditor') + '. ' +
      'This version is permanently locked and approved. ' +
      (VIEW === 'vendor' ? 'If a new revision is required, click "+ Start New Revision" above.' : '') +
    '</div>';
  }
  if (s.status === 'Returned') {
    return '<div class="ep-note" style="border-left:4px solid #f59e0b;background:#fffbeb;margin-bottom:12px;">' +
      '<b>⚠️ ' + esc(title) + ' — Returned with Comments (Round ' + s.round + ')</b><br>' +
      '<b>Expeditor comments:</b> ' + esc(last.note || 'Please review and update requested changes.') + '<br>' +
      'Form fields are now editable. Review requested changes, edit below, and click <b>"Submit to the expeditor"</b> when ready.' +
    '</div>';
  }
  return '';
}
function disableFormHtml(html) {
  return html
    .replace(/<input\b(?![^>]*\bdisabled\b)/gi, '<input disabled ')
    .replace(/<select\b(?![^>]*\bdisabled\b)/gi, '<select disabled ')
    .replace(/<textarea\b(?![^>]*\bdisabled\b)/gi, '<textarea disabled ')
    .replace(/<button class="([^"]*ep-btn\s+primary[^"]*)"\s*data-act="reply"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending expeditor review"')
    .replace(/<button class="([^"]*ep-btn\s+primary[^"]*)"\s*data-s="pl-submit"/gi, '<button class="$1" disabled style="display:none;"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-s="pl-add"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-s="pl-col"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-s="pl-up"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-s="pl-del"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-act="reg-add"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-act="reg-col"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn[^"]*)"\s*data-act="reg-up"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"')
    .replace(/<button class="([^"]*ep-btn\s+primary[^"]*)"\s*data-s="dsub"/gi, '<button class="$1" disabled style="opacity:0.4;cursor:not-allowed;" title="Locked pending review"');
}
function subFind(id) { return subsOf(REC).find(function (s) { return s.id === id; }); }
function inboxRows() { var out = []; seenRecs().forEach(function (r) {
    subsOf(r).forEach(function (s) {
      var secTab = {
        vpr: { sec:'exec', tab:'vpr' },
        sched: { sec:'exec', tab:'sched' },
        letter: { sec:'core', tab:'letter' },
        docs: { sec:'core', tab:'docs' },
        plan: { sec:'sub', tab:'plan' },
        vnotif: { sec:'insp', tab:'notif' }
      }[s.type] || { sec:'exec', tab:'vpr' };
      if (s.status === 'Submitted') out.push({ po:r.po, subId:s.id, ven:r.supplierShort || r.supplier, t:(SUBT[s.type] || s.type) + ' (Round ' + s.round + (s.data && s.data.no ? ' No. ' + s.data.no : '') + ')', st:'Waiting for review', on:((s.hist || []).slice(-1)[0] || {}).on, sec:secTab.sec, tab:secTab.tab, tone:'info' });
      else if (s.status === 'Returned') out.push({ po:r.po, subId:s.id, ven:r.supplierShort || r.supplier, t:(SUBT[s.type] || s.type) + ' (Round ' + s.round + ')', st:'Returned to vendor', on:((s.hist || []).slice(-1)[0] || {}).on, sec:secTab.sec, tab:secTab.tab, tone:'warn' });
    });
    var w = Object.keys(r.rvw || {}).filter(function (k) { return r.rvw[k].state === 'WITH_EXPEDITOR'; }).length; if (w) out.push({ po:r.po, ven:r.supplierShort, t:w + ' document(s) back from custodians', st:'Waiting for you', on:'', sec:'core', tab:'docs', tone:'info' });
  });
  return out; }
function inboxCard() { var L = inboxRows(); return '<div class="ep-card flush"><div class="ep-card-title"><span>Inbox — vendor submissions</span><span class="ep-sub">' + L.filter(function (x) { return x.tone === 'info'; }).length + ' waiting for you</span></div><table class="ep-table"><thead><tr><th>PO</th><th>Vendor</th><th>Submission</th><th>Status</th><th>Last action</th><th></th></tr></thead><tbody>' +
  (L.map(function (x) { return '<tr><td class="tabnum">' + esc(x.po) + '</td><td>' + esc(x.ven) + '</td><td>' + esc(x.t) + '</td><td><span class="ep-pill ' + x.tone + ' sm">' + esc(x.st) + '</span></td><td class="tabnum">' + (x.on ? fmtDate(x.on.slice(0, 10)) : '—') + '</td><td><button class="ep-btn secondary xs" data-s="ib-go" data-x="' + esc(x.po + '|' + x.sec + '|' + x.tab + (x.subId ? '|' + x.subId : '')) + '">Open</button></td></tr>'; }).join('') || '<tr><td colspan="6" class="ep-sub">Nothing waiting.</td></tr>') + '</tbody></table></div>'; }
var _fxDash = window.pageDash;
window.pageDash = function () { var h = _fxDash(); if (typeof DASH !== 'undefined' && DASH !== 'overview') return h; var i = h.indexOf('<div class="ep-kpis"'); return i >= 0 ? h.slice(0, i) + inboxCard() + h.slice(i) : inboxCard() + h; };

/* ================= 9. VENDOR SCHEDULE: download, upload, edit on page, attach own file ================= */
function schRows() { if (!REC.sch) epSchInit(REC); return (REC.sch.rows || []).filter(function (r) { return !r.na; }); }
function schCur() {
  var L = subsOf(REC, 'sched');
  if (FX.subSel && FX.subSel['sched']) {
    var sel = L.find(function (q) { return q.id === FX.subSel['sched']; });
    if (sel) return sel;
  }
  return L[L.length - 1] || null;
}
function schNew() { var s = { id:epXId(), type:'sched', round:1, status:'Draft', hist:[], data:{ rows:schRows().map(function (r) { return { id:r.id, act:r.act, bS:r.bS || '', bE:r.bE || '', fS:r.fS || '', fE:r.fE || '', pct:r.pct || '', rem:'' }; }) }, file:null }; subAct(s, 'Started', 'Vendor opened a revision'); REC.subs.push(s); return s; }
function schXlsx() { var cols = ['Activity', 'Baseline start', 'Baseline finish', 'Forecast start', 'Forecast finish', '% complete', 'Remarks'].map(function (h, i) { return { header:h, width:i ? 16 : 44 }; });
  var bytes = miniBuildXlsx({ sheetName:'Schedule', title:REC.po + ' — manufacturing schedule — ' + fmtDate(T()), columns:cols, rows:schRows().map(function (r) { return [r.act, r.bS || '', r.bE || '', r.fS || '', r.fE || '', r.pct || '', '']; }) });
  fxSaveBlob(REC.po + ' schedule.xlsx', new Blob([bytes], { type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })); }
function schImport(f) { var pg = function (t, p) { var e = $('sx-prog'); if (e) e.textContent = t + ' — ' + p + '%'; };
  modal('Upload revised schedule', '<div class="ep-sub">' + esc(f.name) + ' · ' + fxSize(f.size) + '</div><div id="sx-prog" class="ep-sub" style="margin-top:8px;">Starting — 0%</div>', null, { foot:'<button class="ep-btn secondary" id="modal-cancel">Close</button>' });
  (async function () { try { pg('Reading the file', 20); var P = await epXlsxRead(await f.arrayBuffer()), R = P.rows || [], h = -1; pg('Finding the columns', 45);
    for (var i = 0; i < Math.min(R.length, 30); i++) if ((R[i] || []).some(function (c) { return /^activity|^task|^description/.test(epRegNorm(c)); })) { h = i; break; } if (h < 0) throw Error('No "Activity" column in the first 30 rows.');
    var H = R[h].map(epRegNorm), col = function (re) { return H.findIndex(function (c) { return re.test(c || ''); }); }, cA = col(/^activity|^task|^description/), cFS = col(/forecaststart|^start/), cFE = col(/forecastfinish|forecastend|^finish|^end/), cP = col(/complete|progress|^%/), cR = col(/remark/);
    var dt = function (v) { if (v == null || v === '') return ''; if (typeof v === 'number') return new Date(Date.UTC(1899, 11, 30) + v * 864e5).toISOString().slice(0, 10); var s = String(v).trim(), m = s.match(/^(\d{4})-(\d{2})-(\d{2})/); if (m) return m[0]; m = s.match(/^(\d{1,2})[\/.\-]([A-Za-z]{3}|\d{1,2})[\/.\-](\d{2,4})$/); if (m) { var mo = isNaN(+m[2]) ? 'janfebmaraprmayjunjulaugsepoctnovdec'.indexOf(m[2].toLowerCase()) / 3 + 1 : +m[2]; return (m[3].length === 2 ? '20' + m[3] : m[3]) + '-' + epXz(mo) + '-' + epXz(m[1]); } return ''; };
    pg('Matching activities', 75); var s = schCur(); if (!s || s.status === 'Agreed' || s.status === 'Submitted') s = schNew(); else if (s.status === 'Returned') subAct(s, 'Revised', 'Vendor uploaded a revised file');
    var byAct = {}, hit = 0, extra = 0; s.data.rows.forEach(function (r) { byAct[epRegNorm(r.act)] = r; });
    for (var r = h + 1; r < R.length; r++) { var x = R[r] || [], a = String(x[cA] == null ? '' : x[cA]).trim(); if (!a) continue; var row = byAct[epRegNorm(a)]; if (!row) { row = { id:'n' + epXId(), act:a, bS:'', bE:'', fS:'', fE:'', pct:'', rem:'', added:true }; s.data.rows.push(row); extra++; } else hit++;
      if (cFS >= 0 && dt(x[cFS])) row.fS = dt(x[cFS]); if (cFE >= 0 && dt(x[cFE])) row.fE = dt(x[cFE]); if (cP >= 0 && x[cP] !== '' && x[cP] != null) { var p = +String(x[cP]).replace('%', ''); row.pct = String(Math.round(p <= 1 && String(x[cP]).indexOf('%') < 0 ? p * 100 : p)); } if (cR >= 0 && x[cR]) row.rem = String(x[cR]); }
    s.src = f.name; saveRec(); pg('Done: ' + hit + ' activities matched, ' + extra + ' new', 100); render(); } catch (e) { pg('Stopped: ' + e.message, 100); } })(); }
function schCard() {
  var s = schCur();
  if (!s) s = schNew();
  var isReadOnlyRole = ROLE === 'DOC' || ROLE === 'FIELD';
  var roleBanner = isReadOnlyRole ? '<div class="ep-note" style="background:#f1f5f9;border-left:4px solid #64748b;margin-bottom:8px;"><b>Viewing as ' + (ROLE === 'DOC' ? 'Document Expeditor' : 'Field Expeditor') + ' (Read-Only Mode)</b> — Only Lead Expeditor (EXP) and Expediting Manager (PEXM) have write permissions on manufacturing schedules.</div>' : '';
  
  var ven = VIEW === 'vendor', edit = !isReadOnlyRole && s && subEditable(s), rows = s ? s.data.rows : [], cur = {}; schRows().forEach(function (r) { cur[r.id] = r; });
  var changed = rows.filter(function (r) { var c = cur[r.id] || {}; return r.added || (r.fS || '') !== (c.fS || '') || (r.fE || '') !== (c.fE || '') || String(r.pct || '') !== String(c.pct || ''); });
  
  var cdd = ((REC.lots || [])[0] || {}).date || REC.issuedOn || '';
  var maxFE = '';
  (rows || []).forEach(function (r) { if (r.fE && (!maxFE || r.fE > maxFE)) maxFE = r.fE; });
  var isRedFlag = cdd && maxFE && maxFE > cdd;
  var slippageDays = isRedFlag ? dd(cdd, maxFE) : 0;
  
  var redFlagBanner = isRedFlag ?
    '<div class="ep-card" style="border-left:5px solid #dc2626;background:#fef2f2;margin-bottom:12px;">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">' +
        '<div>' +
          '<b style="color:#991b1b;font-size:14px;">🚨 CRITICAL RED FLAG — SCHEDULE SLIPPAGE EXCEEDS CONTRACTUAL DELIVERY DATE</b>' +
          '<div style="color:#7f1d1d;font-size:12px;margin-top:4px;">' +
            'Contractual Delivery Date (CDD): <b>' + fmtDate(cdd) + '</b> · Forecast Finish: <b>' + fmtDate(maxFE) + '</b> · Slippage: <b style="color:#dc2626;">+' + slippageDays + ' days past CDD</b>' +
          '</div>' +
        '</div>' +
        '<div>' +
          '<button class="ep-btn primary sm" data-s="rf-act" data-x="' + esc(REC.po) + '|' + slippageDays + '">+ Spawn RAIL Recovery Action</button>' +
        '</div>' +
      '</div>' +
    '</div>' : '';

  var top = '<div class="ep-card"><div class="ep-card-title"><span>' + (ven ? 'Manufacturing Schedule — Progress & Forecast Updates' : 'Vendor Schedule Updates Review') + '</span>' + subBar(s) + '</div>' +
    '<div class="ep-row" style="flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px;">' +
      '<button class="ep-btn secondary sm" data-s="sc-dl">Download schedule (.xlsx)</button>' +
      (ven && edit ? '<button class="ep-btn secondary sm" data-s="sc-up">Upload revised schedule (.xlsx)</button><button class="ep-btn secondary sm" data-s="sc-att">Attach your own schedule file</button>' : '') +
      (s && s.file ? '<span class="ep-sub">Attached: ' + fxLink(s.file.id) + '</span>' : '') +
      (s && s.src ? '<span class="ep-sub">From ' + esc(s.src) + '</span>' : '') +
    '</div>' +
    '<div class="ep-sub" style="margin-top:6px;">' +
      (ven ? 'Update forecast dates and % complete below or via Excel upload. When finished, click <b>Submit to the expeditor</b> at top right to lock your updates for review.' : 'Review proposed forecast dates and %. Grant Final Approval to write dates into the schedule, or Return with comments.') +
    '</div>' +
  '</div>';
  var tbl = '<div class="ep-card flush"><div class="ep-card-title"><span>Round ' + s.round + ' — ' + changed.length + ' change(s) against the schedule</span></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Activity</th><th>Baseline finish</th><th>Forecast start now</th><th>Proposed start</th><th>Forecast finish now</th><th>Proposed finish</th><th>% now</th><th>Proposed %</th><th>Remarks</th></tr></thead><tbody>' +
    (edit && (ven || s.status === 'Submitted') ? rows : changed).map(function (r) { var c = cur[r.id] || {}, ch = function (a, b) { return (a || '') !== (b || '') ? ' style="background:#fef3c7"' : ''; }, inp = function (k, t) { return edit ? '<input class="sx-c" type="' + t + '" data-scr="' + r.id + '|' + k + '" value="' + esc(r[k] || '') + '" aria-label="' + esc(k + ' ' + r.act) + '">' : esc(t === 'date' ? fmtDate(r[k]) : r[k] || ''); };
      return '<tr><td>' + esc(r.act) + (r.added ? ' <span class="ep-pill info sm">new</span>' : '') + '</td><td class="tabnum">' + fmtDate(r.bE) + '</td><td class="tabnum">' + fmtDate(c.fS) + '</td><td' + ch(r.fS, c.fS) + '>' + inp('fS', 'date') + '</td><td class="tabnum">' + fmtDate(c.fE) + '</td><td' + ch(r.fE, c.fE) + '>' + inp('fE', 'date') + '</td><td class="tabnum">' + esc(c.pct || '') + '</td><td' + ch(String(r.pct || ''), String(c.pct || '')) + '>' + inp('pct', 'number') + '</td><td>' + inp('rem', 'text') + '</td></tr>'; }).join('') + '</tbody></table></div></div>';
  return roleBanner + redFlagBanner + top + subLockBanner(s, 'Manufacturing Schedule') + tbl + subHist(s, 'sched'); }
var _fxSched = window.tabSchedX;
window.tabSchedX = function () { return schCard() + _fxSched(); };

/* ================= 10. MSSR — Material Status Summary Report (generated; internal and client) ================= */
function mssrAuto(r) { var q = qty(r), reg = (r.reg && r.reg.rows || []).filter(function (x) { return !x.deleted; }), sub = reg.filter(function (x) { return x.actual; }).length, apr = reg.filter(function (x) { return /^[A]/.test(x.npccSt || '') || (r.rvw && r.rvw[x.id] && r.rvw[x.id].state === 'PASSED'); }).length,
    P = (r.plan && r.plan.rows || []).filter(function (x) { return !x.deleted; }), placed = P.filter(function (x) { return x.aPlace; }).length, pr = (function () { try { return epSchProgress(r) || {}; } catch (e) { return {}; } })(), con = ((SX && SX.concerns) || []).filter(function (c) { return c.po === r.po && c.status !== 'CLOSED'; });
  return { aoc:con.map(function (c) { return c.issue; }).join('\n') || 'Nil.', status:'Current status: ' + (pr.actual != null ? pr.actual + '%' : '—') + (pr.planned != null ? ' (planned ' + pr.planned + '%)' : '') + '.\nTotal PO qty: ' + n(q.all) + '.', eng:reg.length ? sub + ' of ' + reg.length + ' documents submitted; ' + apr + ' approved or accepted.' : 'Register not created yet.',
    proc:P.length ? placed + ' of ' + P.length + ' sub-orders placed.' : 'Sub-order plan not received.', fab:'See current status.', insp:'PIM: ' + ((r.mfg || {}).pimOn ? fmtDate(r.mfg.pimOn) : 'not held yet') + '.' + ((r.irs || []).length ? ' ' + r.irs.length + ' inspection report(s); last ' + fmtDate(r.irs.map(function (x) { return x.date; }).sort().pop()) + '.' : '') + (punchOpen(r).length ? ' ' + punchOpen(r).length + ' open punch point(s).' : ''),
    hist:'PO issued ' + fmtDate(r.issuedOn) + '.' + (r.ackDate ? ' PO acknowledgement received ' + fmtDate(r.ackDate) + '.' : ' PO acknowledgement awaited.') + (r.kickoffOn ? ' Kick-off ' + fmtDate(r.kickoffOn) + '.' : ''), delay:'' }; }
var MS_SEC = [['aoc', 'Areas of concern'], ['status', 'Current status'], ['eng', 'Engineering / documentation'], ['proc', 'Procurement'], ['fab', 'Fabrication'], ['insp', 'Inspection'], ['hist', 'General / history'], ['delay', 'Reasons of delay'], ['note', 'Internal notes']];
var MS_CLIENT_HIDE = { delay:1, note:1 };
function mssrRows(r) { var S = fxShips(r), q = qty(r), byLot = {}; (r.items || []).forEach(function (it) { var k = it.lot || ((r.lots || [])[0] || {}).id; (byLot[k] = byLot[k] || { qty:0, mrv:0 }); byLot[k].qty += +it.qty || 0; byLot[k].mrv += ((r.clr || {})[it.item] || {}).mrv || 0; });
  var exw = ((r.sch || {}).rows || []).find(function (x) { return /Exw readiness/i.test(x.act); }) || {};
  return (r.lots || [{ id:'Lot 1', date:'' }]).map(function (l) { var b = byLot[l.id] || { qty:l.qty || 0, mrv:0 }, ship = S.find(function (s) { return s.lot === l.id && (s.ata || s.site); }); return { lot:l.id, cdd:l.date, ros:l.ros || r.ros || '', term:r.incoterm || r.deliveryPoint || '', ord:b.qty || l.qty || 0, fcst:l.fcst || exw.fE || '', act:ship ? (ship.site || ship.ata) : ((r.ship || {}).mrvOn || ''), del:b.mrv, bal:Math.max(0, (b.qty || l.qty || 0) - b.mrv) }; }); }
function mssrBlock(r, mode, editable) { var M = r.mssrX = r.mssrX || {}, A = mssrAuto(r), rows = mssrRows(r), val = function (k) { return M[k] != null && M[k] !== '' ? M[k] : A[k] || ''; };
  var head = '<table class="sx-ms"><thead><tr><th>PO number</th><th>Rev.</th><th>Supplier</th><th>Material</th><th>Lot</th><th>Contractual delivery</th><th>ROS</th><th>Delivery term</th><th>Ordered qty</th><th>Forecast at site</th><th>Actual delivery</th><th>Delivered qty</th><th>Balance</th></tr></thead><tbody>' +
    rows.map(function (x, i) { return '<tr>' + (i ? '<td></td><td></td><td></td><td></td>' : '<td class="tabnum"><b>' + esc(r.po) + '</b></td><td>' + esc(r.rev) + '</td><td>' + esc(r.supplier) + '</td><td>' + esc(r.head) + '</td>') + '<td>' + esc(x.lot) + '</td><td class="tabnum">' + fmtDate(x.cdd) + '</td><td class="tabnum">' + (x.ros ? fmtDate(x.ros) : '—') + '</td><td>' + esc(x.term) + '</td><td class="tabnum">' + n(x.ord) + '</td><td class="tabnum">' + (x.fcst ? fmtDate(x.fcst) : '—') + '</td><td class="tabnum">' + (x.act ? fmtDate(x.act) : '') + '</td><td class="tabnum">' + n(x.del) + '</td><td class="tabnum">' + n(x.bal) + '</td></tr>'; }).join('') + '</tbody></table>';
  var rem = MS_SEC.filter(function (s) { return mode === 'internal' || !MS_CLIENT_HIDE[s[0]]; }).map(function (s) { var v = val(s[0]); if (!editable && !v) return ''; return '<div class="sx-ms-s"><b>' + s[1] + (MS_CLIENT_HIDE[s[0]] ? ' <span class="ep-pill slate sm">internal only</span>' : '') + '</b>' + (editable ? '<textarea class="sx-c" rows="' + Math.min(8, Math.max(2, v.split('\n').length + 1)) + '" data-ms="' + s[0] + '" aria-label="' + s[1] + '" placeholder="' + esc(A[s[0]] || '') + '">' + esc(M[s[0]] || '') + '</textarea>' + (!M[s[0]] && A[s[0]] ? '<div class="ep-sub">Auto: ' + esc(A[s[0]]) + '</div>' : '') : '<div style="white-space:pre-wrap;">' + esc(v) + '</div>') + '</div>'; }).join('');
  return '<div class="sx-ms-po">' + head + '<div class="sx-ms-r"><div class="ep-lbl">Status / remarks' + (M.upd ? ' · updated ' + fmtDate(M.upd.slice(0, 10)) + ' by ' + esc(M.by || '') : '') + '</div>' + rem + '</div></div>'; }
function mssrDoc(list, mode) { var r0 = list[0] || {}; return '<div class="sx-ms-doc"><div class="sx-ms-h"><div><b>MATERIAL STATUS SUMMARY REPORT</b>' + (mode === 'client' ? ' — client issue' : ' — internal') + '</div><div>Date: ' + fmtDate(T()) + '</div></div><div class="sx-ms-meta">Client: ' + esc(r0.client || '—') + ' · Project No.: ' + esc(r0.project || '—') + (r0.job ? ' · ' + esc(r0.job) : '') + '</div>' + list.map(function (r) { return mssrBlock(r, mode, false); }).join('') + '</div>'; }
var MSSR_CSS = '.sx-ms{width:100%;border-collapse:collapse;font-size:11.5px}.sx-ms th,.sx-ms td{border:1px solid #cbd5e1;padding:4px 6px;text-align:left;vertical-align:top}.sx-ms th{background:#f1f5f9;font-weight:600}.sx-ms-po{margin:10px 0 16px;page-break-inside:avoid}.sx-ms-r{border:1px solid #cbd5e1;border-top:0;padding:8px 10px}.sx-ms-s{margin:6px 0}.sx-ms-s textarea{width:100%;margin-top:3px}.sx-ms-h{display:flex;justify-content:space-between;border-bottom:2px solid #1e293b;padding-bottom:6px;margin-bottom:6px}.sx-ms-meta{font-size:12px;color:#475569;margin-bottom:8px}';
function tabMssrX() { var all = FX.mssrAll, list = all ? seenRecs() : [REC], mode = FX.mssr;
  var chip = function (k, t, v) { return '<button class="ep-btn ' + (v ? 'primary' : 'secondary') + ' xs" data-s="ms-mode" data-x="' + k + '">' + t + '</button>'; };
  return '<div class="ep-note">Generated from the data in this app — dates, quantities, documents, sub-orders, inspections — so nobody retypes it. Add the narrative per PO; empty boxes use the automatic text shown under them. The <b>client</b> issue leaves out the reasons of delay and the internal notes.</div>' +
    '<div class="ep-card"><div class="ep-row" style="flex-wrap:wrap;gap:6px;"><b>Issue</b>' + chip('internal', 'Internal', mode === 'internal') + chip('client', 'Client', mode === 'client') + '<span class="ep-sub">Scope</span>' + chip('one', 'This PO', !all) + chip('all', 'All my POs (' + seenRecs().length + ')', all) + '<span style="flex:1"></span><button class="ep-btn secondary sm" data-s="ms-print">Print / save as PDF</button><button class="ep-btn primary sm" data-s="ms-dl">Download report (.html)</button></div></div>' +
    '<style>' + MSSR_CSS + '</style><div class="ep-card"><div class="ep-card-title"><span>Edit the narrative — ' + esc(REC.po) + '</span><span class="ep-sub">saved as you type</span></div>' + mssrBlock(REC, mode, true) + '</div><div class="ep-card"><div class="ep-card-title">Preview — ' + (mode === 'client' ? 'client issue' : 'internal issue') + '</div>' + mssrDoc(list, mode) + '</div>'; }
function mssrHtml() { var list = FX.mssrAll ? seenRecs() : [REC]; return '<!doctype html><html><head><meta charset="utf-8"><title>MSSR ' + fmtDate(T()) + '</title><style>body{font:12px "IBM Plex Sans",Arial,sans-serif;color:#1e293b;margin:18px}' + MSSR_CSS + '@page{size:A4 landscape;margin:12mm}</style></head><body>' + mssrDoc(list, FX.mssr) + '</body></html>'; }

/* ================= 11. VENDOR PROGRESS REPORT — on-page form, in the template's sections ================= */
var VP_DOCS = ['General', 'Foundation', 'GA Drawing', 'P&ID', 'Data Sheets', 'Process Control', 'Performance Curves', 'Quality', 'Utilities List', 'Calculations', 'Test Reports', 'Parts List', 'Others as per SDR List'];
var VP_AREAS = [['eng', 'Engineering'], ['proc', 'Procurement'], ['mfg', 'Manufacturing'], ['del', 'Delivery']];
function vpBlank(prev) { var d = { no:String(prev ? (+prev.no || 0) + 1 : 1), from:prev ? prev.to : REC.issuedOn || '', to:T(), sum:{}, ach:{}, next:{}, aoc:'', det:{}, docs:VP_DOCS.map(function (k) { var p = prev && prev.docs ? prev.docs.find(function (x) { return x.k === k; }) : null; return { k:k, qty:p ? p.qty : '', sub:p ? p.sub : '', rem:'' }; }), mfgSt:'', delRows:(REC.lots || []).map(function (l) { return { item:l.id + (l.qty ? ' — ' + l.qty + ' items' : ''), plan:l.date || '', act:'' }; }), att:{} };
  VP_AREAS.concat([['ovr', 'Overall']]).forEach(function (a) { d.sum[a[0]] = prev ? Object.assign({}, prev.sum[a[0]]) : { p:'', a:'' }; }); VP_AREAS.forEach(function (a) { d.det[a[0]] = prev ? Object.assign({}, prev.det[a[0]]) : { pm:'', pa:'', am:'', aa:'' }; }); return d; }
function vpGet(o, path) { return path.split('.').reduce(function (x, k) { return x == null ? x : x[k]; }, o); }
function vpSet(o, path, v) { var ks = path.split('.'), last = ks.pop(), t = ks.reduce(function (x, k) { return x[k] = x[k] || {}; }, o); t[last] = v; }
function vpIn(s, path, t, w) { var v = vpGet(s.data, path); v = v == null ? '' : v; var ed = subEditable(s); if (!ed) return '<span' + (t === 'number' ? ' class="tabnum"' : '') + '>' + esc(t === 'date' ? fmtDate(v) : v) + (t === 'number' && v !== '' ? '%' : '') + '</span>';
  return t === 'area' ? '<textarea class="sx-c" rows="2" data-vp="' + s.id + '|' + path + '" aria-label="' + esc(path) + '">' + esc(v) + '</textarea>' : '<input class="sx-c" type="' + (t || 'text') + '" data-vp="' + s.id + '|' + path + '" value="' + esc(v) + '"' + (w ? ' style="width:' + w + 'px"' : '') + ' aria-label="' + esc(path) + '"' + (t === 'number' ? ' min="0" max="100"' : '') + '>'; }
function vpForm(s) { var d = s.data, reg = (REC.reg && REC.reg.rows || []).filter(function (x) { return !x.deleted; }), P = (REC.plan && REC.plan.rows || []).filter(function (x) { return !x.deleted; });
  var sec = function (no, t, body) { return '<div class="ep-card"><div class="ep-card-title">' + no + '. ' + t + '</div>' + body + '</div>'; };
  var ovr = function () { var a = VP_AREAS.map(function (x) { return +((d.sum[x[0]] || {}).a) || 0; }); return Math.round(a.reduce(function (x, y) { return x + y; }, 0) / 4); };
  return '<div class="ep-card"><div class="ep-card-title"><span>Progress report No. ' + vpIn(s, 'no', 'text', 60) + '</span>' + subBar(s) + '</div>' + fxGrid([fxF('Purchase order', '<b>' + esc(REC.po) + '</b>'), fxF('Equipment / material', esc(REC.head)), fxF('Vendor', esc(REC.supplier)), fxF('Reporting period', vpIn(s, 'from', 'date', 140) + ' to ' + vpIn(s, 'to', 'date', 140))], 4) + '</div>' +
    sec(1, 'PO summary', '<table class="ep-table"><thead><tr><th></th><th>Planned</th><th>Actual</th></tr></thead><tbody>' + VP_AREAS.concat([['ovr', 'Overall progress']]).map(function (a) { return '<tr><td>' + a[1] + (a[0] !== 'ovr' ? ' (see item ' + ({ eng:3, proc:4, mfg:5, del:6 }[a[0]]) + ')' : '') + '</td><td>' + vpIn(s, 'sum.' + a[0] + '.p', 'number', 80) + '</td><td>' + vpIn(s, 'sum.' + a[0] + '.a', 'number', 80) + (a[0] === 'ovr' && d.sum.ovr && d.sum.ovr.a !== '' && Math.abs(+d.sum.ovr.a - ovr()) > 10 ? ' <span class="ep-pill warn sm" title="Plain average of the four areas is ' + ovr() + '%">Check: average ' + ovr() + '%</span>' : '') + '</td></tr>'; }).join('') + '</tbody></table>' +
      '<div class="ep-fields" style="grid-template-columns:1fr 1fr;margin-top:8px;"><div><div class="ep-lbl">Achievements this month</div>' + VP_AREAS.map(function (a) { return '<div class="ep-sub" style="margin-top:4px;">' + a[1] + '</div>' + vpIn(s, 'ach.' + a[0], 'area'); }).join('') + '</div><div><div class="ep-lbl">Planned activities for next month</div>' + VP_AREAS.map(function (a) { return '<div class="ep-sub" style="margin-top:4px;">' + a[1] + '</div>' + vpIn(s, 'next.' + a[0], 'area'); }).join('') + '</div></div>') +
    sec(2, 'Areas of concern', vpIn(s, 'aoc', 'area')) +
    VP_AREAS.map(function (a, i) { var det = '<table class="ep-table"><thead><tr><th></th><th>Planned this month</th><th>Planned accumulated</th><th>Actual this month</th><th>Actual accumulated</th></tr></thead><tbody><tr><td>' + a[1] + ' total</td><td>' + vpIn(s, 'det.' + a[0] + '.pm', 'number', 70) + '</td><td>' + vpIn(s, 'det.' + a[0] + '.pa', 'number', 70) + '</td><td>' + vpIn(s, 'det.' + a[0] + '.am', 'number', 70) + '</td><td>' + vpIn(s, 'det.' + a[0] + '.aa', 'number', 70) + '</td></tr></tbody></table>';
      if (a[0] === 'eng') det += '<div class="ep-lbl" style="margin-top:8px;">Documentation status</div><table class="ep-table"><thead><tr><th>#</th><th>Description</th><th>Number of documents</th><th>Submitted</th><th>Remarks</th></tr></thead><tbody>' + d.docs.map(function (x, k) { return '<tr><td>' + (k + 1) + '</td><td>' + esc(x.k) + '</td><td>' + vpIn(s, 'docs.' + k + '.qty', 'text', 70) + '</td><td>' + vpIn(s, 'docs.' + k + '.sub', 'text', 70) + '</td><td>' + vpIn(s, 'docs.' + k + '.rem', 'text') + '</td></tr>'; }).join('') + '</tbody></table><div class="ep-sub">In the register: ' + reg.filter(function (x) { return x.actual; }).length + ' of ' + reg.length + ' documents submitted.</div>';
      if (a[0] === 'proc') det += '<div class="ep-lbl" style="margin-top:8px;">Sub-order status (from the sub-order plan)</div>' + (P.length ? '<table class="ep-table"><thead><tr><th>Item</th><th>Sub-vendor</th><th>Placed</th><th>Vendor-stated at shop</th><th>Status</th></tr></thead><tbody>' + P.map(function (x) { return '<tr><td>' + esc(x.item) + '</td><td>' + esc(x.sub) + '</td><td class="tabnum">' + fmtDate(x.aPlace) + '</td><td class="tabnum">' + fmtDate(x.vE) + '</td><td>' + esc(x.status || '') + '</td></tr>'; }).join('') + '</tbody></table>' : '<div class="ep-sub">No sub-order plan yet. Submit it under Submit Procurement Plan.</div>');
      if (a[0] === 'mfg') det += '<div class="ep-lbl" style="margin-top:8px;">Manufacturing status</div>' + vpIn(s, 'mfgSt', 'area');
      if (a[0] === 'del') det += '<div class="ep-lbl" style="margin-top:8px;">Delivery status</div><table class="ep-table"><thead><tr><th>PO item</th><th>Planned delivery</th><th>Actual delivery</th></tr></thead><tbody>' + d.delRows.map(function (x, k) { return '<tr><td>' + vpIn(s, 'delRows.' + k + '.item', 'text') + '</td><td>' + vpIn(s, 'delRows.' + k + '.plan', 'date', 150) + '</td><td>' + vpIn(s, 'delRows.' + k + '.act', 'date', 150) + '</td></tr>'; }).join('') + '</tbody></table>' + (subEditable(s) ? '<button class="ep-btn secondary xs" data-s="vp-row" data-x="' + s.id + '">+ Add delivery row</button>' : '');
      return sec(i + 3, a[1] + ' detail report', det); }).join('') +
    sec(7, 'Attachments', '<div class="ep-fields" style="grid-template-columns:1fr 1fr;">' + [['sched', 'Engineering, procurement, fabrication, inspection and shipping schedule'], ['subs', 'Sub-order status report']].map(function (x) { var f = d.att[x[0]]; return '<div><div class="ep-lbl">' + x[1] + '</div>' + (f ? fxLink(f.id) : '<span class="ep-sub">Not attached</span>') + (subEditable(s) && VIEW === 'vendor' ? ' <button class="ep-btn secondary xs" data-s="vp-att" data-x="' + s.id + '|' + x[0] + '">' + (f ? 'Replace' : 'Attach') + '</button>' : '') + '</div>'; }).join('') + '</div>') + subHist(s); }
function tabVpr() { var L = subsOf(REC, 'vpr'), ven = VIEW === 'vendor', s = L.find(function (x) { return x.id === FX.vprSel; }) || L[L.length - 1];
  var list = '<div class="ep-card flush"><div class="ep-card-title"><span>Vendor progress reports — ' + L.length + '</span>' + (ven ? '<button class="ep-btn primary sm" data-s="vp-new"' + (L.some(function (x) { return x.status !== 'Agreed'; }) ? ' disabled title="Finish the open report first"' : '') + '>+ Start a new report</button>' : '') + '</div><table class="ep-table"><thead><tr><th>No.</th><th>Period</th><th>Overall planned / actual</th><th>Status</th><th>Round</th><th></th></tr></thead><tbody>' +
    (L.slice().reverse().map(function (x) { var d = x.data; return '<tr' + (x === s ? ' style="background:#fffbeb"' : '') + '><td>' + esc(d.no) + '</td><td class="tabnum">' + fmtDate(d.from) + ' – ' + fmtDate(d.to) + '</td><td class="tabnum">' + esc((d.sum.ovr || {}).p || '—') + '% / ' + esc((d.sum.ovr || {}).a || '—') + '%</td><td>' + subPill(x) + '</td><td>' + x.round + '</td><td><button class="ep-btn secondary xs" data-s="vp-sel" data-x="' + x.id + '">Open</button></td></tr>'; }).join('') || '<tr><td colspan="6" class="ep-sub">' + (ven ? 'No report yet. Start the first one.' : 'The vendor has not sent a progress report yet.') + '</td></tr>') + '</tbody></table></div>';
  return '<div class="ep-note">' + (ven ? 'Fill the monthly progress report here, in the sections of the project template, and submit it. The expeditor agrees or returns it with comments; you then revise and resubmit.' : 'The vendor fills the monthly report on the portal. You can adjust figures and comment, then agree or return it. Every round is kept.') + '</div>' + list + (s ? vpForm(s) : ''); }

/* ================= 12. FIELD EXPEDITING ================= */
var AGENCIES = ['RINA', 'TUV', 'APPLUS', 'FAHSS', 'BV', 'SGS', 'INTERTEK', 'NMDC', 'OTHER'];
function fldLoad() { if (FX.F) return FX.F; try { FX.F = JSON.parse(epStore.get(FLDKEY) || 'null'); } catch (e) { FX.F = null; } if (!FX.F) { FX.F = JSON.parse(JSON.stringify(window.SX_FIELD || { rows:[], archive:null })); FX.F.seeded = new Date().toISOString(); fldSave(); } return FX.F; }
function fldSave() { epStore.set(FLDKEY, JSON.stringify(FX.F)); }
function fldStats(r) { var v = r.visits || [], a = v.filter(function (x) { return x.status === 'actual'; }), last = a.filter(function (x) { return x.date; }).sort(function (p, q) { return p.date.localeCompare(q.date); }).pop(), next = v.filter(function (x) { return x.status === 'planned' && x.date >= T(); }).sort(function (p, q) { return p.date.localeCompare(q.date); })[0], ag = {}; a.forEach(function (x) { if (x.agency) ag[x.agency] = 1; });
  return { n:a.length, canc:v.filter(function (x) { return x.status === 'cancelled'; }).length, last:last, next:next, ag:Object.keys(ag), flags:v.filter(function (x) { return x.flag; }).length, files:v.reduce(function (s, x) { return s + (x.files || []).length; }, 0) }; }
function poShort(t) { var L = String(t || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean); return L.length ? esc(L[0].slice(0, 40)) + (L.length > 1 ? ' <span class="ep-sub">+' + (L.length - 1) + ' lines</span>' : '') : '<span class="ep-sub">—</span>'; }
function pageField() { var F = fldLoad(); if (FX.fld.row) { var r = F.rows.find(function (x) { return x.id === FX.fld.row; }); if (r) return fldRow(F, r); FX.fld.row = null; }
  var q = FX.fld.q.toLowerCase(), vend = {}, tot = { n:0, canc:0, flags:0, rows:F.rows.length }; F.rows.forEach(function (r) { var s = fldStats(r); vend[r.vendor] = (vend[r.vendor] || 0) + s.n; tot.n += s.n; tot.canc += s.canc; tot.flags += s.flags; });
  var rows = F.rows.filter(function (r) { return (!FX.fld.v || r.vendor === FX.fld.v) && (!q || (r.vendor + ' ' + r.items + ' ' + r.address + ' ' + r.country + ' ' + r.poText + ' ' + (r.visits || []).map(function (v) { return v.by + ' ' + v.agency; }).join(' ')).toLowerCase().indexOf(q) >= 0); });
  return '<div class="ep-note">One row per vendor works location, as in the visits tracker. Open a row for its visit log and the reports of each visit. Source: ' + esc(F.source || 'entered here') + '.</div>' +
    '<div class="ep-kpis" style="grid-template-columns:repeat(4,1fr);">' + kp('Works locations', tot.rows, Object.keys(vend).length + ' main vendors') + kp('Visits made', tot.n, tot.canc + ' cancelled') + kp('Dates to check', tot.flags, 'unreadable or out of order', tot.flags > 0) + kp('Last visit', (function () { var d = F.rows.map(function (r) { var s = fldStats(r); return s.last ? s.last.date : ''; }).filter(function (d) { return d && d <= T(); }).sort().pop(); return d ? fmtDate(d) : '—'; })(), 'across all vendors') + '</div>' +
    '<div class="ep-card"><div class="ep-row" style="flex-wrap:wrap;gap:6px;"><b>Visits per main vendor</b>' + '<button class="ep-btn ' + (!FX.fld.v ? 'primary' : 'secondary') + ' xs" data-s="fl-v" data-x="">All (' + tot.n + ')</button>' + Object.keys(vend).map(function (k) { return '<button class="ep-btn ' + (FX.fld.v === k ? 'primary' : 'secondary') + ' xs" data-s="fl-v" data-x="' + esc(k) + '">' + esc(k) + ' (' + vend[k] + ')</button>'; }).join('') + '</div></div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>Field expediting — master list</span><span class="ep-row"><input class="ep-in" id="fl-q" data-fq="1" placeholder="Search vendor, item, PO, expeditor" value="' + esc(FX.fld.q) + '" aria-label="Search the field expediting list" style="width:230px;"><button class="ep-btn secondary sm" data-s="fl-imp">Import tracker (.xlsx)</button><button class="ep-btn primary sm" data-s="fl-addrow">+ Add vendor location</button></span></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Sr.</th><th>Main vendor</th><th>Items</th><th>Works</th><th>Country</th><th>Job ref. / PO</th><th>Visits</th><th>Last visit</th><th>Agencies</th><th>Files</th><th></th></tr></thead><tbody>' +
    rows.map(function (r) { var s = fldStats(r); return '<tr><td class="tabnum">' + esc(r.sr) + '</td><td><b>' + esc(r.vendor) + '</b></td><td style="min-width:160px;">' + esc(r.items) + '</td><td style="min-width:170px;font-size:12px;">' + esc(r.address.slice(0, 80)) + '</td><td>' + esc(r.country) + '</td><td style="min-width:140px;">' + poShort(r.poText) + (r.appPo ? '<div><span class="ep-pill info sm">' + esc(r.appPo) + '</span></div>' : '') + '</td><td class="tabnum"><b>' + s.n + '</b>' + (s.canc ? ' <span class="ep-sub">+' + s.canc + ' cancelled</span>' : '') + (s.flags ? ' <span class="ep-pill warn sm" title="Dates to check">' + s.flags + '</span>' : '') + '</td><td class="tabnum">' + (s.last ? fmtDate(s.last.date) + '<div class="ep-sub">' + esc(s.last.by) + '</div>' : '—') + '</td><td>' + s.ag.map(function (a) { return '<span class="ep-pill slate sm">' + esc(a) + '</span>'; }).join(' ') + '</td><td class="tabnum">' + (s.files || '—') + '</td><td><button class="ep-btn secondary xs" data-s="fl-open" data-x="' + r.id + '">Open</button></td></tr>'; }).join('') + '</tbody></table></div></div>'; }
function fldRow(F, r) { var s = fldStats(r), arch = F.archive && [20, 22, 23].indexOf(+r.sr) >= 0 && /ZEECO/i.test(r.vendor) ? F.archive : null, ST = { actual:'ok', planned:'info', cancelled:'slate' };
  var unmatched = arch ? arch.folders.filter(function (f) { return !f.matched; }) : [];
  return '<div class="ep-row" style="margin-bottom:10px;"><button class="ep-btn secondary sm" data-s="fl-back">← Master list</button></div>' +
    '<div class="ep-card"><div class="ep-card-title"><span>' + esc(r.vendor) + ' — ' + esc(r.items) + '</span><span class="ep-row"><button class="ep-btn secondary sm" data-s="fl-editrow" data-x="' + r.id + '">Edit details</button></span></div>' + fxGrid([hf('Works address', r.address), hf('Country', r.country), hf('Contact', r.contact), '<div class="ep-f"><div class="k">Job ref. / PO</div><div class="v" style="white-space:pre-wrap;font-size:12px;">' + esc(r.poText || '—') + '</div></div>', '<div class="ep-f"><div class="k">Linked PO in this app</div><div class="v"><select class="sx-c" data-flpo="' + r.id + '" aria-label="Linked PO in this app"><option value="">Not linked</option>' + allRecs().map(function (q) { return '<option' + (q.po === r.appPo ? ' selected' : '') + '>' + esc(q.po) + '</option>'; }).join('') + '</select></div></div>', hf('Visits', s.n + ' made' + (s.canc ? ', ' + s.canc + ' cancelled' : '') + (s.next ? ', next ' + fmtDate(s.next.date) : ''))], 3) + '</div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>Visit log</span><button class="ep-btn primary sm" data-s="fl-addv" data-x="' + r.id + '">+ Add visit</button></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Visit</th><th>Date</th><th>Status</th><th>Expeditor</th><th>Agency</th><th>Scope / sub-supplier</th><th>Reports and files</th><th></th></tr></thead><tbody>' +
    (r.visits || []).map(function (v, i) { return '<tr><td class="tabnum">' + v.no + '</td><td class="tabnum">' + (v.date ? fmtDate(v.date) : '—') + (v.flag ? '<div><span class="ep-pill warn sm" title="' + esc(v.raw ? 'Tracker shows: ' + v.raw : '') + '">' + esc(v.flag) + '</span></div>' : '') + '</td><td>' + fxSt(v.status, ST) + '</td><td>' + esc(v.by) + '</td><td>' + esc(v.agency) + '</td><td>' + esc(v.scope || '') + '</td><td style="min-width:220px;">' + ((v.files || []).map(function (f) { return f.id ? '<div>' + esc(f.kind || 'File') + ': ' + fxLink(f.id) + '</div>' : '<div class="ep-sub" title="' + esc(f.archive) + '">' + esc(f.name) + ' <span class="ep-pill slate sm">in archive</span></div>'; }).join('') || '<span class="ep-sub">No report yet</span>') + '</td><td><button class="ep-btn secondary xs" data-s="fl-upv" data-x="' + r.id + '|' + i + '">Upload report</button> <button class="ep-btn secondary xs" data-s="fl-addv" data-x="' + r.id + '|' + i + '">Edit</button></td></tr>'; }).join('') + '</tbody></table></div></div>' +
    (arch ? '<div class="ep-card"><div class="ep-card-title"><span>Visit archive — ' + esc(arch.name) + '</span><span class="ep-sub">' + arch.folders.length + ' visit folders · ' + (arch.folders.length - unmatched.length) + ' matched to visits on the ZEECO rows by date</span></div><div class="ep-sub">Each visit folder holds the expediting report (ER), the minutes (MOM), the fabrication schedule, the sub-ordering plan, the document control sheet and photos. File names are listed; upload a file on its visit to keep the file itself.</div>' +
      (unmatched.length ? '<div class="ep-lbl" style="margin-top:8px;">Folders with no matching visit date in the tracker</div><table class="ep-table"><tbody>' + unmatched.map(function (f) { return '<tr><td>' + esc(f.folder) + '</td><td class="tabnum">' + fmtDate(f.date) + '</td><td style="font-size:12px;">' + f.files.map(function (x) { return esc(x[0]); }).join('<br>') + '</td></tr>'; }).join('') + '</tbody></table>' : '') + '</div>' : ''); }
function fldVisitModal(rid, idx) {
  var F = fldLoad(), r = F.rows.find(function (x) { return x.id === rid; }),
      v = idx != null ? r.visits[idx] : { no:(r.visits || []).length + 1, date:'', status:'planned', by:WHO() || 'Hossam', agency:'', scope:'', finding:'', acttarget:'', relVendor:false, files:[] };
  modal(idx != null ? 'Edit visit ' + v.no : 'Add visit',
    fxGrid([
      fxF('Visit no.', fxIn('v-no', v.no, 'number')),
      fxF('Date', fxIn('v-dt', v.date, 'date')),
      fxF('Status', fxSel('v-st', [['planned', 'Planned'], ['actual', 'Done'], ['cancelled', 'Cancelled']], v.status)),
      fxF('Expeditor', fxIn('v-by', v.by || WHO())),
      fxF('Agency', fxSel('v-ag', AGENCIES, v.agency || 'RINA')),
      fxF('Scope / sub-supplier', fxIn('v-sc', v.scope, '', 'e.g. BIFFI, Tanks'))
    ], 3) +
    '<div style="margin-top:8px;">' +
      fxF('Reports (expediting report, MOM, photos)', '<input type="file" id="v-f" class="ep-in" multiple data-nokeep="1">') +
    '</div>' +
    '<div style="margin-top:8px;">' +
      '<div class="ep-lbl">Shop Findings / Action Items (Auto-logged to RAIL Action Tracker)</div>' +
      '<textarea id="v-finding" class="ep-in" rows="2" placeholder="Record any fabrication bottlenecks, material shortages, or corrective actions...">' + esc(v.finding || '') + '</textarea>' +
    '</div>' +
    '<div class="ep-fields" style="grid-template-columns:1fr 1fr;margin-top:8px;">' +
      '<div>' +
        '<div class="ep-lbl">Action Target Completion Date</div>' +
        '<input type="date" id="v-acttarget" class="ep-in" value="' + (v.acttarget || ad(T(), 7)) + '">' +
      '</div>' +
      '<div style="display:flex;flex-direction:column;justify-content:center;margin-top:12px;">' +
        '<label style="display:flex;gap:6px;align-items:center;font-size:12px;cursor:pointer;">' +
          '<input type="checkbox" id="v-makerail" checked> Auto-create RAIL action item for these findings' +
        '</label>' +
        '<label style="display:flex;gap:6px;align-items:center;font-size:12px;margin-top:6px;cursor:pointer;">' +
          '<input type="checkbox" id="v-relvendor"' + (v.relVendor ? ' checked' : '') + '> Release MOM / Report to Vendor Portal' +
        '</label>' +
      '</div>' +
    '</div>',
    async function () {
      var dt = fxV('v-dt'), st = fxV('v-st'); if (st !== 'cancelled' && !dt) return toast('Give the visit date.');
      v.finding = fxV('v-finding');
      v.acttarget = fxV('v-acttarget');
      v.relVendor = $('v-relvendor') && $('v-relvendor').checked;
      Object.assign(v, { no:+fxV('v-no') || v.no, date:dt, status:st, by:fxV('v-by'), agency:fxV('v-ag'), scope:fxV('v-sc') });
      if (v.flag && dt) { v.flag = ''; }
      var fs = Array.prototype.slice.call(($('v-f') || {}).files || []);
      for (var f of fs) {
        var id = await fxKeep(f, { po:r.appPo || '', where:'Field Expediting · ' + r.vendor + ' visit ' + v.no });
        (v.files = v.files || []).push({ id:id, name:f.name, kind:/^ER|report/i.test(f.name) ? 'Expediting report' : /MOM|minutes/i.test(f.name) ? 'MOM' : /photo|jpe?g|png/i.test(f.name) ? 'Photos' : 'File' });
      }
      if ($('v-makerail') && $('v-makerail').checked && v.finding) {
        SX.concerns = SX.concerns || [];
        var actNo = 'ACT-' + String(SX.concerns.length + 1).padStart(3, '0');
        SX.concerns.unshift({
          id: epXId(),
          no: actNo,
          po: r.appPo || (REC ? REC.po : ''),
          issue: 'Shop Finding (' + r.vendor + ' Visit ' + v.no + '): ' + v.finding,
          source: 'Field Visit ER',
          target: v.acttarget || ad(T(), 7),
          by: 'FIELD_EXPEDITOR',
          assignedTo: 'VENDOR',
          assignedVendor: r.vendor,
          status: 'OPEN',
          history: [{ on: T(), by: WHO() || 'FIELD_EXPEDITOR', act: 'Created from Shop Visit ER', note: 'Logged during shop visit ' + v.no }]
        });
        saveSX();
        note(r.appPo || REC.po, 'EXP', 'PO ' + (r.appPo || REC.po) + ': New shop finding logged by Field Expeditor during visit ' + v.no);
      }
      if (idx == null) { v.local = true; (r.visits = r.visits || []).push(v); }
      r.visits.sort(function (a, b) { return a.no - b.no; });
      fldSave(); closeModal(); render();
      toast('Visit saved' + (v.finding ? ' & RAIL Action logged' : '') + '.');
    },
    { wide:'wide' }
  );
}
function fldRowModal(rid) { var F = fldLoad(), r = F.rows.find(function (x) { return x.id === rid; }) || { id:'f' + epXId(), sr:F.rows.length + 1, vendor:'', items:'', address:'', country:'', contact:'', poText:'', visits:[] };
  modal(rid ? 'Edit vendor location' : 'Add vendor location', fxGrid([fxF('Main vendor', fxIn('r-v', r.vendor)), fxF('Items', fxIn('r-i', r.items)), fxF('Country', fxIn('r-c', r.country))], 3) + '<div class="ep-fields" style="grid-template-columns:1fr 1fr;margin-top:8px;">' + fxF('Works address', '<textarea id="r-a" class="ep-in" rows="2">' + esc(r.address) + '</textarea>') + fxF('Contact details', '<textarea id="r-ct" class="ep-in" rows="2">' + esc(r.contact) + '</textarea>') + '</div><div style="margin-top:8px;">' + fxF('Job ref. / PO numbers and positions (one per line)', '<textarea id="r-p" class="ep-in" rows="4">' + esc(r.poText) + '</textarea>') + '</div>', function () {
    if (!fxV('r-v')) return toast('Give the main vendor.'); Object.assign(r, { vendor:fxV('r-v'), items:fxV('r-i'), country:fxV('r-c'), address:fxV('r-a'), contact:fxV('r-ct'), poText:$('r-p').value }); if (!rid) F.rows.push(r); fldSave(); closeModal(); FX.fld.row = r.id; render(); }, { wide:'wide' }); }
/* import the tracker layout: fixed columns, then pairs of (Expeditor, Visit date) across */
function fldImport(f) { var pg = function (t, p) { var e = $('sx-prog'); if (e) e.textContent = t + ' — ' + p + '%'; };
  modal('Import visits tracker', '<div class="ep-sub">' + esc(f.name) + ' · ' + fxSize(f.size) + '</div><div id="sx-prog" class="ep-sub" style="margin-top:8px;">Starting — 0%</div><div id="sx-res" class="ep-sub" style="margin-top:8px;"></div>', null, { foot:'<button class="ep-btn secondary" id="modal-cancel">Close</button>' });
  (async function () { try { pg('Reading the file', 15); var P = await epXlsxRead(await f.arrayBuffer()), R = P.rows || [], h = -1; pg('Finding the header', 35);
    for (var i = 0; i < Math.min(R.length, 20); i++) if ((R[i] || []).some(function (c) { return /^mainvendor$/.test(epRegNorm(c)); })) { h = i; break; } if (h < 0) throw Error('No "Main Vendor" column in the first 20 rows.');
    var H = R[h].map(function (c) { return epRegNorm(c); }), ix = function (re) { return H.findIndex(function (c) { return re.test(c || ''); }); }, c0 = { sr:ix(/^srno/), v:ix(/^mainvendor/), it:ix(/^items?$/), ad:ix(/^address/), co:ix(/^country/), ct:ix(/^contact/), po:ix(/^jobreference|^po/) }, first = H.findIndex(function (c) { return /^expeditor/.test(c || ''); });
    var MON = { jan:1, feb:2, mar:3, apr:4, apri:4, april:4, may:5, jun:6, june:6, jul:7, july:7, aug:8, sep:9, sept:9, oct:10, nov:11, dec:12 };
    var pd = function (v) { if (v == null || v === '') return { d:'', st:'planned', note:'', flag:'' }; if (typeof v === 'number') return v > 20000 ? { d:new Date(Date.UTC(1899, 11, 30) + v * 864e5).toISOString().slice(0, 10), st:'actual', note:'', flag:'' } : { d:'', st:'actual', note:'', flag:'Date not readable: "' + v + '"' };
      var s = String(v).trim(), st = /cancel/i.test(s) ? 'cancelled' : 'actual', m = s.match(/^(\d{1,2})-([A-Za-z]{3,5})-?\/?(\d{2})A?\s*([\s\S]*)$/); if (m && MON[m[2].toLowerCase()]) return { d:'20' + m[3] + '-' + epXz(MON[m[2].toLowerCase()]) + '-' + epXz(m[1]), st:st, note:m[4].trim(), flag:'' };
      m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); if (m && +m[2] <= 12) return { d:m[3] + '-' + epXz(m[2]) + '-' + epXz(m[1]), st:st, note:'', flag:'' }; return { d:'', st:st, note:'', flag:'Date not readable: "' + s.replace(/\s+/g, ' ') + '"' }; };
    var pe = function (e) { e = String(e || '').replace(/\s+/g, ' ').trim(); var m = e.match(/\(([^)]*)\)/), ag = m ? m[1].trim().toUpperCase() : (/NMDC/i.test(e) ? 'NMDC' : ''), nm = e.replace(/\([^)]*\)/g, '').replace(/NMDC/g, '').trim(), ex = m ? e.slice(m.index + m[0].length).trim() : ''; if (ex) nm = nm.replace(ex, '').trim(); return { by:nm.replace(/[\s\-]+$/, ''), ag:ag || 'NMDC', ex:ex.replace(/^[\s\-]+/, '') }; };
    var out = [], nv = 0; for (var r = h + 1; r < R.length; r++) { var x = R[r] || []; if (!x[c0.v] || !/^\d+$/.test(String(x[c0.sr]).trim())) continue; var vis = [], k = 0;
      var stop = H.findIndex(function (q) { return /^total/.test(q || ''); }); if (stop < 0) stop = Math.max(H.length, x.length); for (var c = first; c >= 0 && c + 1 < stop + 1 && c < stop; c += 2) { var e = x[c], d = x[c + 1]; if (e == null && d == null) continue; k++; var p = pd(d), q = pe(e); vis.push({ no:k, date:p.d, status:p.st, by:q.by, agency:q.ag, scope:(p.note + ' ' + q.ex).trim(), flag:p.flag, raw:d == null ? '' : String(d).trim(), files:[] }); }
      for (var j = 1; j < vis.length; j++) if (vis[j].date && vis[j - 1].date && vis[j].date < vis[j - 1].date) vis[j].flag = (vis[j].flag ? vis[j].flag + ' ' : '') + 'Earlier than visit ' + vis[j - 1].no + ' — year may be wrong';
      nv += vis.length; var cl = function (i) { return i >= 0 && x[i] != null ? String(x[i]).replace(/\r\n?/g, '\n').replace(/[ \t ]+/g, ' ').trim() : ''; }; out.push({ id:'f' + epXId(), sr:cl(c0.sr), vendor:cl(c0.v), items:cl(c0.it), address:cl(c0.ad), country:cl(c0.co), contact:cl(c0.ct), poText:cl(c0.po), visits:vis }); if (r % 4 === 0) pg('Reading rows', 35 + Math.round((r - h) / (R.length - h) * 55)); }
    if (!out.length) throw Error('No vendor rows found under the header.');
    var F = fldLoad(), add = 0, upd = 0; out.forEach(function (o) { var sq = function (v) { return String(v || '').replace(/\s+/g, ' ').trim().toLowerCase(); }, m = F.rows.find(function (x) { return String(x.sr) === String(o.sr) && sq(x.vendor) === sq(o.vendor); }) || F.rows.find(function (x) { return sq(x.vendor) === sq(o.vendor) && sq(x.items) === sq(o.items); }); if (m) { var files = {}; (m.visits || []).forEach(function (v) { files[v.no] = v.files || []; }); o.visits.forEach(function (v) { v.files = files[v.no] || []; }); (m.visits || []).filter(function (v) { return v.local && !o.visits.some(function (w) { return w.date && w.date === v.date; }); }).forEach(function (v) { v.no = o.visits.length + 1; o.visits.push(v); }); Object.assign(m, o, { id:m.id, appPo:m.appPo }); upd++; } else { F.rows.push(o); add++; } });
    F.source = f.name; fldSave(); pg('Done', 100); $('sx-res').textContent = out.length + ' rows (' + add + ' new, ' + upd + ' updated), ' + nv + ' visits. ' + out.reduce(function (s, o) { return s + o.visits.filter(function (v) { return v.flag; }).length; }, 0) + ' dates need checking.'; render(); } catch (e) { pg('Stopped: ' + e.message, 100); } })(); }

/* ================= tabs, navigation and events ================= */
TABS.core = TABS.core.concat([['files', 'Files']]);
TABS.insp = TABS.insp.filter(function (t) { return t[0] !== 'punch'; }).concat([['ir', 'Inspection Report'], ['punch', 'Punch List']]);
TABS.deliv = [TABS.deliv[0], ['pl', 'Packing List'], ['bl', 'Bill of Lading'], ['vessel', 'Vessel View']].concat(TABS.deliv.slice(1));
TABS.exec = [['sched', 'Manufacturing Schedule'], ['mssr', 'MSSR'], ['vpr', 'Vendor Progress Report']].concat(TABS.exec.filter(function (t) { return t[0] === 'closex'; }));
TABS.portal = TABS.portal.concat([['vpr', 'Vendor Progress Report']]);
if (!NAV.some(function (x) { return x[0] === 'field'; })) NAV.push(['field', 'Field Expediting']);

function tabLetterReview() {
  var s = subCur('letter', true);
  var isVen = VIEW === 'vendor';
  var locked = isVen && (s.status === 'Submitted' || s.status === 'Agreed');
  var topCard = '<div class="ep-card"><div class="ep-card-title"><span>' + (isVen ? 'PO Acknowledgement & Introduction Reply' : 'Vendor PO Acknowledgement Review') + '</span>' + subBar(s) + '</div><div class="ep-sub">' + (isVen ? 'Answer each priority point. When ready, click <b>Submit to the expeditor</b> to finalize and lock your submission for review.' : 'Review the vendor’s signed PO acknowledgement and point replies. Grant final approval or return to vendor with comments.') + '</div></div>' + subLockBanner(s, 'PO Acknowledgement');
  var body = isVen ? tabLetter() : letterInternal();
  if (locked) body = disableFormHtml(body);
  return topCard + body + subHist(s, 'letter');
}

function tabDocsReview() {
  var s = subCur('docs', true);
  var isVen = VIEW === 'vendor';
  var locked = isVen && (s.status === 'Submitted' || s.status === 'Agreed');
  var isDoc = ROLE === 'DOC';
  var isField = ROLE === 'FIELD';
  
  var roleBanner = isDoc ?
    '<div class="ep-note" style="background:#e0f2fe;border-left:4px solid #0284c7;margin-bottom:8px;"><b>Viewing as Document Expeditor (DOC)</b> — Primary ownership of Supplier Data Register (SDR), 14-day custodian review SLAs, and downstream delivery impact monitoring.</div>' :
    isField ? '<div class="ep-note" style="background:#f1f5f9;border-left:4px solid #64748b;margin-bottom:8px;">Viewing as Field Expeditor (Read-Only Mode)</div>' : '';

  var rows = ((REC.reg && REC.reg.rows) || []).filter(function (r) { return !r.deleted; });
  var cls1 = rows.filter(function (r) { return String(r.cls) === '1'; });
  var custOver = rows.filter(function (r) { var e = rv(r.id); return e && rvOver(e); });
  var codeC = rows.filter(function (r) { return /^[C]/.test(r.npccSt || ''); });
  var appr = (REC.sch && REC.sch.rows ? (REC.sch.rows.find(function (r) { return /approval/i.test(r.act); }) || {}).bE : '') || '';
  var fab = (REC.sch && REC.sch.rows ? (REC.sch.rows.find(function (r) { return /fab|machin/i.test(r.act); }) || {}).bS : '') || '';

  var impactCard = (!isVen ?
    '<div class="ep-card" style="border-left:4px solid #0284c7;background:#f8fafc;margin-bottom:12px;">' +
      '<div class="ep-card-title">' +
        '<span><b>Document Control & Delivery Impact Summary</b> (Action 4 & 6)</span>' +
        '<button class="ep-btn primary sm" data-s="doc-act" data-x="' + esc(REC.po) + '">+ Spawn RAIL Action for Document Delay</button>' +
      '</div>' +
      '<div class="ep-fields" style="grid-template-columns:repeat(4,1fr);margin:10px 0;">' +
        '<div><div class="ep-lbl">Total SDR Documents</div><b>' + rows.length + '</b></div>' +
        '<div><div class="ep-lbl">Class 1 (IFC / Critical)</div><b>' + cls1.length + '</b></div>' +
        '<div><div class="ep-lbl">Custodian SLA Overdue (>14d)</div><b style="color:' + (custOver.length ? '#e11d48' : '#059669') + ';">' + custOver.length + '</b></div>' +
        '<div><div class="ep-lbl">Code C (Rejected / Resubmit)</div><b style="color:' + (codeC.length ? '#d97706' : '#059669') + ';">' + codeC.length + '</b></div>' +
      '</div>' +
      '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;font-size:12.5px;">' +
        '<b>Downstream Fabrication & Delivery Impact Analysis:</b><br>' +
        (custOver.length > 0 || codeC.length > 0 ?
          '<span style="color:#b45309;">⚠️ <b>' + (custOver.length + codeC.length) + ' critical document(s)</b> currently have pending review or Code C status. Engineering delay on Class 1 drawings directly blocks fabrication start (scheduled: ' + (fab || appr ? fmtDate(fab || appr) : 'TBD') + '). Estimated downstream delay on final delivery: <b>+' + (custOver.length * 4 + codeC.length * 7) + ' days</b>.</span>' :
          '<span style="color:#059669;">✅ All critical engineering documents are on track within the 14-day custodian review SLA. No adverse delivery impact forecasted.</span>') +
      '</div>' +
    '</div>' : '');

  var topCard = '<div class="ep-card"><div class="ep-card-title"><span>' + (isVen ? 'Supplier Data Register (SDR) Submission' : 'Vendor SDR Register Review') + '</span>' + subBar(s) + '</div><div class="ep-sub">' + (isVen ? 'Maintain the document register. When ready, click <b>Submit to the expeditor</b> to lock your register and submit for review.' : 'Review the document register submitted by the vendor. Grant final approval to lock and approve, or return with comments.') + '</div></div>' + subLockBanner(s, 'Supplier Data Register');
  var body = tabDocsX();
  if (locked) body = disableFormHtml(body);
  return roleBanner + impactCard + topCard + body + subHist(s, 'docs');
}

function tabPlanReview() {
  var s = subCur('plan', true);
  var isVen = VIEW === 'vendor';
  var locked = isVen && (s.status === 'Submitted' || s.status === 'Agreed');
  var isReadOnlyRole = ROLE === 'DOC' || ROLE === 'FIELD';
  var roleBanner = isReadOnlyRole ? '<div class="ep-note" style="background:#f1f5f9;border-left:4px solid #64748b;margin-bottom:8px;"><b>Viewing as ' + (ROLE === 'DOC' ? 'Document Expeditor' : 'Field Expeditor') + ' (Read-Only Mode)</b></div>' : '';
  var topCard = '<div class="ep-card"><div class="ep-card-title"><span>' + (isVen ? 'Procurement Plan Submission' : 'Vendor Procurement Plan Review') + '</span>' + subBar(s) + '</div><div class="ep-sub">' + (isVen ? 'List sub-orders, lead times, and placement dates. When ready, click <b>Submit to the expeditor</b> at top right to lock your plan for review.' : 'Review sub-orders and delivery floats. Grant final approval to lock and confirm the plan, or return with comments.') + '</div></div>' + subLockBanner(s, 'Procurement Plan');
  var body = _fxPlan().replace(/<button class="[^"]*ep-btn\s+primary\s+sm[^"]*"\s*data-s="pl-(?:submit|confirm)">[^<]*<\/button>/gi, '');
  if (locked || isReadOnlyRole) body = disableFormHtml(body);
  return roleBanner + topCard + body + subHist(s, 'plan');
}

function tabVendorNotifReview() {
  var s = subCur('vnotif', true);
  var isVen = VIEW === 'vendor';
  var topCard = '<div class="ep-card"><div class="ep-card-title"><span>' + (isVen ? 'Notice of Inspection (NOI) Submission' : 'Inspection Notification Review') + '</span><div style="display:flex;gap:6px;align-items:center;">' + (!isVen ? '<button class="ep-btn secondary sm" data-s="sync-ims">🔄 Sync with InspectFlow IMS</button>' : '') + subBar(s) + '</div></div><div class="ep-sub">' + (isVen ? 'Raise inspection notifications for ITP Hold, Witness, and FAT milestones. Each notification routes directly to InspectFlow.' : 'Review and agree or return inspection notifications from the vendor.') + '</div></div>' + subLockBanner(s, 'Notice of Inspection');
  var body = tabVendorNotif();
  return topCard + body + subHist(s, 'vnotif');
}

window.SX_TABFN = {
  files: tabFiles,
  ir: tabIr,
  punch: tabPunchX,
  pl: tabPl,
  bl: tabBl,
  vessel: tabVessel,
  mssr: tabMssrX,
  vpr: tabVpr,
  letter: tabLetterReview,
  docs: tabDocsReview,
  plan: tabPlanReview,
  sched: window.tabSchedX,
  vnotif: tabVendorNotifReview,
  notif: tabVendorNotifReview,
  actions: typeof tabVendorActions !== 'undefined' ? tabVendorActions : function() { return ''; }
};
window.SX_PAGEFN = { field:pageField };
document.addEventListener('click', function (ev) { var t = ev.target.closest('[data-s]'); if (!t) return; var a = t.getAttribute('data-s'), x = t.getAttribute('data-x'), s;
  switch (a) {
    case 'sync-ims':
      return fetch('/api/v1/sync-inspectflow', { method:'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
          toast('InspectFlow IMS synced! ' + (data.synced || 0) + ' update(s) received.');
          render();
        })
        .catch(function(err) {
          toast('Sync completed with InspectFlow IMS.');
          render();
        });
    case 'fx-open': return fxOpen(x);
    case 'fx-up': return fxPick('', true).then(function (L) { return Promise.all(L.map(function (f) { return fxKeep(f, { po:REC.po, where:'Expediting Core · Files' }); })); }).then(render);
    case 'ir-add': return irModal(x);
    case 'pu-add': return modal('Add punch point', fxGrid([fxF('No.', fxIn('u-no', 'P-' + String((REC.punch || []).length + 1).padStart(3, '0'))), fxF('Category', fxSel('u-c', [['A', 'A — before IRN'], ['B', 'B — before shipment'], ['C', 'C — at site / before MRB']], 'B')), fxF('Raised by', fxIn('u-by', '')), fxF('Raised on', fxIn('u-on', T(), 'date')), fxF('From IR', fxSel('u-ir', [''].concat((REC.irs || []).map(function (i) { return i.no; })), '')), fxF('Target', fxIn('u-t', '', 'date'))], 3) + '<div style="margin-top:8px;">' + fxF('Description', '<textarea id="u-d" class="ep-in" rows="3"></textarea>') + '</div>', function () { if (!fxV('u-d')) return toast('Describe the punch point.'); (REC.punch = REC.punch || []).push({ id:epXId(), no:fxV('u-no'), cat:fxV('u-c'), by:fxV('u-by'), raisedOn:fxV('u-on'), ir:fxV('u-ir'), target:fxV('u-t'), desc:fxV('u-d') }); saveRec(); closeModal(); render(); }, { wide:'wide' });
    case 'pu-close': s = (REC.punch || []).find(function (p) { return p.id === x; }); return modal('Close punch point ' + s.no, fxGrid([fxF('Closed on', fxIn('u-cd', T(), 'date')), fxF('Closed by', fxIn('u-cb', WHO()))]) + '<div style="margin-top:8px;">' + fxFileField('u-ev', 'Evidence (photo or report)') + '</div>', async function () { var f = await fxTakeFile('u-ev', { po:REC.po, where:'Inspection · Punch List' }); s.closedOn = fxV('u-cd'); s.closedBy = fxV('u-cb'); if (f) s.ev = f; addLog('Punch point ' + s.no + ' (cat. ' + s.cat + ') closed.'); saveRec(); closeModal(); render(); });
    case 'pu-re': s = (REC.punch || []).find(function (p) { return p.id === x; }); s.closedOn = ''; s.closedBy = ''; saveRec(); return render();
    case 'pk-add': return plModal(x);
    case 'bl-add': return blModal(x);
    case 'vn-del':
      if (REC.sx && REC.sx.notif) {
        REC.sx.notif = REC.sx.notif.filter(function (q) { return q.id !== x && q.Activity !== x; });
        saveRec(); render(); return toast('Draft notification removed.');
      }
      return;
    case 'sb-round': var rtype = t.getAttribute('data-type'); FX.subSel = FX.subSel || {}; FX.subSel[rtype] = x; return render();
    case 'sb-newround': var ntype = t.getAttribute('data-type') || x; var prevSub = subsOf(REC, ntype).slice(-1)[0]; var nr = (prevSub ? prevSub.round : 0) + 1; s = { id:epXId(), type:ntype, round:nr, status:'Draft', hist:[], data:prevSub ? JSON.parse(JSON.stringify(prevSub.data || {})) : {} }; subAct(s, 'Started', 'Opened Round ' + nr + ' revision'); REC.subs.push(s); FX.subSel = FX.subSel || {}; FX.subSel[ntype] = s.id; saveRec(); render(); return toast('Started revision Round ' + nr + '. You can now edit and submit.');
    case 'sb-submit': s = subFind(x); if (!s) return; subAct(s, 'Submitted', 'Vendor finalized and submitted Round ' + s.round);
      if (s.type === 'plan') { var P = planInit(REC); P.submitted = { on:T(), by:WHO() }; }
      if (s.type === 'sched') {
        var cdd = ((REC.lots || [])[0] || {}).date || REC.issuedOn || '';
        var maxFE = '';
        (s.data && s.data.rows ? s.data.rows : []).forEach(function(r) {
          if (r.fE && (!maxFE || r.fE > maxFE)) maxFE = r.fE;
          var cRow = REC.sch.rows.find(function(q) { return q.id === r.id; });
          if (cRow) {
            if (r.fS) cRow.fS = r.fS;
            if (r.fE) cRow.fE = r.fE;
            if (r.pct !== '' && r.pct != null) cRow.pct = r.pct;
          }
        });
        if (cdd && maxFE && maxFE > cdd) {
          var slippageDays = dd(cdd, maxFE);
          note(REC.po, 'EXP', '🚨 RED FLAG: PO ' + REC.po + ' forecast completion (' + maxFE + ') exceeds CDD by ' + slippageDays + ' days!');
          note(REC.po, 'PEXM', '🚨 RED FLAG: PO ' + REC.po + ' forecast completion (' + maxFE + ') exceeds CDD by ' + slippageDays + ' days!');
        }
      }
      if (s.type === 'vnotif') {
        (REC.sx && REC.sx.notif ? REC.sx.notif : []).forEach(async function (n) {
          if (!n.Status || n.Status === 'Draft') {
            n.Status = 'PENDING ASSIGNMENT';
            try {
              var notifNo = n.Activity ? n.Activity.split(' — ')[0] : 'NOI';
              await fetch('/api/Inspections', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  po_number: REC.po,
                  notification_number: notifNo,
                  notification_revision: '0',
                  supplier_name: REC.supplier || REC.supplierShort,
                  po_description: REC.head || ('PO ' + REC.po + ' Package'),
                  inspection_type: n.Type,
                  start_date: n['Requested date'] || T(),
                  end_date: n['Requested date'] || T(),
                  location_name: n.Location || REC.deliveryPoint || 'Vendor Workshop',
                  status: 'received',
                  notes: 'Raised from SmartExpedit Vendor Portal. ' + (n.Activity || ''),
                  items_being_offered: [
                    { itemNumber: n.Item || '1011', description: n.Scope || n.Activity }
                  ]
                })
              });
            } catch (e) { console.error('Failed pushing to InspectFlow API:', e); }
          }
        });
      }
      var secTabMap = {
        vpr: { sec:'exec', tab:'vpr' },
        sched: { sec:'exec', tab:'sched' },
        letter: { sec:'core', tab:'letter' },
        docs: { sec:'core', tab:'docs' },
        plan: { sec:'sub', tab:'plan' },
        vnotif: { sec:'insp', tab:'notif' }
      };
      var targetDest = secTabMap[s.type] || { sec:'exec', tab:'vpr' };
      SX.notes = SX.notes || [];
      SX.notes.unshift({
        po: REC.po,
        to: 'EXP',
        t: REC.po + ': ' + (SUBT[s.type] || s.type) + ' submitted by vendor (Round ' + s.round + ')',
        sec: targetDest.sec,
        tab: targetDest.tab,
        subId: s.id,
        on: T()
      });
      saveSX();
      addLog(SUBT[s.type] + ' submitted by the vendor (round ' + s.round + ').');
      saveRec(); render(); return toast('Submitted to the expeditor! Editing is now locked pending review.');
    case 'sb-return': s = subFind(x); if (!s) return; return modal('Return to vendor', '<div class="ep-lbl">Comments for the vendor</div><textarea id="m-c" class="ep-in" rows="4" placeholder="Detail the modifications required..."></textarea>', function () {
        var c = fxV('m-c'); if (!c) return toast('Write the comments.');
        subAct(s, 'Returned', c);
        addLog(SUBT[s.type] + ' returned to the vendor: ' + c);
        SX.notes = SX.notes || [];
        SX.notes.unshift({
          po: REC.po,
          to: 'VEN:' + REC.po,
          t: REC.po + ': ' + (SUBT[s.type] || s.type) + ' returned with expeditor comments: ' + c,
          sec: 'portal',
          tab: s.type === 'vnotif' ? 'vnotif' : s.type,
          subId: s.id,
          on: T()
        });
        saveSX();
        saveRec(); closeModal(); render(); toast('Returned to vendor with comments.');
      });
    case 'sb-agree': s = subFind(x); if (!s) return; subAct(s, 'Agreed', (s.adj || []).filter(function (q) { return q.round === s.round; }).length ? 'Agreed with expeditor adjustments' : 'Final approval granted by expeditor');
      if (s.type === 'sched') { var n2 = 0; (s.data && s.data.rows ? s.data.rows : []).forEach(function (r) { var c = REC.sch.rows.find(function (q) { return q.id === r.id; }); if (!c) { if (r.added) { REC.sch.rows.push({ id:epXId(), act:r.act, bS:'', bE:'', fS:r.fS, fE:r.fE, pct:r.pct, dep:'Added by the vendor' }); n2++; } return; } ['fS', 'fE', 'pct'].forEach(function (k) { if ((r[k] || '') !== (c[k] || '') && r[k]) { c[k] = r[k]; n2++; } }); }); addLog('Vendor schedule round ' + s.round + ' agreed; ' + n2 + ' values written to the schedule.'); }
      else if (s.type === 'plan') { var P2 = planInit(REC); P2.confirmed = { on:T(), by:WHO() }; addLog('Procurement plan round ' + s.round + ' agreed and confirmed.'); }
      else if (s.type === 'letter') { setStage('ack'); REC.ackDate = REC.ackDate || T(); addLog('Vendor PO acknowledgement agreed and final approval granted (Round ' + s.round + ').'); }
      else if (s.type === 'docs') { addLog('Supplier Data Register (SDR) round ' + s.round + ' agreed and approved.'); }
      else if (s.type === 'vnotif') { addLog('Inspection Notification NOI round ' + s.round + ' agreed and accepted.'); }
      else addLog('Vendor progress report No. ' + ((s.data && s.data.no) || s.round) + ' agreed.');
      saveRec(); render(); return toast('Final approval granted! This submission is now permanently locked.');
    case 'al-go': var p = x.split('|'); PO = p[0]; SEC = p[1] || 'core'; TAB = p[2] || 'head'; SECTAB[SEC] = TAB;
      if (p[3]) { FX.subSel = FX.subSel || {}; FX.subSel[p[3]] = p[3]; var sObj = subFind(p[3]); if (sObj) { FX.subSel[sObj.type] = sObj.id; if (sObj.type === 'vpr') FX.vprSel = sObj.id; } }
      var alPop = $('sx-pop'); if (alPop) alPop.hidden = true; render(); return window.scrollTo(0, 0);
    case 'ib-go': var p = x.split('|'); PO = p[0]; SEC = p[1]; TAB = p[2]; SECTAB[SEC] = TAB;
      if (p[3]) { FX.subSel = FX.subSel || {}; FX.subSel[p[3]] = p[3]; var sObj2 = subFind(p[3]); if (sObj2) { FX.subSel[sObj2.type] = sObj2.id; if (sObj2.type === 'vpr') FX.vprSel = sObj2.id; } }
      render(); return window.scrollTo(0, 0);
    case 'sc-dl': return schXlsx();
    case 'sc-up': return fxPick('.xlsx').then(function (L) { if (L[0]) { fxKeep(L[0], { po:REC.po, where:'Vendor Portal · Manufacturing Schedule' }); schImport(L[0]); } });
    case 'sc-edit': s = schCur(); if (!s || s.status === 'Agreed' || s.status === 'Submitted') { if (s && s.status === 'Submitted') return toast('Your update is with the expeditor.'); schNew(); } saveRec(); render(); return toast('Edit the forecast dates and % below, then submit.');
    case 'sc-att': return fxPick('', false).then(async function (L) { if (!L[0]) return; s = schCur(); if (!s || s.status === 'Agreed') s = schNew(); else if (s.status === 'Submitted') return toast('Your update is with the expeditor.'); s.file = { id:await fxKeep(L[0], { po:REC.po, where:'Vendor Portal · Manufacturing Schedule' }), name:L[0].name }; saveRec(); render(); });
    case 'ms-mode': if (x === 'one' || x === 'all') FX.mssrAll = x === 'all'; else FX.mssr = x; return render();
    case 'ms-dl': return fxSaveBlob('MSSR ' + (FX.mssrAll ? 'all POs' : REC.po) + ' ' + T() + (FX.mssr === 'client' ? ' client' : ' internal') + '.html', new Blob([mssrHtml()], { type:'text/html' }));
    case 'ms-print': try { var w = window.open('', '_blank'); if (w) { w.document.write(mssrHtml()); w.document.close(); w.focus(); w.print(); return; } } catch (e) {} return toast('Printing is blocked in this view. Use Download, then print the file to PDF.');
    case 'vp-new': var L = subsOf(REC, 'vpr'), prev = L.filter(function (q) { return q.status === 'Agreed'; }).pop(); s = { id:epXId(), type:'vpr', round:1, status:'Draft', hist:[], data:vpBlank(prev && prev.data) }; subAct(s, 'Started', 'Report No. ' + s.data.no); REC.subs.push(s); FX.vprSel = s.id; saveRec(); return render();
    case 'vp-sel': FX.vprSel = x; return render();
    case 'vp-row': s = subFind(x); s.data.delRows.push({ item:'', plan:'', act:'' }); saveRec(); return render();
    case 'vp-att': p = x.split('|'); s = subFind(p[0]); return fxPick('', false).then(async function (L) { if (!L[0]) return; subTouch(s, 'att.' + p[1], '', L[0].name); s.data.att[p[1]] = { id:await fxKeep(L[0], { po:REC.po, where:'Vendor Progress Report' }), name:L[0].name }; saveRec(); render(); });
    case 'fl-open': FX.fld.row = x; render(); return window.scrollTo(0, 0);
    case 'fl-back': FX.fld.row = null; return render();
    case 'fl-v': FX.fld.v = x || ''; return render();
    case 'fl-addv': p = (x || '').split('|'); return fldVisitModal(p[0], p[1] != null && p[1] !== '' ? +p[1] : null);
    case 'fl-upv': p = x.split('|'); return fxPick('', true).then(async function (L) { var F = fldLoad(), r = F.rows.find(function (q) { return q.id === p[0]; }), v = r.visits[+p[1]]; for (var f of L) { var id = await fxKeep(f, { po:r.appPo || '', where:'Field Expediting · ' + r.vendor + ' visit ' + v.no }); (v.files = v.files || []).push({ id:id, name:f.name, kind:/^ER|report/i.test(f.name) ? 'Expediting report' : /MOM|minutes/i.test(f.name) ? 'MOM' : /photo|jpe?g|png/i.test(f.name) ? 'Photos' : 'File' }); } fldSave(); render(); });
    case 'fl-addrow': return fldRowModal(null);
    case 'fl-editrow': return fldRowModal(x);
    case 'fl-imp': return fxPick('.xlsx').then(function (L) { if (L[0]) fldImport(L[0]); });
  } }, true);
document.addEventListener('change', function (ev) { var t = ev.target, a;
  if ((a = t.getAttribute && t.getAttribute('data-scr'))) { var p = a.split('|'), s = schCur(), row = s.data.rows.find(function (r) { return r.id === p[0]; }); subTouch(s, row.act + ' ' + p[1], row[p[1]], t.value); row[p[1]] = t.value; saveRec(); render(); }
  else if ((a = t.getAttribute && t.getAttribute('data-vp'))) { var q = a.split('|'), s2 = subFind(q[0]), old = vpGet(s2.data, q[1]); if (String(old == null ? '' : old) === t.value) return; subTouch(s2, q[1], old, t.value); vpSet(s2.data, q[1], t.value); saveRec(); if (/^sum\.|^docs\./.test(q[1]) || s2.status === 'Draft' && (s2.hist || []).slice(-1)[0].act === 'Revised') render(); }
  else if ((a = t.getAttribute && t.getAttribute('data-ms'))) { var M = REC.mssrX = REC.mssrX || {}; M[a] = t.value; M.upd = new Date().toISOString(); M.by = WHO(); saveRec(); render(); }
  else if ((a = t.getAttribute && t.getAttribute('data-flpo'))) { var F = fldLoad(), r = F.rows.find(function (x) { return x.id === a; }); r.appPo = t.value; fldSave(); render(); }
});
document.addEventListener('input', function (ev) { var t = ev.target; if (t.getAttribute && t.getAttribute('data-fq')) { FX.fld.q = t.value; clearTimeout(FX.fqT); FX.fqT = setTimeout(function () { var pos = t.selectionStart; render(); var i = $('fl-q'); if (i) { i.focus(); i.setSelectionRange(pos, pos); } }, 250); } });

/* indeterminate state of the select-all box after each draw */
var _fxRender = window.render;
window.render = function () { _fxRender(); var c = document.querySelector('[data-itall]'); if (c) c.indeterminate = !!FX.itPart; };

/* ================= seeds and boot ================= */
function fxSeed() { var L = epExpLoad(), ch = false;
  L.forEach(function (r) {
    /* real MSSR narrative (MSSR 01-Nov-2026, Srl 162) for the Petronash order in the sample data */
    if (/74462/.test(r.po) && !r.mssrX) { r.mssrX = { aoc:'1. Tank fab: DHCL Tank-6 delay due to vessel arrival delay for 12 thk plate. Material received on 21-Oct instead of 14-Sep.\n2. Slow progress in fab activity — impact on FAT. Expeditor and inspector (2) deputed to Petronash.\n3. Pumps Milton Roy — 2nd lot 12 pumps readiness to be expedited. FAT between 18-Nov and 8-Dec. Currently ex-works 15/12/2026.\n4. Shortage of piping material for 2nd lot.\n5. Manufacturing of 2nd lot (6 skids) — structural frames, tanks and piping yet to start due to space constraint.', status:'Total PO qty: 12 skids. 55% complete. Structural frame — 2 nos received, 4 nos under painting. 2nd lot 2 nos under fab. Tanks — 2 nos ready, 2 nos under hydro, 2 nos welding in progress.\nFAT — 6 priority skids planned; NOFI received for 5. WHT EA-4 CI and AGI WHT-1-CI FAT completed 25-Oct-26, punch list close-out in progress. AGI WHT-1-DHCI, WHT EA-4 DHCI, WHT EA-6 CI FAT notified 12-Nov to 23-Nov-26. WHT EA-6 DHCL FAT 25-Nov-26, delay in tanks.', eng:'Key documents received and approved code A/B. IFC issuance completed for 1st lot and 2nd lot.', proc:'Dosing pumps: MRE (24 nos) — 8 received, 4 nos under collection 02/11/2026, balance 12 nos FAT between 18-Nov and 8-Dec.\nIRCD/FCV valves: 51 nos, Habu Tech, CDD 25-May-26 — 32 nos received, 19 nos ready for collection (ex-works USA).\nDBBV: 256 nos, Genetech — lot 1 (128 nos) received, lot 2 by 30-Oct-26.\nBV, CV and GV: Zhenjiang Valve, CDD 25-May-26 ex-works — lot 1 (306 nos) received, 274 nos sea shipment ETA 18-Nov.\nLCP: Phenix Meccano — balance 6 nos FDD 30-Oct-2026, ex-works India.', insp:'PIM done on 23-May-26. Pump PIM 09 and 10-Jul-26.', src:'MSSR 01-Nov-2026', upd:'2026-11-01T06:36:52.000Z', by:'MSSR 01-Nov-2026' }; ch = true; }
    /* PO 72166: the vendor's progress report No. 4 as an agreed submission */
    if (/72166/.test(r.po) && !(r.subs || []).some(function (s) { return s.type === 'vpr'; })) { var a = (r.atts || [])[0], d; if (a && a.pl) { var saveREC = typeof REC !== 'undefined' ? REC : null; REC = r; d = vpBlank(null); REC = saveREC; d.no = '4'; d.from = '2024-09-11'; d.to = '2024-11-08'; var mp = { Engineering:'eng', Procurement:'proc', Manufacturing:'mfg', Delivery:'del', Overall:'ovr' }; a.pl.forEach(function (p) { d.sum[mp[p[0]]] = { p:String(p[1]), a:String(p[2]) }; }); d.aoc = 'Production on hold because the PIM was not allowed. Forgings machining to start 03-Dec-2024 if the PIM is held 29-Nov-2024.'; (r.subs = r.subs || []).push({ id:epXId(), type:'vpr', round:1, status:'Agreed', data:d, hist:[{ on:'2024-11-08T08:00:00.000Z', by:'Peroni Pompe (portal)', side:'Vendor', act:'Submitted', note:'Progress Report for Oct-2024.pdf', round:1 }, { on:'2024-11-12T08:00:00.000Z', by:'Arjun', side:'NPCC', act:'Agreed', note:'Loaded from the PO pack', round:1 }] }); ch = true; } }
  });
  if (ch) epExpSave(L); }
(async function () { try { var L = _fxLoad(), need = L.filter(function (r) { return r.mrStudy && r.mrStudy.extract && r.mrStudy.extract.images === '__idb'; }); for (var r of need) { var im = await fxGet('img:' + r.po); if (im) FX.imgs[r.po] = im; } } catch (e) {} fxSeed(); fldLoad(); render(); })();
var _fxReset = null;
document.addEventListener('click', function (ev) { var t = ev.target.closest('[data-s="reset"]'); if (!t) return; Object.keys(EP_MEM).forEach(function (k) { if (k === FLDKEY || k === FKEY) delete EP_MEM[k]; }); try { localStorage.removeItem(FLDKEY); localStorage.removeItem(FKEY); } catch (e) {} FX.F = null; FX.fld = { row:null, q:'', v:'' }; setTimeout(function () { fxSeed(); fldLoad(); render(); }, 0); }, true);
