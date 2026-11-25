/* SmartExpedit third app. The expediting engine and workspace run underneath.
   This file overrides tabList/render and adds the shell, queue, dashboard, plan and new tabs. */
var AFTER = window.SX_EDITION === 'after';
var CONN_INSP = AFTER ? 'IMS' : 'external app', CONN_DEL = AFTER ? 'Logistics app' : 'external app';
var ROLES = {
  PEXM: 'Expediting Manager — Mr. Huzaifa',
  EXP: 'Expeditor — Ali',
  DOC: 'Document Expeditor',
  FIELD: 'Field Expeditor — Hossam'
};
['ENGINEERING','PMT','INSPECTION'].concat(AFTER ? ['EXPEDITING'] : ['QUALITY','CERTIFICATION']).forEach(function (g) { ROLES['REV_' + g] = 'Reviewer — ' + g.charAt(0) + g.slice(1).toLowerCase(); });
var ROLE = 'PEXM', SEC = 'dash', SECTAB = {}, DASH = 'overview', QTAB = 'wait', SX = null, PLAN_ROWS = window.SX_PLAN, RAW = window.SX_RECORDS;
var isV = function () { return ROLE.indexOf('VEN:') === 0; }, revGroup = function () { return ROLE.indexOf('REV_') === 0 ? ROLE.slice(4) : ''; };
var canPO = function (r) { return ROLE === 'PEXM' || ROLE === 'EXP' || ROLE === 'DOC' || (ROLE === 'EXP' && r.assignedTo === 'Ali'); };
var canDoc = function (r) { return canPO(r) || ROLE === 'DOC' || ROLE === 'EXP'; };
var T = function () { return epXToday(); }, ad = epXAddDays, dd = epXDiff;
var PKEY = 'sx_state';
function saveSX() { epStore.set(PKEY, JSON.stringify(SX)); }
function allRecs() { return epExpLoad(); }
function seenRecs() {
  var L = allRecs();
  if (isV()) return L.filter(function (r) { return r.po === ROLE.slice(4); });
  if (ROLE === 'EXP') return L;
  if (ROLE === 'DOC') return L;
  if (ROLE === 'FIELD') return L;
  return L;
}

/* ---------- seed ---------- */
function setupSched(r) {
  epSchInit(r); var i0 = r.issuedOn, lot = (r.lots[0] || {}).date, span = Math.max(30, dd(i0, lot)), n = r.sch.rows.length;
  var inc = String(r.incoterm || '').toUpperCase().split(' ')[0];
  r.sch.rows.forEach(function (x, i) {
    var s = ad(i0, Math.round(span * i / n)), e = ad(s, Math.max(1, Math.round(span / n)));
    if (/FOB Port/.test(x.act) && inc !== 'FOB' || /CFR Port/.test(x.act) && !/CFR|CIF/.test(inc) || /Delivered at/.test(x.act) && !/DDP|DDU|DAP|DPU/.test(inc)) { x.na = { why:'Not this incoterm', by:'System' }; return; }
    if (!x.bS) x.bS = s; if (!x.bE) x.bE = e;
    var slip = i % 7 === 4 ? 6 : 0; x.fS = ad(x.bS, slip); x.fE = ad(x.bE, slip); if (slip) x.dep = 'Sub-order delay (sample)';
    x.dur = dd(x.bS, x.bE); x.pct = x.fE <= T() ? '100' : x.fS <= T() ? '50' : '0';
  });
  epSchFreeze(r, r.assignedTo || 'System');
}
function seedAll() {
  var L = JSON.parse(RAW), A = L[0], B = L[1], C = L[2], days = function (r, ago, lot) { r.issuedOn = ad(T(), -ago); r.issuedAt = r.issuedOn + ' 09:00'; r.notifiedOn = r.issuedOn + 'T05:00:00.000Z'; r.lots[0].date = lot; };
  days(A, 70, ad(T(), 45)); days(B, 40, ad(T(), 95)); days(C, 12, ad(T(), 80));
  [A, B].forEach(function (r, i) { r.assignedTo = i ? 'Arjun' : 'Ali'; r.assignedBy = 'Mr. Huzaifa'; r.assignedOn = ad(r.issuedOn, 2); setupSched(r); epRegCreateFromSdr(r, r.assignedTo, 'NPCC'); epLetterSend(r, epLetterDraft(r, r.assignedTo), r.assignedTo); });
  A.ackDate = ad(A.issuedOn, 2); A.kickoffOn = ad(A.issuedOn, 14); A.stage = 'docsIn'; A.mfg = Object.assign(A.mfg || {}, { fabStart:'' }); B.stage = 'docsOut'; B.ackDate = ad(B.issuedOn, 4); B.kickoffOn = ad(B.issuedOn, 15);
  /* the Petronash order from his sub-order report */
  var D = JSON.parse(JSON.stringify(C)); D.po = '2820-2025-74462-AC'; D.letter = 'AC'; D.supplier = 'PETRONASH FZE'; D.supplierShort = 'Petronash FZE'; D.mrRef = '2820-2025-74462'; D.head = 'Chemical Injection Package'; D.value = 4800000; D.ccy = 'USD'; D.incoterm = 'DAP Mussafah';
  D.issuedOn = '2025-09-01'; D.issuedAt = '2025-09-01 09:00'; D.notifiedOn = '2025-09-01T05:00:00.000Z'; D.lots = [{ id:'Lot 1', date:'2026-09-30', grace:2, ld:true }];
  D.items = PLAN_ROWS.map(function (p, i) { return { item:(i + 1) * 10, desc:p.item, unit:'EA', qty:+p.qty || 0, hold:0, lot:'Lot 1' }; }); D.lines = D.items.length; D.qty = D.items.reduce(function (s, x) { return s + x.qty; }, 0);
  D.assignedTo = 'Ali'; D.assignedBy = 'Mr. Huzaifa'; D.assignedOn = '2025-09-03'; D.ackDate = '2025-09-04'; D.kickoffOn = '2025-09-20'; D.stage = 'fab'; D.mfg.pimOn = '2026-04-02'; D.mfg.fabStart = '2026-01-20'; delete D.sch; setupSched(D);
  [['A001','Supplier Data Register',-300],['X002','Inspection and Test Plan',-200],['Z003','Manufacturing Schedule',-280]].forEach(function (c) { var o = epRegAdd(D, c[0], 'Ali', 'NPCC', c[1]); var row = D.reg.rows[D.reg.rows.length - 1]; row.planned = ad(T(), c[2]); });
  epLetterSend(D, epLetterDraft(D, 'Ali'), 'Ali');
  var P = planInit(D), ids = PLAN_ROWS.map(function () { return epXId(); });
  P.rows = PLAN_ROWS.map(function (p, i) { var q = Object.assign({ id:ids[i], x:{}, m:{}, deleted:null }, p); if (p.dep !== '') q.dep = ids[p.dep]; return q; }); P.ver = 1; P.cov = {}; D.items.forEach(function (x) { P.cov[x.item] = true; });
  L.push(D);
  /* modelled cleared quantities */
  var frac = function (r, a, b, c) { r.clr = {}; var n = r.items.length; r.items.forEach(function (x, i) { var u = i / n; r.clr[x.item] = { irn:u < a ? x.qty : 0, ship:u < b ? x.qty : 0, mrv:u < c ? x.qty : 0 }; }); };
  frac(A, 0, 0, 0); frac(B, 0, 0, 0); frac(C, 0, 0, 0); frac(D, .35, .25, .15);
  /* document reviews on Rollstud */
  var rows = A.reg.rows.filter(function (r) { return !r.deleted; });
  var sub = function (row, ago, resp) { row.actual = ad(T(), -ago); var e = { cycle:1, sub:row.actual, due:ad(row.actual, 14), state:'IN_REVIEW', file:row.code + '.pdf', reviews:groups(row).map(function (g) { return { group:g, status:resp ? 'NO_COMMENT' : 'PENDING', comment:'' }; }) }; if (resp) e.state = 'WITH_EXPEDITOR'; (A.rvw = A.rvw || {})[row.id] = e; };
  if (rows[0]) sub(rows[0], 20, false); if (rows[1]) sub(rows[1], 5, false); if (rows[2]) sub(rows[2], 9, true);
  epExpSave(L);
  SX = { concerns:[
    { id:epXId(), po:D.po, no:'ACT-001', cat:'SUB_VENDOR', issue:'Dosing pump float is negative, with 100% witness delivery impact', by:'VENDOR', assignedTo:'VENDOR', assignedVendor:'Rollstud Middle East', source:'Procurement Plan', target:ad(T(), -3), impact:'CRITICAL', status:'OPEN', history:[{ on:ad(T(), -5), by:'EXPEDITOR', act:'Created', note:'Logged during procurement plan review' }] },
    { id:epXId(), po:A.po, no:'ACT-002', cat:'ENGINEERING', issue:'Register review past SLA on A001 (sample)', by:'ENGINEERING', assignedTo:'DOC', assignedVendor:'Petronash FZE', source:'Document SLA', target:ad(T(), -9), impact:'MAJOR', status:'OPEN', history:[{ on:ad(T(), -12), by:'DOC_EXPEDITOR', act:'Created', note:'14-day SLA exceeded' }] },
    { id:epXId(), po:D.po, no:'ACT-003', cat:'SHOP_VISIT', issue:'Machining delay on flange batch B — lack of raw billet material at shop', by:'FIELD', assignedTo:'VENDOR', assignedVendor:'Rollstud Middle East', source:'Field Visit ER', target:ad(T(), -16), impact:'CRITICAL', status:'OPEN', history:[{ on:ad(T(), -20), by:'FIELD_EXPEDITOR', act:'Created from Shop Visit ER', note:'Recorded in visit log' }] },
    { id:epXId(), po:D.po, no:'ACT-004', cat:'INSPECTION', issue:'PIM agenda and test bench calibration certificates to be confirmed before witness test', by:'EXPEDITOR', assignedTo:'FIELD', assignedVendor:'Rollstud Middle East', source:'Inspection', target:ad(T(), 6), impact:'MEDIUM', status:'OPEN', history:[{ on:ad(T(), -1), by:'EXPEDITOR', act:'Created', note:'Pre-inspection meeting prep' }] },
    { id:epXId(), po:A.po, no:'ACT-005', cat:'FABRICATION', issue:'Pressure vessel nozzle weld test coupons radiography report required', by:'EXPEDITOR', assignedTo:'VENDOR', assignedVendor:'Petronash FZE', source:'Shop Visit', target:ad(T(), -1), impact:'HIGH', status:'PENDING_VERIFICATION', resolution:'RT film review completed and approved by Level III inspector. Report NDT-2026-88 uploaded.', evidence:'NDT Report NDT-2026-88 Rev 0', history:[{ on:ad(T(), -4), by:'EXPEDITOR', act:'Created', note:'NDT coupon request' }, { on:T(), by:'VENDOR', act:'Resolution Submitted', note:'RT film review completed and approved by Level III inspector.' }] }
  ] };
  saveSX();
}

/* ---------- document groups and review ---------- */
function groups(row) { if (AFTER) return ['ENGINEERING','INSPECTION','EXPEDITING','PMT']; var d = epSdrl(row.code); return [(d && d.custodian) || 'PMT']; }
function rv(id) { return (REC.rvw = REC.rvw || {})[id]; }
function rvOver(e) { return e && !e.ret && e.state !== 'PASSED' && e.state !== 'RETURNED' && e.due < T(); }
function allOverdue() { var n = 0; allRecs().forEach(function (r) { Object.keys(r.rvw || {}).forEach(function (k) { if (rvOver(r.rvw[k])) n++; }); }); return n; }
function reviewCard() {
  var g = revGroup(), ven = VIEW === 'vendor', rows = ((REC.reg && REC.reg.rows) || []).filter(function (r) { return !r.deleted; });
  if (g) rows = rows.filter(function (r) { var e = rv(r.id); return e && e.reviews.some(function (x) { return x.group === g; }); });
  var body = rows.map(function (r) { var e = rv(r.id), act = '';
    if (ven && (!e || e.state === 'RETURNED')) act = '<button class="ep-btn primary xs" data-s="dsub" data-x="' + r.id + '">' + (e ? 'Resubmit' : 'Submit') + '</button>';
    if (g && e && e.state === 'IN_REVIEW') { var m = e.reviews.find(function (x) { return x.group === g; }); if (m.status === 'PENDING') act = '<button class="ep-btn secondary xs" data-s="dcom" data-x="' + r.id + '">Comment</button> <button class="ep-btn secondary xs" data-s="dnoc" data-x="' + r.id + '">No comment</button>'; }
    if (canDoc(REC) && !ven && e && e.state === 'WITH_EXPEDITOR') act = '<button class="ep-btn secondary xs" data-s="dret" data-x="' + r.id + '">Return</button> <button class="ep-btn primary xs" data-s="dacc" data-x="' + r.id + '">Accept, pass to VDMS</button>';
    var st = e ? { IN_REVIEW:'info', WITH_EXPEDITOR:'warn', RETURNED:'warn', PASSED:'' }[e.state] : '';
    return '<tr><td class="tabnum">' + esc(r.npcc) + '</td><td>' + esc(r.title) + (ven && e && e.comments && e.state === 'RETURNED' ? '<div class="ep-sub"><b>Comments:</b> ' + esc(e.comments) + '</div>' : '') + '</td><td>' + (e ? e.cycle : '—') + '</td><td>' + (e ? fmtDate(e.sub) : '—') + '</td><td>' + (e ? fmtDate(e.due) + (rvOver(e) ? ' <span class="ep-pill rose sm">Overdue</span>' : '') : '—') + '</td>' +
      (ven ? '' : '<td>' + (e ? e.reviews.map(function (x) { return esc(x.group) + ': ' + (x.status === 'PENDING' ? 'pending' : x.status === 'NO_COMMENT' ? 'no comment' : esc(x.comment)); }).join('<br>') : '—') + '</td>') +
      '<td><span class="ep-pill ' + (st || 'slate') + ' sm">' + (e ? e.state.replace(/_/g, ' ') : 'NOT SUBMITTED') + '</span></td><td>' + act + '</td></tr>'; }).join('');
  return '<div class="ep-card flush" id="review-card"><div class="ep-card-title"><span>Document review</span><span class="ep-sub">14-day SLA from submission · ' + (AFTER ? 'all four groups respond' : 'routed to the SDRL custodian') + '</span></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Document no.</th><th>Title</th><th>Cycle</th><th>Submitted</th><th>SLA due</th>' + (ven ? '' : '<th>Reviewers</th>') + '<th>Status</th><th></th></tr></thead><tbody>' + (body || '<tr><td colspan="8" class="ep-sub">Nothing is waiting here.</td></tr>') + '</tbody></table></div></div>';
}
function dSubmit(id) { var row = epRegFind(REC, id), e = rv(id);
  modal(e ? 'Resubmit document' : 'Submit document', '<div class="ep-sub" style="margin-bottom:8px;">' + esc(row.npcc) + ' — ' + esc(row.title) + '</div><div class="ep-lbl">Document file</div><input type="file" id="m-file" class="ep-in">', function () {
    var f = $('m-file').files[0]; if (!f) return toast('Choose the file.');
    epRegSet(REC, id, 'actual', T(), WHO(), SIDE());
    REC.rvw[id] = { cycle:(e ? e.cycle + 1 : 1), sub:T(), due:ad(T(), 14), state:'IN_REVIEW', file:f.name, reviews:groups(row).map(function (g) { return { group:g, status:'PENDING', comment:'' }; }) };
    saveRec(); closeModal(); render(); toast('Submitted for review. The 14-day SLA has started.'); }); }
function dResp(id, status, comment) { var e = rv(id), g = revGroup(), m = e.reviews.find(function (x) { return x.group === g; }); m.status = status; m.comment = comment || ''; m.by = ROLES[ROLE]; if (e.reviews.every(function (x) { return x.status !== 'PENDING'; })) e.state = 'WITH_EXPEDITOR'; saveRec(); render(); toast('Response saved.'); }
function dReturn(id) { var e = rv(id), pre = e.reviews.filter(function (x) { return x.comment; }).map(function (x) { return x.group + ': ' + x.comment; }).join('\n');
  modal('Return to vendor', '<div class="ep-lbl">NPCC status</div><select id="m-st" class="ep-in"><option value="B">B — Commented as marked</option><option value="C">C — Not accepted</option></select><div class="ep-lbl" style="margin-top:8px;">Comments for the vendor</div><textarea id="m-c" class="ep-ta">' + esc(pre) + '</textarea>', function () {
    var c = $('m-c').value.trim(); if (!c) return toast('Add the comments.'); epRegSet(REC, id, 'npccSt', $('m-st').value, WHO(), 'NPCC'); e.state = 'RETURNED'; e.comments = c; e.ret = T(); note(REC.po, 'VEN:' + REC.po, 'Document returned with comments: ' + epRegFind(REC, id).npcc); saveRec(); closeModal(); render(); toast('Returned to the vendor.'); }); }
function dAccept(id) { var e = rv(id); epRegSet(REC, id, 'npccSt', 'A', WHO(), 'NPCC'); epRegSetRoute(REC, id, 'vdmsSent', WHO(), 'NPCC'); e.state = 'PASSED'; e.ret = T(); saveRec(); render(); toast('Accepted and passed to VDMS.'); }
function note(po, to, t) { SX.notes = SX.notes || []; SX.notes.unshift({ po:po, to:to, t:t, on:T() }); saveSX(); }

/* ---------- procurement plan ---------- */
var PC = [['item','Material / Equipment',200],['qty','Total Qty',70],['resp','Responsible',90],['sub','Selected Sub-vendor',190],['loc','Mfg Location',100],['no','Sub-Order No.',110],['insp','Insp. Level',70],['fPlace','Forecast placement (a)',125,'date'],['aPlace','Actual placement',125,'date'],['clear','Mfg clearance',125,'date'],['weeks','Lead time, weeks (b)',80,'number'],['contract','Contractual delivery',125,'date'],['Q','Forecast delivery (c)',105,'calc'],['transit','Transit, days (d)',75,'number'],['S','Expected at shop (e)',105,'calc'],['raw','RAW date (f)',125,'date'],['U','Float (f−e)',70,'calc'],['stage','Stage',75,'calc'],['status','Current status / reasons',260,'text'],['cName','Contact name',130],['cMail','Contact email',170],['cPhone','Contact phone',120]];
if (AFTER) PC.splice(6, 0, ['unp','Unpriced PO copy',130], ['unpR','Unpriced review',100, 'review']);
function planInit(r) { if (!r.plan) r.plan = { rows:[], extra:[], log:[], ver:0, cov:{}, submitted:null, confirmed:null }; return r.plan; }
function plQ(x) { if (x.over) return x.over; if (x.contract) return x.contract; var c = [x.fPlace, x.aPlace, x.clear].filter(Boolean).sort().pop(); return c ? ad(c, (+x.weeks || 0) * 7) : ''; }
function plS(x) { var q = plQ(x); return q ? ad(q, +x.transit || 0) : ''; }
function plRaw(x, rows) { if (x.dep) { var p = rows.find(function (r) { return r.id === x.dep; }); var s = p && plS(p); return s ? ad(s, -(+x.depDays || 0)) : ''; } return x.raw; }
function plU(x, rows) { var f = plRaw(x, rows), e = plS(x); return f && e ? dd(e, f) : null; }
function flSt(v) { return v == null ? '' : v < 0 ? 'CRITICAL DELAY' : v <= 14 ? 'WARNING' : 'ON TRACK'; }
function flPill(v) { if (v == null) return '—'; return '<span class="ep-pill ' + (v < 0 ? 'rose' : v <= 14 ? 'warn' : 'ok') + ' sm">' + v + '</span>'; }
function plCheck(r) { var P = planInit(r), live = P.rows.filter(function (x) { return !x.deleted; }), un = (r.items || []).filter(function (i) { return !P.cov[i.item]; }).length;
  var bad2 = live.filter(function (x) { return !x.aPlace && (!x.status || !x.fPlace); }).length, crit = live.filter(function (x) { var u = plU(x, P.rows); return u != null && u < 0; }).length;
  return { live:live, un:un, bad2:bad2, crit:crit, ok:un === 0 && bad2 === 0 && live.length > 0 }; }
function allCrit() { var n = 0; allRecs().forEach(function (r) { if (r.plan) n += plCheck(r).crit; }); return n; }
function tabPlan() { var P = planInit(REC), c = plCheck(REC), ven = VIEW === 'vendor', cols = PC.concat(P.extra.map(function (e) { return [e.key, e.label + ' *', 120, 'x']; })), html = '';
  html += '<div class="ep-note">' + (ven ? 'List <b>every sub-order item, placed or not</b>. For orders not placed, give the enquiry status and the expected order date. Every change is marked with who made it.' : 'The vendor keeps this plan on the portal. Both sides add rows and columns, every change is marked, and deleted rows stay struck through with their reason.') + '</div>';
  html += '<div class="ep-kpis" style="grid-template-columns:repeat(5,1fr);">' + kp('Sub-order items', c.live.length, 'listed') + kp('Critical', c.crit, 'negative float', c.crit > 0) + kp('Warning', c.live.filter(function (x) { var u = plU(x, P.rows); return u != null && u >= 0 && u <= 14; }).length, 'float 0 to 14') + kp('Not placed', c.live.filter(function (x) { return !x.aPlace; }).length, 'still at enquiry') + kp('PO items not covered', c.un, 'rule 1', c.un > 0) + '</div>';
  var st = P.confirmed ? '<span class="ep-pill ok sm">Confirmed ' + fmtDate(P.confirmed.on) + '</span>' : P.submitted ? '<span class="ep-pill info sm">Submitted ' + fmtDate(P.submitted.on) + '</span>' : '<span class="ep-pill warn sm">Draft</span>';
  html += '<div class="ep-card flush"><div class="ep-card-title"><span>Procurement plan — version ' + (P.ver || 0) + ' ' + st + '</span><span class="ep-row"><span class="ep-pill ep-mk-n sm">NMDC change</span><span class="ep-pill ep-mk-v sm">Vendor change</span>' +
    '<button class="ep-btn primary sm" data-s="pl-add">+ Add row</button><button class="ep-btn secondary sm" data-s="pl-col">+ Add column</button><button class="ep-btn secondary sm" data-s="pl-cov">Match PO items</button><button class="ep-btn secondary sm" data-s="pl-dl">Download .xlsx</button><button class="ep-btn secondary sm" data-s="pl-up">Upload .xlsx</button>' +
    (ven ? '<button class="ep-btn primary sm" data-s="pl-submit">Submit plan</button>' : '<button class="ep-btn primary sm" data-s="pl-confirm">Confirm plan</button>') + '</span></div>';
  if (!P.rows.length) html += '<div class="ep-empty"><div class="big">No plan submitted yet</div><div class="ep-sub">Add the first sub-order row or upload the vendor’s Excel.</div></div>';
  else { html += '<div style="overflow-x:auto;max-height:560px;"><table class="ep-table sx-plan"><thead><tr><th>#</th>' + cols.map(function (k) { return '<th style="min-width:' + k[2] + 'px">' + esc(k[1]) + '</th>'; }).join('') + '<th></th></tr></thead><tbody>';
    var n = 0; P.rows.forEach(function (x) { var u = plU(x, P.rows), dele = !!x.deleted; html += '<tr class="' + (dele ? 'sx-del' : '') + '" title="' + (dele ? esc('Deleted: ' + x.deleted.why) : '') + '"><td class="tabnum">' + (dele ? '' : ++n) + '</td>' + cols.map(function (k) { var f = k[0], t = k[3];
      if (f === 'Q') return '<td class="tabnum sx-calc" title="' + (x.over ? esc('Manual override: ' + x.overWhy) : '') + '">' + fmtDate(plQ(x)) + (x.over ? ' <span class="ep-pill warn sm">Override</span>' : '') + (dele ? '' : ' <button class="ep-btn xs secondary" data-s="pl-ov" data-x="' + x.id + '">Edit</button>') + '</td>';
      if (f === 'S') return '<td class="tabnum sx-calc">' + fmtDate(plS(x)) + '</td>'; if (f === 'U') return '<td class="sx-calc">' + flPill(u) + '</td>';
      if (f === 'stage') return '<td class="sx-calc"><span class="ep-pill ' + (x.aPlace ? 'ok' : 'warn') + ' sm">' + (x.aPlace ? 'Placed' : 'Enquiry') + '</span></td>';
      if (f === 'raw' && x.dep) { var p = P.rows.find(function (y) { return y.id === x.dep; }); return '<td class="tabnum sx-calc" title="Depends on ' + esc(p ? p.item : '') + '">' + fmtDate(plRaw(x, P.rows)) + '<div class="ep-sub">' + (x.depDays || 0) + ' d before ' + esc((p ? p.item : '').slice(0, 16)) + '</div></td>'; }
      var val = t === 'x' ? (x.x[f] || '') : (x[f] == null ? '' : x[f]), mk = x.m[f], cl = mk ? (mk.side === 'Vendor' ? ' sx-mv' : ' sx-mn') : '', dis = (dele || (f === 'raw' && ven)) ? ' disabled' : '', ti = mk ? ' title="' + esc(mk.by + ' · ' + fmtDT(mk.on) + ' · was: ' + (mk.old || '(empty)')) + '"' : '';
      if (t === 'review') return '<td class="' + cl + '"' + ti + '><select class="sx-c" data-pl="' + f + '" data-x="' + x.id + '"' + dis + (ven ? ' disabled' : '') + '>' + ['', 'Reviewed', 'Comments'].map(function (o) { return '<option' + (o === val ? ' selected' : '') + '>' + o + '</option>'; }).join('') + '</select></td>';
      if (t === 'text') return '<td class="' + cl + '"' + ti + '><textarea class="sx-c" rows="2" data-pl="' + f + '" data-x="' + x.id + '"' + dis + '>' + esc(val) + '</textarea></td>';
      return '<td class="' + cl + '"' + ti + '><input class="sx-c" type="' + (t === 'date' || t === 'number' ? t : 'text') + '" value="' + esc(val) + '" data-pl="' + f + '" data-x="' + x.id + '"' + dis + '></td>'; }).join('') +
      '<td>' + (dele ? '<button class="ep-btn xs secondary" data-s="pl-rest" data-x="' + x.id + '">Restore</button>' : (!ven && u != null && u < 0 ? '<button class="ep-btn xs secondary" data-s="pl-dep" data-x="' + x.id + '">Department status</button> ' : '') + '<button class="ep-btn xs danger" data-s="pl-del" data-x="' + x.id + '">Delete</button>') + '</td></tr>'; });
    html += '</tbody></table></div>'; }
  return html + '</div><div class="ep-sub" style="margin-top:6px;">Forecast delivery uses the contractual date if entered, otherwise the latest of (a), actual placement and clearance + (b). Expected at shop = (c) + (d). Float = (f) − (e). Status: below 0 critical, 0 to 14 warning, above 14 on track.</div>'; }
function plSet(id, f, v) { var P = REC.plan, x = P.rows.find(function (r) { return r.id === id; }), ex = !PC.some(function (k) { return k[0] === f; }), old = ex ? (x.x[f] || '') : (x[f] == null ? '' : x[f]); if (String(old) === String(v)) return; if (ex) x.x[f] = v; else x[f] = v; x.m[f] = { by:WHO(), side:SIDE(), on:epXNow(), old:old }; P.ver++; P.confirmed = null; P.submitted = null; P.log.push({ on:epXNow(), by:WHO(), f:f, old:old, v:v, item:x.item }); saveRec(); render(); }
function plXlsx() { var P = REC.plan, cols = PC.filter(function (k) { return k[0] !== 'stage'; }).concat(P.extra.map(function (e) { return [e.key, e.label + ' *', 120, 'x']; })), rows = P.rows.filter(function (x) { return !x.deleted; }).map(function (x) { return cols.map(function (k) { var f = k[0]; if (f === 'Q') return plQ(x); if (f === 'S') return plS(x); if (f === 'U') { var u = plU(x, P.rows); return u == null ? '' : String(u); } if (f === 'raw') return plRaw(x, P.rows) || ''; return k[3] === 'x' ? (x.x[f] || '') : String(x[f] == null ? '' : x[f]); }); });
  downloadMiniXlsx(miniBuildXlsx({ sheetName:'Sub-order status', title:'SUB ORDER STATUS REPORT — PO ' + REC.po + ' — ' + REC.supplier, columns:cols.map(function (k) { return { header:k[1], width:Math.max(12, Math.round(k[2] / 7)) }; }), rows:rows }), 'Sub Order Status ' + REC.po + '.xlsx'); }
var PUP = { 'material':'item','materialequipment':'item','totalqty':'qty','responsible':'resp','selectedsubvendor':'sub','mfglocation':'loc','manufacturinglocation':'loc','suborderno':'no','inspectionlevel':'insp','insplevel':'insp','forecastplacementa':'fPlace','forecastsuborderplacementdatea':'fPlace','actualplacement':'aPlace','actualsuborderplacementdate':'aPlace','mfgclearance':'clear','mfgclearancedate':'clear','leadtimeweeksb':'weeks','contractualdelivery':'contract','transitdaysd':'transit','rawdatef':'raw','currentstatusreasons':'status','contactname':'cName','contactemail':'cMail','contactphone':'cPhone' };
async function plUpload(f) { try { var parsed = await epXlsxRead(await f.arrayBuffer()), rows = parsed.rows || [], h = -1; for (var i = 0; i < Math.min(rows.length, 30); i++) { if ((rows[i] || []).some(function (c) { return PUP[epRegNorm(c)] === 'item'; })) { h = i; break; } } if (h < 0) return toast('No header row found. The sheet needs a Material / Equipment column.');
    var map = (rows[h] || []).map(function (c) { return PUP[epRegNorm(c)] || ''; }), P = REC.plan, add = 0, upd = 0; for (var r = h + 1; r < rows.length; r++) { var row = rows[r] || [], o = {}; map.forEach(function (k, ix) { if (k && row[ix] != null && row[ix] !== '') o[k] = String(row[ix]).slice(0, /Place|clear|contract|raw/.test(k) ? 10 : 2000); }); if (!o.item) continue; var x = P.rows.find(function (y) { return !y.deleted && y.item === o.item; }); if (!x) { x = { id:epXId(), x:{}, m:{}, deleted:null, item:o.item, dep:'', depDays:'', over:'', overWhy:'' }; P.rows.push(x); add++; x.m.item = { by:WHO(), side:SIDE(), on:epXNow(), old:'' }; } else upd++; Object.keys(o).forEach(function (k) { if (String(x[k] == null ? '' : x[k]) !== o[k]) { x.m[k] = { by:WHO(), side:SIDE(), on:epXNow(), old:x[k] || '' }; x[k] = o[k]; } }); }
    P.ver++; P.confirmed = null; saveRec(); render(); toast(add + ' added, ' + upd + ' updated from the Excel.'); } catch (e) { toast('That file could not be read: ' + e.message); } }
function tabAnalysis() { return '<div class="ep-card ep-empty"><div class="big">Analysis</div><div class="ep-sub">Reserved. The logic will be added here later.</div></div>'; }

/* ---------- connectors, inspection, delivery ---------- */
function conn(title, app, feeds) { return '<div class="ep-card sx-conn"><div class="ep-row" style="justify-content:space-between;"><b>' + esc(title) + '</b><span class="ep-pill warn sm">Not connected</span></div><div class="ep-sub" style="margin:6px 0;">Connects to ' + esc(app) + '. The link is set up in the Base44 build, once the connection details are confirmed.</div><div class="ep-lbl">Will receive</div><ul class="sx-ul">' + feeds.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('') + '</ul></div>'; }
function tabIap() { return conn('IAP — Inspection Assignment Pack', CONN_INSP, ['Inspection assignment pack and its status', AFTER ? 'Time sheets and TPI personnel records' : 'Inspection assignment details']); }
function tabIrn() { var m = REC.mfg || {}; return conn('IRN', CONN_INSP, AFTER ? ['IRN and IRC', 'Inspection reports and MTC', 'Released quantity per line item and lot'] : ['IRN details', 'Released quantity per line item and lot']) + '<div class="ep-card"><div class="ep-fields" style="grid-template-columns:repeat(2,1fr);">' + hf('IRN issued', m.irn ? fmtDate(m.irn) : '—') + hf('Source', 'Modelled until connected') + '</div><button class="ep-btn secondary sm" data-s="mfgd">Record dates</button></div>'; }
function tabPim() { var m = REC.mfg || {}; return conn('PIM', CONN_INSP, AFTER ? ['PIM MOM with dossier', 'PIM notification'] : ['PIM record']) + '<div class="ep-card"><div class="ep-fields" style="grid-template-columns:repeat(2,1fr);">' + hf('PIM held', m.pimOn ? fmtDate(m.pimOn) : '—') + hf('Notes', m.pimNotes || '—') + '</div><button class="ep-btn secondary sm" data-s="pimm">Record PIM</button></div>'; }
function sList(key, title, cols, app) { var rows = (REC.sx = REC.sx || {})[key] = (REC.sx[key] || []); return '<div class="ep-card flush"><div class="ep-card-title"><span>' + esc(title) + '</span><span class="ep-row"><span class="ep-pill slate sm">' + esc(app) + '</span><button class="ep-btn primary sm" data-s="sl-add" data-x="' + key + '" data-y="' + esc(cols.join('|')) + '">+ Add</button></span></div><table class="ep-table"><thead><tr>' + cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>' + (rows.map(function (r) { return '<tr>' + cols.map(function (c) { return '<td>' + esc(r[c]) + '</td>'; }).join('') + '</tr>'; }).join('') || '<tr><td colspan="' + cols.length + '" class="ep-sub">No entries yet.</td></tr>') + '</tbody></table></div>'; }
function tabNotif() { return sList('notif', 'Inspection notifications', ['Activity', 'Type', 'Requested date', 'Status'], 'From IMS') + sList('look', 'Inspection look-ahead schedule', ['Activity', 'Forecast date', 'For client'], 'From supplier'); }
function tabPunch() { return sList('punch', 'Punch list', ['Punch point', 'Raised by', 'Due', 'Status'], 'From TPIA'); }
function qty(r) { var o = { all:0, irn:0, ship:0, mrv:0 }; (r.items || []).forEach(function (x) { var c = (r.clr || {})[x.item] || {}; o.all += +x.qty || 0; o.irn += c.irn || 0; o.ship += c.ship || 0; o.mrv += c.mrv || 0; }); return o; }
function tabDeliv() { var q = qty(REC), s = REC.ship || {}; var rows = (REC.items || []).slice(0, 40).map(function (x) { var c = (REC.clr || {})[x.item] || {}; return '<tr><td class="tabnum">' + x.item + '</td><td>' + esc(x.desc) + '</td><td>' + esc(x.lot || 'Lot 1') + '</td><td class="tabnum">' + n(x.qty) + '</td><td class="tabnum">' + n(c.irn) + '</td><td class="tabnum">' + n(c.ship) + '</td><td class="tabnum">' + n(c.mrv) + '</td></tr>'; }).join('');
  return conn('Delivery', CONN_DEL, AFTER ? ['Shipping documents', 'Shipped quantity per line item and lot', 'MRV quantity per line item and lot', 'Stamped delivery notes from stores'] : ['Shipment details', 'Shipped quantity per line item and lot', 'MRV quantity per line item and lot']) +
    '<div class="ep-kpis" style="grid-template-columns:repeat(3,1fr);">' + kp('IRN issued', pct(q.irn, q.all) + '%', n(q.irn) + ' of ' + n(q.all)) + kp('Shipped', pct(q.ship, q.all) + '%', n(q.ship) + ' of ' + n(q.all)) + kp('Received (MRV)', pct(q.mrv, q.all) + '%', n(q.mrv) + ' of ' + n(q.all)) + '</div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>By line item and lot</span><span class="ep-pill warn sm">MODELLED until connected</span></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Item</th><th>Description</th><th>Lot</th><th>Qty</th><th>IRN</th><th>Shipped</th><th>MRV</th></tr></thead><tbody>' + rows + '</tbody></table></div>' + (REC.items.length > 40 ? '<div class="ep-sub" style="padding:8px 12px;">Showing the first 40 of ' + REC.items.length + ' lines.</div>' : '') + '</div>'; }
function tabDispatch() { var d = REC.disp = REC.disp || {}, it = [['pack', 'Advance packing list received from the vendor'], ['pmt', 'PMT confirmed the destination and transport mode'], ['logi', 'Logistics instructed to dispatch']]; return '<div class="ep-card"><div class="ep-card-title">Dispatch actions</div>' + it.map(function (x, i) { var locked = i && !d[it[i - 1][0]]; return '<div class="ep-row" style="justify-content:space-between;padding:7px 0;border-bottom:1px solid #e2e8f0;"><span>' + x[1] + '</span>' + (d[x[0]] ? '<span class="ep-pill ok sm">Done ' + fmtDate(d[x[0]]) + '</span>' : '<button class="ep-btn secondary xs" data-s="disp" data-x="' + x[0] + '"' + (locked ? ' disabled' : '') + '>Mark done</button>') + '</div>'; }).join('') + '</div>'; }
function tabProgress() { var a = REC.atts = REC.atts || []; return '<div class="ep-card flush"><div class="ep-card-title"><span>Monthly progress reports</span><button class="ep-btn primary sm" data-s="att">Upload report</button></div><table class="ep-table"><thead><tr><th>Month</th><th>File</th><th>Uploaded by</th></tr></thead><tbody>' + (a.map(function (x) { return '<tr><td>' + esc(x.m) + '</td><td>' + esc(x.f) + '</td><td>' + esc(x.by) + '</td></tr>'; }).join('') || '<tr><td colspan="3" class="ep-sub">No reports uploaded yet.</td></tr>') + '</tbody></table></div>'; }
function tabMssr() { var P = planInit(REC), c = plCheck(REC), pr = epSchProgress(REC) || {}, st = REC.reg ? epRegStats(REC) : { total:0, submitted:0, overdue:0 }, q = qty(REC), ms = (REC.sch.rows || []).filter(function (r) { return !r.na && r.bE; }).slice(0, 23), late = ms.filter(function (r) { return r.fE > r.bE; });
  return '<div class="ep-note">The MSSR is generated from the data already in this app, so nobody retypes it. Use Download for the weekly issue.</div><div class="ep-card"><div class="ep-card-title"><span>Weekly MSSR — ' + esc(REC.po) + ' · ' + fmtDate(T()) + '</span><button class="ep-btn primary sm" data-s="mssr-dl">Download .xlsx</button></div><div class="ep-kpis" style="grid-template-columns:repeat(4,1fr);">' + kp('Stage', epExpStatusLabel(REC), 'current') + kp('Documents', st.submitted + ' / ' + st.total, st.overdue + ' overdue', st.overdue > 0) + kp('Critical sub-orders', c.crit, 'negative float', c.crit > 0) + kp('Received (MRV)', pct(q.mrv, q.all) + '%', 'by quantity') + '</div></div>' +
    '<div class="ep-card flush"><div class="ep-card-title">Key milestones and deviations</div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Activity</th><th>Baseline finish</th><th>Forecast finish</th><th>Slip</th><th>%</th><th>Reason</th></tr></thead><tbody>' + ms.map(function (r) { var s = dd(r.bE, r.fE) || 0; return '<tr><td>' + esc(r.act) + '</td><td class="tabnum">' + fmtDate(r.bE) + '</td><td class="tabnum">' + fmtDate(r.fE) + '</td><td class="tabnum">' + (s ? '+' + s + ' d' : '—') + '</td><td>' + esc(r.pct) + '</td><td>' + esc(r.dep) + '</td></tr>'; }).join('') + '</tbody></table></div></div><div class="ep-sub">' + late.length + ' activities are running late.</div>'; }
function tabCloseX() { var L = REC.ld = REC.ld || { rate:'', cap:'', amt:'', state:'' }, a = epExpAging(REC), amt = (+L.rate || 0) * a.late, cap = (+REC.value || 0) * (+L.cap || 0) / 100, ld = cap ? Math.min(amt, cap) : amt;
  return tabClose() + '<div class="ep-card"><div class="ep-card-title"><span>Liquidated damages</span><span class="ep-pill ' + (a.ldLots ? 'rose' : 'slate') + ' sm">' + a.ldLots + ' lot(s) under LD · ' + a.late + ' days late</span></div><div class="ep-fields" style="grid-template-columns:repeat(3,1fr);"><div><div class="ep-lbl">LD per day (' + esc(REC.ccy) + ')</div><input class="ep-in" id="ld-rate" type="number" data-sc="ld-rate" value="' + esc(L.rate) + '"></div><div><div class="ep-lbl">LD cap, % of PO value</div><input class="ep-in" id="ld-cap" type="number" data-sc="ld-cap" value="' + esc(L.cap) + '"></div>' + hf('LD exposure', money(ld) + (cap && amt > cap ? ' (capped)' : '')) + '</div><div class="ep-row">' + ['Intimated to vendor', 'Settled with supplier', 'LD memo or report issued'].map(function (s) { var on = (L.steps || {})[s]; return on ? '<span class="ep-pill ok sm">' + s + ' ' + fmtDate(on) + '</span>' : '<button class="ep-btn secondary xs" data-s="ld-step" data-x="' + s + '">' + s + '</button>'; }).join('') + '</div></div>' + sList('mncr', 'MNCR — shortages and damages', ['MNCR no.', 'Description', 'Action', 'Status'], 'From Stores'); }

/* ---------- aging pop-up ---------- */
var pct = function (a, b) { return b ? Math.round(a / b * 100) : 0; };
function marks(r) { var reg = (r.reg && r.reg.rows) || [], f = reg.filter(function (x) { return !x.deleted && x.actual; }).map(function (x) { return x.actual; }).sort()[0] || ''; return [['issued', r.issuedOn, 'Issued'], ['ack', r.ackDate, 'Acknowledged'], ['docsOut', r.kickoffOn, 'Kickoff'], ['docsIn', f, 'Docs In'], ['pim', (r.mfg || {}).pimOn, 'PIM'], ['fab', (r.mfg || {}).fabStart, 'Fabrication'], ['insp', (r.mfg || {}).extInsp, 'Inspection'], ['release', (r.mfg || {}).irn, 'IRN'], ['shipped', (r.ship || {}).etd, 'Shipped'], ['delivered', (r.ship || {}).mrvOn, 'MRV'], ['mrbSub', (r.close || {}).mrbSubOn, 'MRB Sub'], ['closed', (r.close || {}).mrbApprOn, 'Closed']]; }
function railAt(r) { return { issued:0, ack:1, docsOut:2, docsIn:3, docsOk:3, pim:4, fab:5, insp:6, release:7, shipped:8, delivered:9, mrbSub:10, closed:11 }[r.stage]; }
function agingOpen(po) { var r = epExpFind(po), a = epExpAging(r), q = qty(r), m = marks(r), at = railAt(r), closed = epExpIsClosed(r), part = q.mrv > 0 && q.mrv < q.all, bar = function (t, v) { return '<div class="sx-bar"><div class="ep-row" style="justify-content:space-between;"><b>' + t + '</b><span class="tabnum">' + pct(v, q.all) + '% · ' + n(v) + ' / ' + n(q.all) + '</span></div><div class="t"><i style="width:' + pct(v, q.all) + '%"></i></div></div>'; };
  var open = (r.items || []).filter(function (x) { return ((r.clr || {})[x.item] || {}).mrv < x.qty || !(r.clr || {})[x.item]; }).length;
  var body = '<div class="sx-ag-h"><div><b>' + esc(r.po) + ' · ' + esc(r.supplierShort) + '</b><div>' + a.order + ' days since issued · ' + money(r.value) + ' · ' + esc(r.assignedTo || 'Unassigned') + '</div></div><span class="ep-pill ' + (closed ? 'slate' : part ? 'warn' : 'ok') + ' sm">' + (closed ? 'Closed' : part ? 'Partially Open' : 'Open') + '</span></div>' +
    '<div class="ep-note" style="margin:10px 0;">MODELLED: these quantities stand in until the connectors feed them.</div>' + bar('IRN issued', q.irn) + bar('Shipped', q.ship) + bar('Received (MRV)', q.mrv) +
    '<table class="ep-table" style="margin:10px 0;"><tbody><tr><td>Order aging</td><td class="tabnum"><b>' + a.order + ' days</b></td></tr><tr><td>Items cleared (MRV)</td><td class="tabnum"><b>' + ((r.items || []).length - open) + ' / ' + (r.items || []).length + '</b></td></tr><tr><td>Open item aging</td><td class="tabnum"><b>' + open + ' items · ' + a.order + ' days</b></td></tr><tr><td>Past due</td><td class="tabnum"><b>' + (a.late ? a.late + ' days · ' + a.ldLots + ' LD lot(s)' : 'None') + '</b></td></tr></tbody></table><div class="ep-lbl">Stage timeline</div><div class="sx-tl">' +
    m.map(function (x, i) { var cl = i < at ? 'done' : i === at ? 'now' : '', took = i < at && m[i + 1] && m[i + 1][1] && x[1] ? ' · took ' + dd(x[1], m[i + 1][1]) + ' days' : ''; return '<div class="sx-ts ' + cl + '"><i>' + (i < at ? '✓' : i + 1) + '</i><div><b>' + x[2] + '</b><span>' + (x[1] ? fmtDate(x[1]) + took : i === at ? 'Current' : '') + '</span></div></div>'; }).join('') + '</div>';
  modal('Aging', body, null, { foot:'<button class="ep-btn primary" id="modal-cancel">Close</button>' }); }

/* ---------- workflow actions (After) ---------- */
var WF = window.SX_WF;
function wfAuto(r, i) { return { 1:!!r.assignedTo, 3:!!r.intro, 11:!!r.kickoffOn, 8:!!r.ackDate, 5:!!(r.reg && r.reg.rows.length), 9:!!(r.sch && r.sch.frozen) }[i] || false; }
function actRows() { var out = []; seenRecs().forEach(function (r) { WF.forEach(function (w, i) { var no = i + 1, done = wfAuto(r, no) || (r.wf || {})[no]; if (done) return; if (ROLE === 'EXP' && w[2] !== 'Expeditor') return; if (ROLE === 'DOC' && w[2] !== 'Doc Expeditor') return; if (out.filter(function (o) { return o.r === r; }).length < 5) out.push({ r:r, no:no, w:w }); }); }); return out; }
function pageActions() { return '<div class="ep-card flush"><div class="ep-card-title"><span>My Actions — next five open steps per PO</span><span class="ep-sub">From your 35 workflow actions</span></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>PO</th><th>#</th><th>Type</th><th>Action</th><th>Owner</th><th></th></tr></thead><tbody>' + actRows().map(function (o) { return '<tr><td class="tabnum"><button class="link" data-s="open" data-x="' + esc(o.r.po) + '">' + esc(o.r.po) + '</button></td><td>' + o.no + '</td><td>' + o.w[0] + '</td><td>' + esc(o.w[1]) + (o.w[3] ? ' <span class="ep-pill warn sm">Pain point</span>' : '') + '</td><td>' + o.w[2] + '</td><td><button class="ep-btn secondary xs" data-s="wf" data-x="' + esc(o.r.po) + '" data-y="' + o.no + '">Done</button></td></tr>'; }).join('') + '</tbody></table></div></div>'; }

/* ---------- RAIL Action Tracker (Rolling Action Item List) with 3-Tier Escalation ---------- */
function railCalc(c) {
  if (c.status === 'CLOSED') return { tier: 0, label: 'Closed', pill: 'ok sm', days: 0 };
  if (c.status === 'PENDING_VERIFICATION') return { tier: 1.5, label: 'Pending Verification', pill: 'warn sm', days: 0 };
  var daysOver = c.target ? dd(c.target, T()) : 0;
  if (daysOver <= 0) return { tier: 1, label: 'On Track (Due ' + (c.target ? fmtDate(c.target) : 'TBD') + ')', pill: 'info sm', days: daysOver };
  if (daysOver <= 7) return { tier: 2, label: 'Overdue (Tier 1: ' + daysOver + 'd)', pill: 'warn sm', days: daysOver };
  if (daysOver <= 14) return { tier: 3, label: 'Escalated to PEXM (Tier 2: ' + daysOver + 'd)', pill: 'warn sm', days: daysOver, bg: '#fed7aa', col: '#9a3412' };
  return { tier: 4, label: 'Critical Escalation (Tier 3: ' + daysOver + 'd)', pill: 'rose sm', days: daysOver, bg: '#fee2e2', col: '#991b1b' };
}

window.RAIL_FILTER = window.RAIL_FILTER || { po: '', status: 'ALL', tier: 'ALL', assignee: 'ALL' };

function pageRail() {
  var list = (SX && SX.concerns) || [];
  var isLead = ROLE === 'EXP' || ROLE === 'PEXM';
  var flt = window.RAIL_FILTER;
  
  var active = list.filter(function (c) { return c.status !== 'CLOSED'; });
  var t1 = list.filter(function (c) { return c.status === 'OPEN' && railCalc(c).tier === 2; }).length;
  var t2 = list.filter(function (c) { return c.status === 'OPEN' && railCalc(c).tier === 3; }).length;
  var t3 = list.filter(function (c) { return c.status === 'OPEN' && railCalc(c).tier === 4; }).length;
  var pVer = list.filter(function (c) { return c.status === 'PENDING_VERIFICATION'; }).length;

  var filtered = list.filter(function (c) {
    if (flt.po && c.po !== flt.po) return false;
    if (flt.status === 'OPEN' && c.status !== 'OPEN') return false;
    if (flt.status === 'PENDING_VERIFICATION' && c.status !== 'PENDING_VERIFICATION') return false;
    if (flt.status === 'CLOSED' && c.status !== 'CLOSED') return false;
    if (flt.assignee !== 'ALL' && (c.assignedTo || c.by) !== flt.assignee) return false;
    if (flt.tier === 'T1' && railCalc(c).tier !== 2) return false;
    if (flt.tier === 'T2' && railCalc(c).tier !== 3) return false;
    if (flt.tier === 'T3' && railCalc(c).tier !== 4) return false;
    return true;
  });

  var pos = allRecs();
  var assignees = ['VENDOR', 'EXP', 'DOC', 'FIELD', 'ENGINEERING', 'PEXM'];

  var kpiGrid = '<div class="ep-kpis" style="grid-template-columns:repeat(5,1fr);margin-bottom:12px;">' +
    kp('Active Actions', active.length, 'across all POs') +
    kp('Tier 1 Overdue (1-7d)', t1, 'flagged to owner', t1 > 0) +
    kp('Tier 2 Escalation (8-14d)', t2, 'escalated to PEXM', t2 > 0) +
    kp('Tier 3 Critical (>14d)', t3, 'executive red alert', t3 > 0) +
    kp('Pending Verification', pVer, 'waiting for expeditor', pVer > 0) +
  '</div>';

  var filterBar = '<div class="ep-card" style="margin-bottom:12px;"><div class="ep-row" style="flex-wrap:wrap;gap:8px;align-items:center;">' +
    '<b>Filter:</b>' +
    '<select class="ep-in sm" data-sc="rail-flt-po" style="width:auto;"><option value="">All POs (' + pos.length + ')</option>' + pos.map(function (r) { return '<option value="' + esc(r.po) + '"' + (flt.po === r.po ? ' selected' : '') + '>' + esc(r.po) + '</option>'; }).join('') + '</select>' +
    '<select class="ep-in sm" data-sc="rail-flt-st" style="width:auto;">' +
      [['ALL', 'All Statuses'], ['OPEN', 'Open Only'], ['PENDING_VERIFICATION', 'Pending Verification (' + pVer + ')'], ['CLOSED', 'Closed']].map(function (s) { return '<option value="' + s[0] + '"' + (flt.status === s[0] ? ' selected' : '') + '>' + s[1] + '</option>'; }).join('') +
    '</select>' +
    '<select class="ep-in sm" data-sc="rail-flt-tier" style="width:auto;">' +
      [['ALL', 'All Tiers'], ['T1', 'Tier 1 Overdue (1-7d)'], ['T2', 'Tier 2 Escalated to PEXM'], ['T3', 'Tier 3 Critical (>14d)']].map(function (s) { return '<option value="' + s[0] + '"' + (flt.tier === s[0] ? ' selected' : '') + '>' + s[1] + '</option>'; }).join('') +
    '</select>' +
    '<select class="ep-in sm" data-sc="rail-flt-asg" style="width:auto;"><option value="ALL">All Assignees</option>' + assignees.map(function (a) { return '<option value="' + a + '"' + (flt.assignee === a ? ' selected' : '') + '>' + a + '</option>'; }).join('') + '</select>' +
    '<span style="flex:1;"></span>' +
    '<button class="ep-btn primary sm" data-s="rail-add">+ New Action Item</button>' +
  '</div></div>';

  var rowsHtml = filtered.map(function (c) {
    var escObj = railCalc(c);
    var badgeStyle = escObj.bg ? ' style="background:' + escObj.bg + ';color:' + escObj.col + ';font-weight:600;"' : '';
    var stPill = c.status === 'CLOSED' ? '<span class="ep-pill ok sm">Closed</span>' : c.status === 'PENDING_VERIFICATION' ? '<span class="ep-pill warn sm">Pending Verification</span>' : '<span class="ep-pill info sm">Open</span>';
    var asgPill = '<span class="ep-pill slate sm">' + esc(c.assignedTo || c.by || 'EXP') + '</span>';
    
    var actBtns = '';
    if (c.status === 'OPEN') {
      actBtns += '<button class="ep-btn primary xs" data-s="rail-res" data-x="' + c.id + '" style="margin-right:4px;">Resolve</button>';
      if (isLead) actBtns += '<button class="ep-btn secondary xs" data-s="rail-rebase" data-x="' + c.id + '" style="margin-right:4px;">Re-baseline</button>';
    } else if (c.status === 'PENDING_VERIFICATION') {
      if (isLead) {
        actBtns += '<button class="ep-btn primary xs" data-s="rail-verify" data-x="' + c.id + '" style="margin-right:4px;">Verify & Close</button>';
        actBtns += '<button class="ep-btn secondary xs danger" data-s="rail-reopen" data-x="' + c.id + '" style="margin-right:4px;">Reject</button>';
      } else {
        actBtns += '<span class="ep-sub">Pending Lead Review</span>';
      }
    }
    actBtns += '<button class="ep-btn secondary xs" data-s="rail-hist" data-x="' + c.id + '">History</button>';

    return '<tr>' +
      '<td class="tabnum"><b>' + esc(c.no) + '</b></td>' +
      '<td class="tabnum"><button class="link" data-s="open" data-x="' + esc(c.po) + '">' + esc(c.po) + '</button><div class="ep-sub">' + esc(c.assignedVendor || '') + '</div></td>' +
      '<td><b>' + esc(c.issue) + '</b><div class="ep-sub">Source: ' + esc(c.source || 'Manual') + (c.evidence ? ' · Evidence: ' + esc(c.evidence) : '') + '</div></td>' +
      '<td>' + asgPill + '</td>' +
      '<td><span class="ep-pill ' + escObj.pill + '"' + badgeStyle + '>' + escObj.label + '</span></td>' +
      '<td>' + stPill + '</td>' +
      '<td>' + actBtns + '</td>' +
    '</tr>';
  }).join('') || '<tr><td colspan="7" class="ep-sub" style="padding:14px;text-align:center;">No matching actions found.</td></tr>';

  var tableCard = '<div class="ep-card flush">' +
    '<div class="ep-card-title"><span>Rolling Action Item List (RAIL) — ' + filtered.length + ' item(s)</span></div>' +
    '<div style="overflow-x:auto;">' +
      '<table class="ep-table">' +
        '<thead><tr><th>Ref #</th><th>PO & Vendor</th><th>Finding / Action Required</th><th>Assigned To</th><th>Target Date & Escalation Tier</th><th>Status</th><th>Actions</th></tr></thead>' +
        '<tbody>' + rowsHtml + '</tbody>' +
      '</table>' +
    '</div>' +
  '</div>';

  return kpiGrid + filterBar + tableCard;
}

function pageConcern() { return pageRail(); }

/* ---------- dashboard and queue ---------- */
function scurve(rows) { rows = rows.filter(function (a) { return a.bE && !a.na; }); if (!rows.length) return ''; var ds = rows.map(function (a) { return a.bE; }).sort(), s = ds[0], e = ds[ds.length - 1], N = 12, sp = Math.max(1, dd(s, e)), pts = []; for (var i = 0; i <= N; i++) pts.push(ad(s, Math.round(sp * i / N))); var pl = pts.map(function (d) { return rows.filter(function (a) { return a.bE <= d; }).length / rows.length * 100; }), ac = pts.filter(function (d) { return d <= T(); }).map(function (d) { return rows.filter(function (a) { return a.pct === '100' && a.fE <= d; }).length / rows.length * 100; });
  var X = function (i) { return 46 + i * (590 / N); }, Y = function (v) { return 190 - v * 1.7; }, ln = function (a) { return a.map(function (v, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); }).join(' '); };
  return '<svg viewBox="0 0 650 224" role="img" aria-label="Planned against actual cumulative progress" style="width:100%;height:auto;max-height:280px;">' + [0, 25, 50, 75, 100].map(function (v) { return '<line x1="46" x2="636" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="#e2e8f0"/><text x="38" y="' + (Y(v) + 4) + '" text-anchor="end" font-size="11" fill="#64748b">' + v + '%</text>'; }).join('') + [0, 6, 12].map(function (i) { return '<text x="' + X(i) + '" y="212" text-anchor="' + (i === 12 ? 'end' : i ? 'middle' : 'start') + '" font-size="11" fill="#64748b">' + fmtDate(pts[i]) + '</text>'; }).join('') + '<path d="' + ln(pl) + '" fill="none" stroke="#94a3b8" stroke-width="2"/><path d="' + ln(ac) + '" fill="none" stroke="#d97706" stroke-width="2.5"/></svg><div class="ep-row ep-sub"><span>■ Planned (grey)</span><span style="color:#b45309">■ Actual</span></div>'; }
function pageDash() { var L = allRecs(), late = 0, ldl = 0; L.forEach(function (r) { var a = epExpAging(r); late += a.lateLots; ldl += a.ldLots; }); var loads = EP_EXP_TEAM.map(function (t) { return { n:t.name, l:epExpLoadOf(t.name, L).total }; }).sort(function (a, b) { return a.l - b.l; });
  var tabs = AFTER ? '<div class="ep-subtabs">' + [['overview', 'Overview'], ['actions', 'My Actions'], ['concern', 'Areas of Concern']].map(function (x) { return '<button data-s="dash" data-x="' + x[0] + '" class="' + (DASH === x[0] ? 'on' : '') + '">' + x[1] + '</button>'; }).join('') + '</div>' : '';
  if (DASH === 'actions') return tabs + pageActions(); if (DASH === 'concern') return tabs + pageConcern();
  return tabs + '<div class="ep-kpis" style="grid-template-columns:repeat(5,1fr);">' + kp('Active POs', L.filter(function (r) { return !epExpIsClosed(r); }).length, 'in expediting') + kp('Waiting assignment', L.filter(function (r) { return !r.assignedTo; }).length, 'with PExM') + kp('Critical sub-orders', allCrit(), 'negative float', allCrit() > 0) + kp('Overdue reviews', allOverdue(), 'past 14-day SLA', allOverdue() > 0) + kp('Late lots', late, ldl + ' under LD', late > 0) + '</div>' +
    '<div class="ep-card"><div class="ep-card-title">Schedule S-curve</div>' + scurve([].concat.apply([], L.filter(function (r) { return r.sch; }).map(function (r) { return r.sch.rows; }))) + '</div>' +
    '<div class="ep-card flush"><div class="ep-card-title"><span>PO allocation</span><span class="ep-sub">Lowest load: ' + loads.slice(0, 3).map(function (x) { return x.n + ' ' + x.l; }).join(' · ') + '</span></div><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>PO</th><th>Vendor</th><th>Value</th><th>Stage</th><th>Expeditor</th><th>Aging</th></tr></thead><tbody>' + L.map(function (r) { return '<tr><td class="tabnum"><button class="link" data-s="open" data-x="' + esc(r.po) + '">' + esc(r.po) + '</button></td><td>' + esc(r.supplierShort) + '</td><td class="tabnum">' + money(r.value) + '</td><td>' + esc(epExpStatusLabel(r)) + '</td><td>' + esc(r.assignedTo || '—') + '</td><td><button class="link" data-s="age" data-x="' + esc(r.po) + '">' + epExpAging(r).order + ' days</button></td></tr>'; }).join('') + '</tbody></table></div></div>'; }
function pageQueue() { var L = allRecs(), w = L.filter(function (r) { return !r.assignedTo; }), p = L.filter(function (r) { return r.assignedTo && !epExpIsClosed(r); }), c = L.filter(epExpIsClosed), list = { wait:w, prog:p, closed:c }[QTAB];
  return '<div class="ep-kpis" style="grid-template-columns:repeat(3,1fr);">' + kp('Waiting assignment', w.length, 'issued POs') + kp('In progress', p.length, 'assigned') + kp('Closed', c.length, 'MRB approved') + '</div><div class="ep-subtabs">' + [['wait', 'Waiting Assignment'], ['prog', 'Assigned — In Progress'], ['closed', 'Closed']].map(function (x) { return '<button data-s="qt" data-x="' + x[0] + '" class="' + (QTAB === x[0] ? 'on' : '') + '">' + x[1] + '</button>'; }).join('') + '</div><div class="ep-card flush"><div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>PO</th><th>Supplier</th><th>MR · Project</th><th>Value</th><th>Issued</th><th>Expeditor</th><th>Stage</th><th>Aging</th><th></th></tr></thead><tbody>' +
    (list.map(function (r) { var q = qty(r); return '<tr><td class="tabnum">' + esc(r.po) + '</td><td>' + esc(r.supplierShort) + '</td><td>' + esc(r.mrRef) + ' · ' + esc(r.project) + '</td><td class="tabnum">' + money(r.value) + '</td><td>' + fmtDate(r.issuedOn) + '</td><td>' + esc(r.assignedTo || '—') + '</td><td>' + (railAt(r) + 1) + ' of 12 · ' + esc(epExpStatusLabel(r)) + '</td><td><button class="link" data-s="age" data-x="' + esc(r.po) + '">' + epExpAging(r).order + ' days</button><div class="ep-sub">' + pct(q.mrv, q.all) + '% received</div></td><td>' + (r.assignedTo ? '<button class="ep-btn secondary xs" data-s="open" data-x="' + esc(r.po) + '">Open</button>' : (ROLE === 'PEXM' ? '<button class="ep-btn primary xs" data-s="asg" data-x="' + esc(r.po) + '">Assign</button>' : '')) + '</td></tr>'; }).join('') || '<tr><td colspan="9" class="ep-sub">Nothing here.</td></tr>') + '</tbody></table></div></div>'; }
function assignModal(po) { var L = allRecs(), r = epExpFind(po), team = EP_EXP_TEAM.map(function (t) { var l = epExpLoadOf(t.name, L), od = 0; L.filter(function (q) { return q.assignedTo === t.name; }).forEach(function (q) { Object.keys(q.rvw || {}).forEach(function (k) { if (rvOver(q.rvw[k])) od++; }); }); return { n:t.name, l:l, od:od }; }).sort(function (a, b) { return a.l.total - b.l.total; }), max = Math.max.apply(null, team.map(function (t) { return t.l.total; })), low = team[0].l.total;
  var card = function (t, i) { var w = Math.round(t.l.total / max * 100), tone = t.l.total <= low + 3 ? '#059669' : t.l.total >= max - 3 ? '#e11d48' : '#f59e0b';
    return '<label class="sx-pk"><input type="radio" name="m-exp" value="' + t.n + '"' + (i === 0 ? ' checked' : '') + '><span class="sx-pk-c"><span class="sx-pk-a">' + esc(t.n.slice(0, 2).toUpperCase()) + '</span><span class="sx-pk-b"><span class="sx-pk-n">' + esc(t.n) + (i === 0 ? ' <span class="ep-pill ok sm">Suggested</span>' : '') + '</span><span class="sx-pk-m"><b class="tabnum">' + t.l.total + '</b> open POs' + (t.l.mine ? ' · ' + t.l.mine + ' in this demo' : '') + (t.od ? ' · <span style="color:#be123c">' + t.od + ' overdue reviews</span>' : '') + '</span><span class="sx-pk-bar"><i style="width:' + w + '%;background:' + tone + '"></i></span></span></span></label>'; };
  modal('Assign ' + po, '<div class="sx-pk-po"><b>' + esc(r.supplierShort || r.supplier) + '</b> · ' + esc(r.head || '') + ' · ' + money(r.value, r.ccy) + '</div><div class="ep-sub" style="margin:8px 0;">Pick an expeditor. Lowest workload first; open-PO counts are MODELLED.</div><div class="sx-pk-g" role="radiogroup" aria-label="Expeditor">' + team.map(card).join('') + '</div>', function () { var sel = document.querySelector('input[name="m-exp"]:checked'); if (!sel) return toast('Pick an expeditor.'); epExpAssign(po, sel.value, 'Mr. Huzaifa'); var list = epExpLoad(), k = list.findIndex(function (x) { return x.po === po; }); if (!list[k].sch) { setupSched(list[k]); epExpSave(list); } closeModal(); render(); toast('Assigned to ' + sel.value + '.'); }, { wide:'wide' }); }

/* ---------- overrides ---------- */
function downloadMiniXlsx(bytes, filename) { (window.claude && window.claude.use ? window.claude.use('downloads') : Promise.resolve(null)).then(function (d) { if (!d) return toast('Downloads are not available in this view.'); return d.save({ filename:filename, data:new Blob([bytes], { type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }) }); }).catch(function (e) { if (!e || e.code !== 'declined') toast('The download did not start.'); }); }
var TABS = {
  core: [['head', 'Order Head'], ['sched', 'Manufacturing Schedule'], ['docs', 'Document Control VDR'], ['plan', 'Sub-Orders & Float'], ['insp', 'Inspection (IMS)'], ['deliv', 'Delivery & Stores'], ['letter', 'Introduction Letter'], ['mr', 'MR Study']].concat(AFTER ? [['log', 'Follow-up Log']] : []),
  sub: [['plan', 'Submit Procurement Plan'], ['analysis', 'Analysis']],
  insp: [['iap', 'IAP'], ['irn', 'IRN'], ['pim', 'PIM']].concat(AFTER ? [['notif', 'Notifications'], ['punch', 'Punch List']] : []),
  deliv: [['deliv', 'Delivery']].concat(AFTER ? [['dispatch', 'Dispatch Actions']] : []),
  exec: [['sched', 'Manufacturing Schedule'], ['progress', AFTER ? 'Progress Report (MSSR)' : 'Progress Report']].concat(AFTER ? [['closex', 'Closeout']] : []),
  portal: [['letter', 'Respond to Notification'], ['docs', 'SDR Portal'], ['sched', 'Manufacturing Schedule'], ['plan', 'Submit Procurement Plan'], ['vnotif', 'Raise Inspection Notification'], ['actions', 'My Actions']]
};
function tabList() { var g = revGroup(); if (g) return [{ k:'docs', t:'Documents to Review' }]; var chk = REC && REC.reg ? epRegCheck(REC).filter(function (c) { return c.sev === 'rose'; }).length : 0; return (TABS[SEC] || []).map(function (x) { var o = { k:x[0], t:x[1] }; if (x[0] === 'docs' && SEC !== 'portal') { o.n = chk; o.rose = true; } if (x[0] === 'letter' && SEC === 'portal' && REC && REC.intro) { o.n = epLetterOpen(REC).length; o.rose = true; } return o; }); }
var NAV = [['dash', 'Executive Dashboard'], ['queue', 'PO Master Register'], ['core', 'Expeditor Workbench'], ['rail', 'RAIL Action Tracker'], ['field', 'Field Expediting']];
function render() {
  var ven = isV(), g = revGroup(), isField = ROLE === 'FIELD', isDoc = ROLE === 'DOC';
  if (ven) SEC = 'portal';
  if (g) SEC = 'core';
  if (isField && (!SEC || SEC === 'dash' || SEC === 'portal')) SEC = 'field';
  if (isDoc && (!SEC || SEC === 'dash' || SEC === 'portal')) { SEC = 'core'; if (!TAB) TAB = 'docs'; }
  if (SEC === 'portal' && !ven) SEC = 'dash';
  var nav = ven || g ? [] : NAV;
  $('sx-nav').innerHTML = (ven ? '<div class="sx-vh">Vendor Portal</div>' : g ? '<div class="sx-vh">Document Review</div>' : '') + nav.map(function (x) { return '<button class="sx-n ' + (x[0] === SEC ? 'on' : '') + '" data-s="nav" data-x="' + x[0] + '">' + x[1] + '</button>'; }).join('');
  $('sx-role').innerHTML = Object.keys(ROLES).map(function (k) { return '<option value="' + esc(k) + '"' + (k === ROLE ? ' selected' : '') + '>' + esc(ROLES[k]) + '</option>'; }).join('');
  var perPO = ['core', 'sub', 'insp', 'deliv', 'exec', 'portal'].indexOf(SEC) >= 0;
  $('wk').hidden = !perPO; $('sx-page').hidden = perPO;
  $('sx-alert').textContent = 'Alerts (' + alertList().length + ')';
  if (!perPO) { $('sx-pos').innerHTML = ''; $('sx-h').textContent = TABSLABEL(); $('sx-page').innerHTML = SEC === 'dash' ? pageDash() : SEC === 'rail' ? pageRail() : (window.SX_PAGEFN || {})[SEC] ? window.SX_PAGEFN[SEC]() : pageQueue(); notifyParentNav(); return; }
  var L = seenRecs(); if (g) L = allRecs().filter(function (r) { return Object.keys(r.rvw || {}).some(function (k) { return r.rvw[k].reviews.some(function (x) { return x.group === g; }); }); });
  if (!L.length) { $('sx-h').textContent = TABSLABEL(); $('sx-pos').innerHTML = ''; $('title').textContent = 'No orders here'; $('sub').textContent = 'Nothing is assigned to this view yet.'; $('tabs').innerHTML = ''; $('content').innerHTML = ''; return; }
  if (!L.some(function (r) { return r.po === PO; })) PO = L[0].po;
  REC = epExpFind(PO); VIEW = ven ? 'vendor' : 'npcc';
  $('sx-h').textContent = TABSLABEL();
  $('sx-pos').innerHTML = '<label class="ep-sub" for="sx-po">PO</label><select id="sx-po" class="ep-in" data-sc="po">' + L.map(function (r) { return '<option' + (r.po === PO ? ' selected' : '') + '>' + esc(r.po) + '</option>'; }).join('') + '</select>';
  $('title').innerHTML = esc(REC.po) + ' — ' + esc(REC.supplierShort || REC.supplier) + (ven ? '' : ' <button class="link sx-aging" data-s="age" data-x="' + esc(REC.po) + '">' + epExpAging(REC).order + ' days aging</button>');
  $('sub').textContent = 'MR ' + REC.mrRef + ' · Project ' + REC.project + ' · ' + REC.head + (ven ? '' : ' · ' + money(REC.value) + (REC.assignedTo ? ' · Expeditor: ' + REC.assignedTo : ''));
  renderTabs(); SECTAB[SEC] = TAB;
  if (SUB.sched === 'subs') SUB.sched = 'act';
  var map = { head:tabHeadX, mr:tabMrX, docs:tabDocsX, sched:tabSchedX, log:tabLog, letter:tabLetterX, plan:tabPlan, analysis:tabAnalysis, iap:tabIap, irn:tabIrn, pim:tabPim, notif:tabNotif, punch:tabPunch, deliv:tabDeliv, dispatch:tabDispatch, progress:AFTER ? tabMssrSafe : tabProgress, closex:tabCloseX, vnotif:tabVendorNotif, actions:tabVendorActions };
  var sx = window.scrollY; if (TAB === 'sched' || TAB === 'progress') epSchInit(REC);
  $('content').innerHTML = ((window.SX_TABFN || {})[TAB] || map[TAB] || map[Object.keys(map)[0]])(); window.scrollTo(0, sx);
  notifyParentNav();
}

function tabVendorActions() {
  var list = ((SX && SX.concerns) || []).filter(function (c) {
    return c.po === REC.po || c.assignedTo === 'VENDOR' || c.assignedVendor === REC.supplierShort || c.assignedVendor === REC.supplier;
  });
  return '<div class="ep-note"><b>My Actions (RAIL) — Action Items Assigned to Vendor</b><br>Track findings from shop expediting visits, document reviews, and schedule updates. When an action is completed, submit your resolution and evidence for Expeditor verification and closeout.</div>' +
    '<div class="ep-card flush">' +
      '<div class="ep-card-title"><span>Assigned Action Items for PO ' + esc(REC.po) + '</span><span class="ep-sub">' + list.filter(function (c) { return c.status !== 'CLOSED'; }).length + ' open</span></div>' +
      '<div style="overflow-x:auto;">' +
        '<table class="ep-table">' +
          '<thead><tr><th>Ref #</th><th>Finding / Action Required</th><th>Source</th><th>Target Date</th><th>Status</th><th>Action</th></tr></thead>' +
          '<tbody>' +
            (list.map(function (c) {
              var escObj = railCalc(c);
              var badgeStyle = escObj.bg ? ' style="background:' + escObj.bg + ';color:' + escObj.col + ';font-weight:600;"' : '';
              var stPill = c.status === 'CLOSED' ? '<span class="ep-pill ok sm">Verified & Closed</span>' : c.status === 'PENDING_VERIFICATION' ? '<span class="ep-pill warn sm">Submitted — Awaiting Expeditor Verification</span>' : '<span class="ep-pill info sm">Open</span>';
              var btn = c.status === 'OPEN' ? '<button class="ep-btn primary xs" data-s="rail-res" data-x="' + c.id + '">Submit Close-out & Evidence</button>' : '<button class="ep-btn secondary xs" data-s="rail-hist" data-x="' + c.id + '">View History</button>';
              return '<tr>' +
                '<td class="tabnum"><b>' + esc(c.no) + '</b></td>' +
                '<td><b>' + esc(c.issue) + '</b>' + (c.resolution ? '<div class="ep-sub" style="color:#059669;margin-top:2px;">Submitted: ' + esc(c.resolution) + '</div>' : '') + '</td>' +
                '<td><span class="ep-pill slate sm">' + esc(c.source || 'Expediting') + '</span></td>' +
                '<td><span class="ep-pill ' + escObj.pill + '"' + badgeStyle + '>' + (c.target ? fmtDate(c.target) : '—') + '</span></td>' +
                '<td>' + stPill + '</td>' +
                '<td>' + btn + '</td>' +
              '</tr>';
            }).join('') || '<tr><td colspan="6" class="ep-sub" style="padding:14px;">No open actions assigned to your company.</td></tr>') +
          '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>';
}
/* ---------- 3. Vendor Portal: Raise Inspection Notification ---------- */
function tabVendorNotif() {
  var notifs = (REC.sx && REC.sx.notif) || [];
  var items = REC.items || [];
  return '<div class="ep-note"><b>Vendor Inspection Notification (NOI)</b> — Raise your inspection request here. It will immediately route to the Inspection Manager and QA/QC team in InspectFlow for inspector dispatch and assignment.</div>' +
    '<div class="ep-card">' +
      '<div class="ep-card-title"><span>Raise Notice of Inspection</span><button class="ep-btn primary sm" data-s="vnotif-new">+ New Inspection Notification</button></div>' +
      '<div class="ep-fields" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px;">' +
        hf('Purchase Order', esc(REC.po)) +
        hf('Supplier', esc(REC.supplierShort || REC.supplier)) +
        hf('Delivery Point / Works', esc(REC.deliveryPoint || 'Vendor Works')) +
      '</div>' +
      '<div class="ep-sub">When your manufactured line items are ready for Pre-Inspection Meeting (PIM), Factory Acceptance Test (FAT), Final Inspection, or Release Note (IRN), submit an NOI at least 5 working days in advance.</div>' +
    '</div>' +
    '<div class="ep-card flush">' +
      '<div class="ep-card-title"><span>Inspection Notifications for PO ' + esc(REC.po) + '</span></div>' +
      '<div style="overflow-x:auto;">' +
        '<table class="ep-table">' +
          '<thead><tr><th>Activity / NOI Ref</th><th>Type</th><th>Requested Date</th><th>Status</th><th>Destination</th><th></th></tr></thead>' +
          '<tbody>' +
            (notifs.map(function (n) {
              var isDraft = n.Status === 'Draft' || !n.Status;
              var canDel = isDraft && VIEW === 'vendor' && (typeof subCur !== 'function' || subEditable(subCur('vnotif', true)));
              return '<tr><td><b>' + esc(n.Activity) + '</b></td><td><span class="ep-pill info sm">' + esc(n.Type) + '</span></td><td class="tabnum">' + fmtDate(n['Requested date']) + '</td><td><span class="ep-pill ' + (isDraft ? 'warn' : 'ok') + ' sm">' + esc(n.Status || 'Draft') + '</span></td><td><span class="ep-pill slate sm">InspectFlow (IMS)</span></td><td>' + (canDel ? '<button class="ep-btn xs danger" data-s="vn-del" data-x="' + esc(n.id || n.Activity) + '">Remove</button>' : '') + '</td></tr>';
            }).join('') || '<tr><td colspan="6" class="ep-sub">No inspection notifications raised yet. Click "+ New Inspection Notification" above to draft one.</td></tr>') +
          '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>';
}

function vnotifModal() {
  var items = REC.items || [];
  var nextNo = 'NOI-' + esc(REC.po) + '-' + String(((REC.sx && REC.sx.notif) || []).length + 1).padStart(3, '0');
  var itemsOptions = items.map(function (it) {
    return '<option value="' + esc(it.item) + '">' + esc(it.item) + ' — ' + esc((it.desc || '').slice(0, 50)) + ' (Qty: ' + esc(it.qty) + ')</option>';
  }).join('');

  modal('Raise Notice of Inspection (NOI)',
    '<div class="ep-sub" style="margin-bottom:10px;">This notification will be transmitted directly into InspectFlow for Inspector Engineer and QA/QC assignment.</div>' +
    '<div class="ep-fields" style="grid-template-columns:1fr 1fr;">' +
      '<div><div class="ep-lbl">Notification Number</div><input class="ep-in" id="vn-no" value="' + nextNo + '"></div>' +
      '<div><div class="ep-lbl">Inspection Type</div><select class="ep-in" id="vn-type"><option>Witness</option><option>Hold</option><option>Review</option><option>PIM (Pre-Inspection Meeting)</option><option>FAT (Factory Acceptance Test)</option><option>Final & Release (IRN)</option></select></div>' +
    '</div>' +
    '<div class="ep-fields" style="grid-template-columns:1fr 1fr;margin-top:8px;">' +
      '<div><div class="ep-lbl">Requested Inspection Date</div><input type="date" class="ep-in" id="vn-date" value="' + ad(T(), 7) + '"></div>' +
      '<div><div class="ep-lbl">Inspection Location / Workshop</div><input class="ep-in" id="vn-loc" value="' + esc(REC.deliveryPoint || 'Vendor Workshop') + '"></div>' +
    '</div>' +
    '<div style="margin-top:8px;">' +
      '<div class="ep-lbl">Offered Line Item</div>' +
      '<select class="ep-in" id="vn-item">' + itemsOptions + '</select>' +
    '</div>' +
    '<div style="margin-top:8px;">' +
      '<div class="ep-lbl">Inspection Scope / Remarks</div>' +
      '<textarea class="ep-ta" id="vn-scope" rows="3" placeholder="Specify items offered, ITP reference clause, test equipment readiness..."></textarea>' +
    '</div>',
    async function () {
      var notifNo = $('vn-no').value.trim() || nextNo;
      var inspType = $('vn-type').value;
      var reqDate = $('vn-date').value || T();
      var loc = $('vn-loc').value.trim();
      var selItem = $('vn-item').value;
      var scope = $('vn-scope').value.trim();

      // 1. Save in SmartExpedit PO record as Draft (does not lock the tab; locking occurs on final Submit)
      REC.sx = REC.sx || {};
      REC.sx.notif = REC.sx.notif || [];
      var newEntry = {
        id: epXId(),
        Activity: notifNo + ' — Item ' + selItem + (scope ? ' (' + scope + ')' : ''),
        Type: inspType,
        'Requested date': reqDate,
        Location: loc,
        Item: selItem,
        Scope: scope,
        Status: 'Draft'
      };
      REC.sx.notif.push(newEntry);
      saveRec();
      closeModal();
      render();
      toast('Inspection notification ' + notifNo + ' added to draft list. Click "Submit to the expeditor" when ready.');
    },
    { wide: 'wide' }
  );
}

function TABSLABEL() { var n = NAV.find(function (x) { return x[0] === SEC; }); return n ? n[1] : (isV() ? 'Vendor Portal' : 'Document Review'); }
function tabMssrSafe() { if (!REC.sch) epSchInit(REC); return tabMssr(); }
function tabSchedX() { return tabSched().replace(/<button data-sub="subs"[^>]*>[^<]*<\/button>/, ''); }
function tabDocsX() { if (revGroup()) return reviewCard(); return tabDocs() + (REC.reg ? reviewCard() : '') + (AFTER && REC.reg && VIEW !== 'vendor' ? dateCheck() : ''); }
function tabMrX() { var h = tabMr(); if (!AFTER) return h; var it = ['Technical requirements', 'BOM matrix', 'HOLDs', 'Optional scope', 'Design inputs', 'HAZOP', 'SIL', 'PIM', 'Document requirements', 'PBG', 'LC requirement']; var m = REC.mrx = REC.mrx || {}; return '<div class="ep-card"><div class="ep-card-title">PO and MR review checklist <span class="ep-sub">Workflow action 2</span></div><div class="sx-chk">' + it.map(function (t) { return '<label><input type="checkbox" id="mrx-' + t.replace(/\W/g, '') + '" data-sc="mrx" data-x="' + t + '"' + (m[t] ? ' checked' : '') + '> ' + t + '</label>'; }).join('') + '</div></div>' + h; }
function tabHeadX() { var h = tabHead(); if (!AFTER) return h; var a = REC.ackx = REC.ackx || { st:REC.ackDate ? 'Unconditional' : 'Pending', pts:'' }; return '<div class="ep-card"><div class="ep-card-title">PO acknowledgement <span class="ep-sub">Workflow action 8</span></div><div class="ep-fields" style="grid-template-columns:1fr 2fr;"><div><div class="ep-lbl">Status</div><select class="ep-in" id="ack-st" data-sc="ack">' + ['Pending', 'With comments', 'Unconditional'].map(function (s) { return '<option' + (s === a.st ? ' selected' : '') + '>' + s + '</option>'; }).join('') + '</select></div><div><div class="ep-lbl">Open points for the buyer to settle</div><input class="ep-in" id="ack-pts" data-sc="ackp" value="' + esc(a.pts) + '"></div></div></div>' + h; }
function letterInternal() { if (!REC.intro) return '<div class="ep-card ep-empty"><div class="big">No introduction letter yet</div><div class="ep-sub" style="margin-bottom:14px;">Generated from the order. The vendor answers each point on the portal.</div><button class="ep-btn primary" data-act="letter">Prepare and send the letter</button></div>'; return '<div class="ep-card"><div class="ep-card-title">Introduction letter — vendor replies</div>' + letterReplies() + '</div><div class="ep-card">' + letterText(REC.intro, REC.intro.points) + '</div>'; }
function tabLetterX() { if (VIEW === 'vendor') return tabLetter(); var h = letterInternal(); if (!AFTER) return h; var d = REC.dc = REC.dc || {}; return h + '<div class="ep-card"><div class="ep-card-title">Doc Controller <span class="ep-sub">Workflow action 4</span></div><div class="ep-row" style="justify-content:space-between;"><span>Document templates and VDMS login issued to the vendor</span>' + (d.on ? '<span class="ep-pill ok sm">Issued ' + fmtDate(d.on) + '</span>' : '<button class="ep-btn secondary xs" data-s="dc">Mark issued</button>') + '</div></div>'; }
function dateCheck() { var rows = REC.reg.rows.filter(function (r) { return !r.deleted && r.planned; }), appr = (REC.sch.rows.find(function (r) { return /approval/.test(r.act); }) || {}).bE, c1 = rows.filter(function (r) { return String(r.cls) === '1' && appr && r.planned > appr; }), c3 = rows.filter(function (r) { var fc = rows.filter(function (q) { return String(q.cls) === '1'; }).map(function (q) { return q.planned; }).sort()[0]; return String(r.cls) === '3' && fc && r.planned <= fc; }); return '<div class="ep-card"><div class="ep-card-title">Date check against the schedule <span class="ep-sub">Workflow action 6</span></div><div class="ep-sub">' + c1.length + ' class 1 document(s) are planned after the approval milestone' + (appr ? ' (' + fmtDate(appr) + ')' : '') + '. ' + c3.length + ' class 3 document(s) are not deferred behind the first class 1 document.</div></div>'; }
function alertList() {
  var a = [], ven = isV();
  if (ven) {
    (SX.notes || []).forEach(function (x) {
      if (x.to === ROLE || (REC && x.to === 'VEN:' + REC.po) || x.to === 'VENDOR') {
        a.push({ po: x.po, sec: x.sec || 'portal', tab: x.tab || 'sched', t: x.t, subId: x.subId, tone: 'info' });
      }
    });
    allRecs().forEach(function (r) {
      (r.subs || []).forEach(function (s) {
        if (s.status === 'Returned') {
          var stab = s.type === 'vnotif' ? 'vnotif' : s.type;
          a.push({
            po: r.po,
            sec: 'portal',
            tab: stab,
            subId: s.id,
            t: r.po + ': ' + (typeof SUBT !== 'undefined' && SUBT[s.type] ? SUBT[s.type] : s.type) + ' returned with comments',
            tone: 'warn'
          });
        }
      });
    });
    return a;
  }
  allRecs().forEach(function (r) {
    var secTabMap = {
      vpr: { sec:'exec', tab:'vpr' },
      sched: { sec:'exec', tab:'sched' },
      letter: { sec:'core', tab:'letter' },
      docs: { sec:'core', tab:'docs' },
      plan: { sec:'sub', tab:'plan' },
      vnotif: { sec:'insp', tab:'notif' }
    };
    (r.subs || []).forEach(function (s) {
      if (s.status === 'Submitted') {
        var m = secTabMap[s.type] || { sec:'exec', tab:'vpr' };
        a.push({
          po: r.po,
          sec: m.sec,
          tab: m.tab,
          subId: s.id,
          t: r.po + ': ' + (typeof SUBT !== 'undefined' && SUBT[s.type] ? SUBT[s.type] : s.type) + ' submitted by vendor (Round ' + s.round + ')',
          tone: 'info'
        });
      }
    });
    Object.keys(r.rvw || {}).forEach(function (k) {
      if (rvOver(r.rvw[k])) a.push({ po:r.po, sec:'core', tab:'docs', t:r.po + ': a document review is past the 14-day SLA', tone:'warn' });
    });
    if (r.plan && plCheck(r).crit) a.push({ po:r.po, sec:'sub', tab:'plan', t:r.po + ': ' + plCheck(r).crit + ' sub-orders have negative float', tone:'warn' });
  });
  (SX.notes || []).forEach(function (x) {
    if (!x.to || x.to === ROLE || x.to === 'EXP') {
      if (!a.some(function (exist) { return exist.subId && exist.subId === x.subId; })) {
        a.push({ po: x.po, sec: x.sec || 'exec', tab: x.tab || 'sched', t: x.t, subId: x.subId, tone: 'info' });
      }
    }
  });
  return a;
}

/* ---------- events ---------- */
document.addEventListener('click', function (ev) {
  var t = ev.target.closest('[data-s]'); if (!t) { var al = document.getElementById('sx-pop'); if (al && !ev.target.closest('#sx-alert')) al.hidden = true; return; }
  var a = t.getAttribute('data-s'), x = t.getAttribute('data-x'), y = t.getAttribute('data-y'), P = REC && REC.plan;
  var row = function () { return P.rows.find(function (r) { return r.id === x; }); };
  switch (a) {
    case 'nav': SEC = x; TAB = SECTAB[x] || ''; if (SEC === 'dash') DASH = 'overview'; render(); window.scrollTo(0, 0); return;
    case 'dash': DASH = x; return render(); case 'qt': QTAB = x; return render(); case 'age': return agingOpen(x); case 'asg': return assignModal(x);
    case 'open': PO = x; SEC = 'core'; TAB = 'head'; render(); window.scrollTo(0, 0); return;
    case 'al-go': var p = x.split('|'); PO = p[0]; SEC = p[1] || 'core'; TAB = p[2] || 'head'; SECTAB[SEC] = TAB;
      if (p[3] && typeof FX !== 'undefined') { FX.subSel = FX.subSel || {}; FX.subSel[p[3]] = p[3]; var sObj = typeof subFind === 'function' ? subFind(p[3]) : null; if (sObj) { FX.subSel[sObj.type] = sObj.id; if (sObj.type === 'vpr') FX.vprSel = sObj.id; } }
      var alPop = $('sx-pop'); if (alPop) alPop.hidden = true; render(); window.scrollTo(0, 0); return;
    case 'alert': var p = $('sx-pop'); p.innerHTML = alertList().map(function (n) {
      return '<button class="sx-al" data-s="al-go" data-x="' + esc(n.po + '|' + (n.sec || 'core') + '|' + (n.tab || 'head') + (n.subId ? '|' + n.subId : '')) + '">' +
        '<div style="font-weight:600;color:' + (n.tone === 'warn' ? '#b45309' : '#1e293b') + ';">' + esc(n.t) + '</div>' +
        '<div class="ep-sub" style="font-size:11px;margin-top:2px;">' + esc(n.po) + ' · Click to open ' + (n.tab || '') + '</div>' +
      '</button>';
    }).join('') || '<div class="ep-sub" style="padding:10px;">No alerts.</div>'; p.hidden = !p.hidden; return;
    case 'reset': epExpSave([]); seedAll(); render(); return toast('Sample data restored.');
    case 'chlog': return REC && REC.reg ? changeLogModal() : toast('No register yet.');
    case 'dsub': return dSubmit(x); case 'dnoc': return dResp(x, 'NO_COMMENT'); case 'dcom': return ask('Comment', 'Your comment goes to the expeditor.', 'Comment', function (v) { closeModal(); dResp(x, 'COMMENTED', v); });
    case 'dret': return dReturn(x); case 'dacc': return dAccept(x);
    case 'pl-add': P.rows.push({ id:epXId(), x:{}, m:{ item:{ by:WHO(), side:SIDE(), on:epXNow(), old:'' } }, deleted:null, item:'New item', qty:'TBC', dep:'', depDays:'', over:'', overWhy:'', transit:28, weeks:0, status:'' }); P.ver++; P.confirmed = null; saveRec(); return render();
    case 'pl-col': return ask('Add a column', 'Kept as a marked extra column.', 'Column name', function (v) { P.extra.push({ key:'c' + epXId(), label:v }); P.ver++; saveRec(); closeModal(); render(); });
    case 'pl-del': return ask('Delete a row', 'The row stays on the plan, struck through, with your reason.', 'Reason', function (v) { row().deleted = { why:v, by:WHO(), on:epXNow() }; P.ver++; saveRec(); closeModal(); render(); });
    case 'pl-rest': row().deleted = null; P.ver++; saveRec(); return render();
    case 'pl-ov': var o = row(); return modal('Forecast delivery override', '<div class="ep-sub" style="margin-bottom:8px;">Leave the date empty to use the calculated forecast.</div><div class="ep-lbl">Date</div><input type="date" id="m-d" class="ep-in" value="' + esc(o.over) + '"><div class="ep-lbl" style="margin-top:8px;">Reason</div><input id="m-w" class="ep-in" value="' + esc(o.overWhy) + '">', function () { var d = $('m-d').value, w = $('m-w').value.trim(); if (d && !w) return toast('Give the reason.'); o.over = d; o.overWhy = w; P.ver++; saveRec(); closeModal(); render(); });
    case 'pl-dep': return modal('Critical sub-order status', ['Engineering status', 'Procurement status', 'Fabrication status'].map(function (s) { return conn(s, 'the department app', ['Live status for this sub-order']); }).join(''), null, { foot:'<button class="ep-btn primary" id="modal-cancel">Close</button>' });
    case 'pl-cov': var un = REC.items.filter(function (i) { return !P.cov[i.item]; }); return modal('Match PO items', '<div class="ep-sub" style="margin-bottom:8px;">Tick the PO items this plan covers. Sub-order rows may not match PO lines one to one.</div><div style="max-height:320px;overflow:auto;">' + (un.slice(0, 300).map(function (i) { return '<label class="sx-li"><input type="checkbox" data-item="' + i.item + '" checked> ' + i.item + ' — ' + esc(i.desc) + '</label>'; }).join('') || 'Every PO item is covered.') + '</div>', function () { document.querySelectorAll('[data-item]').forEach(function (c) { if (c.checked) P.cov[c.getAttribute('data-item')] = true; }); saveRec(); closeModal(); render(); });
    case 'pl-dl': return plXlsx(); case 'pl-up': $('sx-file').click(); return;
    case 'pl-submit': case 'pl-confirm': var c = plCheck(REC); if (c.un) return toast(c.un + ' PO items are not covered. List every item, placed or not.'); if (c.bad2) return toast(c.bad2 + ' unplaced rows need a status and an expected order date.'); if (!c.live.length) return toast('Add at least one row.'); if (a === 'pl-submit') P.submitted = { on:epXNow(), by:WHO() }; else P.confirmed = { on:epXNow(), by:WHO() }; saveRec(); render(); return toast(a === 'pl-submit' ? 'Plan submitted.' : 'Plan confirmed.');
    case 'mfgd': return mfgDatesModal(); case 'pimm': return pimModal();
    case 'sl-add': var cols = y.split('|'); return modal('Add entry', cols.map(function (c, i) { return '<div class="ep-lbl">' + esc(c) + '</div><input class="ep-in" id="m-c' + i + '">'; }).join(''), function () { var e = {}; cols.forEach(function (c, i) { e[c] = $('m-c' + i).value.trim(); }); REC.sx[x].push(e); saveRec(); closeModal(); render(); });
    case 'disp': REC.disp[x] = T(); saveRec(); return render();
    case 'att': return modal('Upload monthly report', '<div class="ep-lbl">Month</div><input type="month" id="m-m" class="ep-in"><div class="ep-lbl" style="margin-top:8px;">Report</div><input type="file" id="m-f" class="ep-in" accept=".pdf,.docx">', function () { var f = $('m-f').files[0], m = $('m-m').value; if (!f || !m) return toast('Choose the month and file.'); REC.atts.push({ m:m, f:f.name, by:WHO() }); saveRec(); closeModal(); render(); });
    case 'mssr-dl': return downloadMiniXlsx(miniBuildXlsx({ sheetName:'MSSR', title:'MSSR — ' + REC.po + ' — ' + REC.supplier, columns:[{ header:'Activity', width:50 }, { header:'Baseline finish', width:16 }, { header:'Forecast finish', width:16 }, { header:'%', width:8 }, { header:'Reason', width:40 }], rows:REC.sch.rows.filter(function (r) { return !r.na; }).map(function (r) { return [r.act, r.bE, r.fE, r.pct, r.dep]; }) }), 'MSSR ' + REC.po + '.xlsx');
    case 'ld-step': REC.ld.steps = REC.ld.steps || {}; REC.ld.steps[x] = T(); saveRec(); return render();
    case 'wf': var ls = epExpLoad(), r = ls.find(function (q) { return q.po === x; }); (r.wf = r.wf || {})[y] = true; epExpSave(ls); return render();
    case 'aoc-add': return modal('Add area of concern', '<div class="ep-lbl">PO</div><select id="m-po" class="ep-in">' + allRecs().map(function (q) { return '<option>' + esc(q.po) + '</option>'; }).join('') + '</select><div class="ep-lbl" style="margin-top:8px;">Issue</div><textarea id="m-i" class="ep-ta"></textarea><div class="ep-lbl" style="margin-top:8px;">Target date</div><input type="date" id="m-t" class="ep-in">', function () { var i = $('m-i').value.trim(), d = $('m-t').value; if (!i || !d) return toast('Fill in the issue and target date.'); SX.concerns.push({ id:epXId(), po:$('m-po').value, no:'AOC-' + String(SX.concerns.length + 1).padStart(3, '0'), cat:'', issue:i, by:'EPC_EXPEDITOR', target:d, impact:'MAJOR', status:'OPEN' }); saveSX(); closeModal(); render(); });
    case 'rail-add': return modal('Add RAIL Action Item',
      '<div class="ep-lbl">Purchase Order</div><select id="m-rail-po" class="ep-in">' + allRecs().map(function (q) { return '<option value="' + esc(q.po) + '">' + esc(q.po) + ' — ' + esc(q.supplierShort || q.supplier) + '</option>'; }).join('') + '</select>' +
      '<div class="ep-lbl" style="margin-top:8px;">Finding / Required Action</div><textarea id="m-rail-iss" class="ep-in" rows="3" placeholder="Describe the delay, discrepancy, or action required..."></textarea>' +
      '<div class="ep-fields" style="grid-template-columns:1fr 1fr;margin-top:8px;">' +
        '<div><div class="ep-lbl">Source</div><select id="m-rail-src" class="ep-in">' + ['Manual', 'Shop Visit', 'Document SLA', 'Schedule Red Flag', 'Inspection'].map(function (s) { return '<option>' + s + '</option>'; }).join('') + '</select></div>' +
        '<div><div class="ep-lbl">Assigned To</div><select id="m-rail-asg" class="ep-in">' + [['VENDOR', 'Vendor'], ['EXP', 'Expeditor'], ['DOC', 'Doc Expeditor'], ['FIELD', 'Field Expeditor'], ['ENGINEERING', 'Engineering Custodian'], ['PEXM', 'Expediting Manager']].map(function (s) { return '<option value="' + s[0] + '">' + s[1] + '</option>'; }).join('') + '</select></div>' +
      '</div>' +
      '<div class="ep-lbl" style="margin-top:8px;">Target Completion Date</div><input type="date" id="m-rail-tgt" class="ep-in" value="' + ad(T(), 7) + '">',
      function () {
        var po = $('m-rail-po').value, iss = $('m-rail-iss').value.trim(), tgt = $('m-rail-tgt').value;
        if (!iss || !tgt) return toast('Please provide the finding description and target date.');
        SX.concerns = SX.concerns || [];
        var actNo = 'ACT-' + String(SX.concerns.length + 1).padStart(3, '0');
        var recObj = epExpFind(po);
        SX.concerns.unshift({
          id: epXId(),
          no: actNo,
          po: po,
          issue: iss,
          source: $('m-rail-src').value,
          assignedTo: $('m-rail-asg').value,
          assignedVendor: recObj ? (recObj.supplierShort || recObj.supplier) : '',
          target: tgt,
          by: WHO() || 'EXPEDITOR',
          status: 'OPEN',
          history: [{ on: T(), by: WHO(), act: 'Created', note: 'Created in RAIL Action Tracker' }]
        });
        saveSX(); closeModal(); render(); toast('Action ' + actNo + ' created!');
      }, { wide: 'wide' }
    );
    case 'rail-res':
      var cRes = (SX.concerns || []).find(function (q) { return q.id === x; });
      if (!cRes) return;
      return modal('Submit Resolution — ' + cRes.no,
        '<div class="ep-sub" style="margin-bottom:8px;"><b>Action:</b> ' + esc(cRes.issue) + '</div>' +
        '<div class="ep-lbl">Close-out Remarks / Corrective Actions Taken</div><textarea id="m-res-rem" class="ep-in" rows="3" placeholder="Detail how this finding was settled..."></textarea>' +
        '<div class="ep-lbl" style="margin-top:8px;">Supporting Evidence (Document No., Inspection Report, or Reference)</div><input id="m-res-ev" class="ep-in" placeholder="e.g. Revised drawing DWG-102 Rev B, or MOM reference">',
        function () {
          var rem = fxV('m-res-rem'), evd = fxV('m-res-ev');
          if (!rem) return toast('Please detail the close-out remarks.');
          cRes.status = 'PENDING_VERIFICATION';
          cRes.resolution = rem;
          cRes.evidence = evd;
          cRes.history = cRes.history || [];
          cRes.history.push({ on: T(), by: WHO(), act: 'Resolution Submitted', note: rem + (evd ? ' [Evidence: ' + evd + ']' : '') });
          note(cRes.po, 'EXP', 'PO ' + cRes.po + ': Action ' + cRes.no + ' resolution submitted for verification.');
          saveSX(); closeModal(); render(); toast('Resolution submitted! Status changed to Pending Verification.');
        }
      );
    case 'rail-verify':
      var cVer = (SX.concerns || []).find(function (q) { return q.id === x; });
      if (!cVer) return;
      return modal('Verify & Close Action — ' + cVer.no,
        '<div class="ep-sub">Review submitted resolution:</div>' +
        '<div style="background:#f8fafc;padding:10px;border-radius:6px;border:1px solid #e2e8f0;margin:8px 0;font-size:12px;">' +
          '<b>Resolution:</b> ' + esc(cVer.resolution || '—') + '<br>' +
          '<b>Evidence:</b> ' + esc(cVer.evidence || '—') +
        '</div>' +
        '<div class="ep-lbl">Lead Expeditor Verification Comments (optional)</div><input id="m-ver-cmt" class="ep-in" placeholder="Approved based on provided evidence">',
        function () {
          cVer.status = 'CLOSED';
          cVer.closedOn = T();
          cVer.closedBy = WHO();
          cVer.history = cVer.history || [];
          cVer.history.push({ on: T(), by: WHO(), act: 'Verified & Closed', note: fxV('m-ver-cmt') || 'Closeout verified.' });
          saveSX(); closeModal(); render(); toast('Action ' + cVer.no + ' verified and closed.');
        }
      );
    case 'rail-reopen':
      var cReop = (SX.concerns || []).find(function (q) { return q.id === x; });
      if (!cReop) return;
      return modal('Reject & Re-open Action — ' + cReop.no,
        '<div class="ep-lbl">Reason for Rejection / Missing Evidence</div><textarea id="m-reop-why" class="ep-in" rows="3" placeholder="Explain what additional corrective action or evidence is required..."></textarea>',
        function () {
          var why = fxV('m-reop-why');
          if (!why) return toast('Please specify the reason for rejection.');
          cReop.status = 'OPEN';
          cReop.history = cReop.history || [];
          cReop.history.push({ on: T(), by: WHO(), act: 'Rejected & Re-opened', note: why });
          saveSX(); closeModal(); render(); toast('Action re-opened with comments.');
        }
      );
    case 'rail-rebase':
      var cReb = (SX.concerns || []).find(function (q) { return q.id === x; });
      if (!cReb) return;
      return modal('Re-baseline Target Date — ' + cReb.no,
        '<div class="ep-sub" style="margin-bottom:8px;">Current Target: <b>' + (cReb.target ? fmtDate(cReb.target) : 'TBD') + '</b></div>' +
        '<div class="ep-lbl">New Target Completion Date</div><input type="date" id="m-reb-d" class="ep-in" value="' + (cReb.target || T()) + '">' +
        '<div class="ep-lbl" style="margin-top:8px;">Mandatory Justification Reason</div><textarea id="m-reb-why" class="ep-in" rows="3" placeholder="Explain why this deadline is being revised..."></textarea>',
        function () {
          var nd = $('m-reb-d').value, why = fxV('m-reb-why');
          if (!nd || !why) return toast('Please specify the new target date and justification.');
          cReb.history = cReb.history || [];
          cReb.history.push({ on: T(), by: WHO(), act: 'Target Date Re-baselined', note: 'Changed from ' + cReb.target + ' to ' + nd + '. Reason: ' + why });
          cReb.target = nd;
          saveSX(); closeModal(); render(); toast('Target date re-baselined to ' + fmtDate(nd));
        }
      );
    case 'rail-hist':
      var cHist = (SX.concerns || []).find(function (q) { return q.id === x; });
      if (!cHist) return;
      var hList = cHist.history || [];
      return modal('Audit History — ' + cHist.no,
        '<div class="ep-sub" style="margin-bottom:10px;"><b>Action:</b> ' + esc(cHist.issue) + '</div>' +
        '<div style="max-height:300px;overflow-y:auto;"><table class="ep-table"><thead><tr><th>Timestamp</th><th>User</th><th>Action</th><th>Notes / Remarks</th></tr></thead><tbody>' +
          (hList.slice().reverse().map(function (h) {
            return '<tr><td class="tabnum">' + fmtDate(h.on ? h.on.slice(0, 10) : T()) + '</td><td>' + esc(h.by || 'System') + '</td><td><span class="ep-pill info sm">' + esc(h.act) + '</span></td><td>' + esc(h.note || '—') + '</td></tr>';
          }).join('') || '<tr><td colspan="4" class="ep-sub">No audit log yet.</td></tr>') +
        '</tbody></table></div>',
        null, { foot: '<button class="ep-btn secondary" id="modal-cancel">Close</button>', wide: 'wide' }
      );
    case 'rf-act':
      var pRf = (x || '').split('|'), rfPo = pRf[0], rfDays = pRf[1] || '0';
      return modal('Spawn RAIL Action for Schedule Slippage',
        '<div class="ep-lbl">Purchase Order</div><input class="ep-in" value="' + esc(rfPo) + '" readonly>' +
        '<div class="ep-lbl" style="margin-top:8px;">Action / Finding Description</div><textarea id="m-rf-iss" class="ep-in" rows="3">Critical schedule slippage: Forecast finish exceeds CDD by ' + rfDays + ' days. Recovery schedule & expedited manufacturing plan required from supplier.</textarea>' +
        '<div class="ep-lbl" style="margin-top:8px;">Target Date for Recovery Plan</div><input type="date" id="m-rf-tgt" class="ep-in" value="' + ad(T(), 7) + '">',
        function () {
          var iss2 = fxV('m-rf-iss'), tgt2 = $('m-rf-tgt').value;
          if (!iss2 || !tgt2) return toast('Provide description and target date.');
          SX.concerns = SX.concerns || [];
          var actNo2 = 'ACT-' + String(SX.concerns.length + 1).padStart(3, '0');
          var recObj2 = epExpFind(rfPo);
          SX.concerns.unshift({
            id: epXId(),
            no: actNo2,
            po: rfPo,
            issue: iss2,
            source: 'Schedule Red Flag',
            assignedTo: 'VENDOR',
            assignedVendor: recObj2 ? (recObj2.supplierShort || recObj2.supplier) : '',
            target: tgt2,
            by: WHO() || 'EXPEDITOR',
            status: 'OPEN',
            history: [{ on: T(), by: WHO(), act: 'Created from Red Flag', note: 'Spawned due to ' + rfDays + 'd slippage against CDD' }]
          });
          saveSX(); closeModal(); render(); toast('Recovery Action ' + actNo2 + ' created in RAIL!');
        }
      );
    case 'doc-act':
      return modal('Spawn RAIL Action for Document Delay',
        '<div class="ep-lbl">Purchase Order</div><input class="ep-in" value="' + esc(x) + '" readonly>' +
        '<div class="ep-lbl" style="margin-top:8px;">Action / Finding Description</div><textarea id="m-doc-iss" class="ep-in" rows="3">Overdue engineering document review: Critical Class 1 drawings exceeded 14-day custodian SLA / Code C return, delaying fabrication start.</textarea>' +
        '<div class="ep-fields" style="grid-template-columns:1fr 1fr;margin-top:8px;">' +
          '<div><div class="ep-lbl">Assigned To</div><select id="m-doc-asg" class="ep-in"><option value="ENGINEERING">Engineering Custodian</option><option value="VENDOR">Vendor</option><option value="DOC">Doc Expeditor</option></select></div>' +
          '<div><div class="ep-lbl">Target Date</div><input type="date" id="m-doc-tgt" class="ep-in" value="' + ad(T(), 5) + '"></div>' +
        '</div>',
        function () {
          var iss3 = fxV('m-doc-iss'), tgt3 = $('m-doc-tgt').value;
          if (!iss3 || !tgt3) return toast('Provide description and target date.');
          SX.concerns = SX.concerns || [];
          var actNo3 = 'ACT-' + String(SX.concerns.length + 1).padStart(3, '0');
          var recObj3 = epExpFind(x);
          SX.concerns.unshift({
            id: epXId(),
            no: actNo3,
            po: x,
            issue: iss3,
            source: 'Document SLA',
            assignedTo: $('m-doc-asg').value,
            assignedVendor: recObj3 ? (recObj3.supplierShort || recObj3.supplier) : '',
            target: tgt3,
            by: WHO() || 'DOC_EXPEDITOR',
            status: 'OPEN',
            history: [{ on: T(), by: WHO(), act: 'Created from Document Review', note: 'Spawned from Document Control VDR summary' }]
          });
          saveSX(); closeModal(); render(); toast('Action ' + actNo3 + ' created in RAIL!');
        }
      );
    case 'vnotif-new': return vnotifModal();
    case 'dc': REC.dc.on = T(); saveRec(); return render();
  }
});
document.addEventListener('change', function (ev) {
  var t = ev.target, c = t.getAttribute('data-sc');
  if (t.id === 'sx-role') {
    ROLE = t.value;
    if (isV()) {
      SEC = 'portal';
      TAB = 'sched';
    } else if (ROLE === 'DOC') {
      SEC = 'core';
      TAB = 'docs';
    } else if (ROLE === 'FIELD') {
      SEC = 'field';
      TAB = '';
    } else if (ROLE === 'EXP') {
      SEC = 'exec';
      TAB = 'sched';
    } else if (ROLE.indexOf('REV_') === 0) {
      SEC = 'core';
      TAB = 'docs';
    } else {
      SEC = 'dash';
      DASH = 'overview';
      TAB = '';
    }
    SECTAB = {};
    if (TAB) SECTAB[SEC] = TAB;
    return render();
  }
  if (t.id === 'sx-file') { if (t.files[0]) plUpload(t.files[0]); t.value = ''; return; }
  if (t.hasAttribute('data-pl')) return plSet(t.getAttribute('data-x'), t.getAttribute('data-pl'), t.value);
  if (c === 'po') { PO = t.value; return render(); }
  if (c === 'rail-flt-po') { window.RAIL_FILTER = window.RAIL_FILTER || {}; window.RAIL_FILTER.po = t.value; return render(); }
  if (c === 'rail-flt-st') { window.RAIL_FILTER = window.RAIL_FILTER || {}; window.RAIL_FILTER.status = t.value; return render(); }
  if (c === 'rail-flt-tier') { window.RAIL_FILTER = window.RAIL_FILTER || {}; window.RAIL_FILTER.tier = t.value; return render(); }
  if (c === 'rail-flt-asg') { window.RAIL_FILTER = window.RAIL_FILTER || {}; window.RAIL_FILTER.assignee = t.value; return render(); }
  if (c === 'ld-rate') { REC.ld.rate = t.value; saveRec(); return render(); } if (c === 'ld-cap') { REC.ld.cap = t.value; saveRec(); return render(); }
  if (c === 'mrx') { REC.mrx[t.getAttribute('data-x')] = t.checked; return saveRec(); }
  if (c === 'ack') { REC.ackx.st = t.value; return saveRec(); } if (c === 'ackp') { REC.ackx.pts = t.value; return saveRec(); }
  if (c === 'aoc') { SX.concerns.find(function (q) { return q.id === t.getAttribute('data-x'); }).status = t.value; return saveSX(); }
});

/* ---------- boot & message bridge ---------- */
function syncParamsFromUrl() {
  try {
    var p = new URLSearchParams(window.location.search);
    if (p.get('sec')) SEC = p.get('sec');
    if (p.get('tab')) { TAB = p.get('tab'); SECTAB[SEC] = TAB; }
    if (p.get('po')) PO = p.get('po');
    if (p.get('role')) ROLE = p.get('role');
  } catch(e) {}
}

function notifyParentNav() {
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: 'SX_NAV_SYNC', sec: SEC, tab: TAB, po: PO, role: ROLE }, '*');
    }
  } catch(e) {}
}

window.addEventListener('message', function (ev) {
  if (!ev.data) return;
  if (ev.data.type === 'SX_NAVIGATE') {
    if (ev.data.sec) SEC = ev.data.sec;
    if (ev.data.tab) { TAB = ev.data.tab; SECTAB[SEC] = TAB; }
    if (ev.data.po) PO = ev.data.po;
    if (ev.data.role) ROLE = ev.data.role;
    render();
  }
});

(function () { allRecsReady(); })();
function allRecsReady() {
  var r = allRecs(), s = epStore.get(PKEY);
  if (!r.length || !s) { seedAll(); } else SX = JSON.parse(s);
  JSON.parse(window.SX_VENDORS).forEach(function (v) { ROLES['VEN:' + v[0]] = 'Vendor — ' + v[1]; });
  $('sx-ed').textContent = AFTER ? 'After workflow file' : 'Before workflow file';
  syncParamsFromUrl();
  render();
}

function kp(k, v, s, bad) { return '<div class="ep-kpi"><div class="k">' + esc(k) + '</div><div class="v"' + (bad ? ' style="color:#be123c"' : '') + '>' + esc(v) + '</div><div class="ep-sub">' + esc(s) + '</div></div>'; }
function hf(k, v) { return '<div class="ep-f"><div class="k">' + esc(k) + '</div><div class="v">' + esc(v) + '</div></div>'; }
