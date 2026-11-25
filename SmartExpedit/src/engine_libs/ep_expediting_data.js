/* ============================================================================
   SmartExpedit — Expediting / Logistics / Closeout — data layer
   ----------------------------------------------------------------------------
   AN EXPEDITING RECORD IS BORN THE MOMENT THE BUYER PRESSES
   "Notify Expediting" ON AN ISSUED PURCHASE ORDER.

   It does not wait for the vendor's acknowledgement — the 72-hour rule is a
   KPI, not a gate; the expeditor works from day one whether or not the vendor
   has signed and stamped the order back.

   The record is one row per PURCHASE ORDER. Lots (delivery dates, grace, LD)
   are tracked inside the record, not as separate rows. The MR is carried on
   the record so the expeditor can study it (hold, PIM, ITR, SDR) before the
   kickoff meeting.

   OWNERSHIP: this module belongs to the Expediting Manager (Mr. Huzaifa) and
   his team. The buyer never works in here; the buyer only sends orders in.
   ============================================================================ */

/* ------------------------------------------------------------------ PEOPLE */
const EP_EXP_TEAM = [
  { name:'Ashok',   role:'Expeditor' },
  { name:'Arjun',   role:'Expeditor' },
  { name:'Hesham',  role:'Expeditor' },
  { name:'Ali',     role:'Expeditor' },
  { name:'Soud',    role:'Expeditor' },
  { name:'Ahmed',   role:'Expeditor' },
  { name:'Youssef', role:'Expeditor' },
];
const EP_EXP_MANAGER  = 'Mr. Huzaifa';   /* Expediting Manager — assigns */
const EP_EXP_MGR_ROLE = 'Expediting Manager — this MR';

/* -------------------------------------------------------------- SDRL CODES
   The master reference: every document a supplier can be asked to submit,
   with its custodian (who reviews it) and its document class (1 = proceed
   only after comments, 2 = proceed if no comment within the contractual
   turnaround, 3 = company may comment but work continues).
   This is the reference the expeditor reads to know what to ask for.     */
const EP_SDRL = [
  /* custodian, code, title, class */
  ['PMT','A001','Supplier data register',1],
  ['CERTIFICATION','A002','Manufacturer Record Book (MRB)',1],
  ['PMT','A003','Installation, Operation and Maintenance manuals (IOM)',1],
  ['PMT','A004','Spare Parts and Interchangeability Record (SPIR) form - Filled in',1],
  ['PMT','A005','Painting application procedure (Including vendor specification)',1],
  ['INSPECTION','A006','Insulation application procedure',2],
  ['PMT','A007','Final drawing electronic files',2],
  ['PMT','A008','Base Line Survey Procedure',2],
  ['PMT','A009','Base Line Survey Report (Information)',3],
  ['ENGINEERING','A010','Tag Number List',2],
  ['PMT','A011','Sub-vendor\u2019s pre qualifications',3],
  ['CERTIFICATION','A012','Manufacturer Book index (MRBI)',1],
  ['PMT','A013','Execution Plan / General Procedures/Method Statements',2],
  ['PMT','A014','Vendor Technical Clarifications',1],
  ['PMT','A016','Waivers from Vendors',1],
  ['PMT','A017','Asset registration form',1],
  ['PMT','A018','DST - 003 CMMS Data Sheet',2],
  ['PMT','A019','Technical Query',1],
  ['PMT','A020','Non Conformity Record',1],
  ['PMT','A021','Concession Request',1],
  ['ENGINEERING','B001','Process description',2],
  ['ENGINEERING','B002','Process flow diagrams with heat and material balance',1],
  ['ENGINEERING','B003','Piping & Instrument diagrams',1],
  ['ENGINEERING','B004','Equipment list',1],
  ['ENGINEERING','E001','Painting Procedures',2],
  ['PMT','E002','Project quality plan',1],
  ['INSPECTION','E003','Inspection and test plan (Structural/Piping/Painting)',2],
  ['PMT','E004','Inspection and test plan (E&I/HVAC/Mech)',2],
  ['PMT','E005','Heat Treatment Procedure',2],
  ['QUALITY','E006','NDT Procedures',2],
  ['QUALITY','E007','NDT Operator qualifications',1],
  ['QUALITY','E008','Welding book including welding procedure specification (WPS), Procedure qualification record (PQR), weld map.',1],
  ['QUALITY','E009','PMI Procedure',2],
  ['ENGINEERING','F001','Equipment filled-in data sheets',2],
  ['ENGINEERING','F002','Calculation notes',2],
  ['ENGINEERING','F014','Detailed drawings',2],
  ['ENGINEERING','F021','Mechanical Design Calculations for Pressure Vessels & Heat Exchangers',2],
  ['ENGINEERING','G001','Equipment filled-in data sheets applicable to proposal, purchase & as built',2],
  ['ENGINEERING','G002','Performance curves',1],
  ['ENGINEERING','H006','Equipment Datasheets',1],
  ['ENGINEERING','H027','Material Approval Request (MAR)',1],
  ['ENGINEERING','J001','Instruments schedule',2],
  ['ENGINEERING','J005','Instrument data sheets / specifications',2],
  ['ENGINEERING','L001','General arrangement drawings',1],
  ['ENGINEERING','L011','Valve Data sheets',1],
  ['ENGINEERING','M001','Drawing(s)',2],
  ['ENGINEERING','M002','Calculation(s)',2],
  ['ENGINEERING','M003','Data Sheet(s)',2],
  ['ENGINEERING','N001','Drawing(s)',2],
  ['ENGINEERING','N002','Calculation(s)',2],
  ['ENGINEERING','N003','Data Sheet(s)',2],
  ['PMT','N004','Mill Tally Sheet(s)',2],
  ['ENGINEERING','P004','Data sheets (switchgears, cables, transformers, etc) - Filled in',2],
  ['ENGINEERING','P005','Filled in motor data sheets',1],
  ['ENGINEERING','R001','Leaflets / Catalogues',2],
  ['ENGINEERING','R002','Deviation list(s)',2],
  ['ENGINEERING','R003','General assembly drawings',1],
  ['INSPECTION','R005','Shop repair manual',2],
  ['INSPECTION','R006','Material mill test certificates',2],
  ['ENGINEERING','R007','Other documents as required in P.O.',2],
  ['PMT','W001','Instruction for handling, transportation and storage prior and after erection',2],
  ['PMT','W002','Instruction and drawings for erection including lifting procedure',2],
  ['PMT','W003','Preservation Procedure prior and after erection',2],
  ['PMT','W004','Consumables list (itemized and priced)',2],
  ['PMT','W005','Spare parts and special tools',1],
  ['PMT','W006','Detailed site erection schedule',3],
  ['PMT','W007','Erection and installation procedure',2],
  ['PMT','W008','Procedures for cable pulling',2],
  ['PMT','W009','Material safety data sheet',2],
  ['INSPECTION','X001','Project quality plan',1],
  ['INSPECTION','X002','Inspection and test plan',2],
  ['INSPECTION','X003','Manufacturing / Test procedure specifications',2],
  ['INSPECTION','X004','Heat Treatment Procedure',2],
  ['INSPECTION','X005','NDT Procedures',2],
  ['INSPECTION','X006','NDT Operator qualifications',1],
  ['INSPECTION','X007','Welding book including welding procedure specification (WPS), Procedure qualification record (PQR), weld map.',1],
  ['INSPECTION','X008','PMI Procedure',2],
  ['INSPECTION','X009','Release note including punchlist',3],
  ['INSPECTION','X010','Inspection Report',3],
  ['INSPECTION','X011','Pickling And Passivation Procedure',2],
  ['INSPECTION','Y001','Material Certification (EN-10204, Type 3.2)',3],
  ['INSPECTION','Y002','Material Certification (EN-10204, Type 3.1)',3],
  ['INSPECTION','Y003','Material Certification (EN-10204, Type 2.2)',3],
  ['INSPECTION','Y004','Material Certification (EN-10204, Type 2.1)',3],
  ['ENGINEERING','Y005','Type Test Certificate (Pre-award design verification)',2],
  ['PMT','Y006','Hazardous Area Classification Certificates and Schedule',3],
  ['INSPECTION','Y007','Fire Safe Certificate (Valves)',3],
  ['ENGINEERING','Y008','Design Approval Certificate',2],
  ['INSPECTION','Y009','Material Location Plan (Traceability records)',3],
  ['INSPECTION','Y011','Welder Qualification Record',3],
  ['INSPECTION','Y012','NDT Operator Qualifications',3],
  ['INSPECTION','Y013','Weld and NDT Identification Diagrams',1],
  ['INSPECTION','Y014','Dimensional Control Reports',3],
  ['INSPECTION','Y015','Radiographic Inspection Reports (INCL. REPAIRS)',3],
  ['INSPECTION','Y016','MPI/ Dye Penetrant Reports',3],
  ['INSPECTION','Y017','Ultrasonic Inspection Reports (INCL. REPAIRS)',3],
  ['INSPECTION','Y020','Hardness Test Reports',1],
  ['INSPECTION','Y021','CODT / Impact Test Reports',3],
  ['INSPECTION','Y022','HIC Test certificate',3],
  ['INSPECTION','Y023','NACE MR 0175 Certificate',3],
  ['INSPECTION','Y025','PWHT Charts (For Each Heat Treatment)',3],
  ['INSPECTION','Y026','Pressure Test Reports / Certificates',3],
  ['INSPECTION','Y027','Functional Test Reports / Certificates',3],
  ['INSPECTION','Y028','Performance Test Reports / Certificates',3],
  ['INSPECTION','Y030','Vibration Test Reports',3],
  ['INSPECTION','Y031','NPSH Test Reports',3],
  ['INSPECTION','Y032','Other Reports / Certificates',3],
  ['INSPECTION','Y035','Electric Motor Type Test Report',3],
  ['INSPECTION','Y037','Cable Continuity and Resistance Test Report',3],
  ['INSPECTION','Y041','Proof Load Test Certificates',2],
  ['INSPECTION','Y042','Weight Certificates',3],
  ['INSPECTION','Y043','Valve Manufacturer\u2019s Certificate',3],
  ['INSPECTION','Y044','Type Approval Certificate',2],
  ['PMT','Y045','Certificate of Compliance',3],
  ['INSPECTION','Y046','Calibration Test Certificates',3],
  ['INSPECTION','Y047','Surface Preparation and Coating Reports',3],
  ['INSPECTION','Y048','Factory Acceptance Tests report',2],
  ['EXPEDITING','Z001','Schedules',3],
  ['EXPEDITING','Z002','Sub-order plan',3],
  ['EXPEDITING','Z003','Manufacturing schedule',3],
  ['EXPEDITING','Z004','Expediting - Progress reports',3],
  ['EXPEDITING','Z005','Shipping documentation',3],
].map(function (r) {
  return { custodian:r[0], code:r[1], title:r[2], cls:r[3],
           adnoc:'AD-27-G-XXXXX-' + r[1] + '-001' };
});
/* the FULL master (386 codes) replaces the curated subset above whenever
   ep_sdrl_master.js is loaded — class from the CSV, prime custodian and group
   from the XLS. The subset stays only as a fallback. */
if (typeof window !== 'undefined' && window.EP_SDRL_MASTER) {
  EP_SDRL.length = 0;
  window.EP_SDRL_MASTER.forEach(function (r) {
    EP_SDRL.push({ code:r[0], title:r[1], cls:r[2], custodian:(r[3] || '').toUpperCase(), prime:r[4] || '',
                   group:r[5] || '', adnoc:r[6] || '' });
  });
}
function epSdrl(code) { return EP_SDRL.find(function (d) { return d.code === code; }) || null; }
function epSdrlByCustodian(c) { return EP_SDRL.filter(function (d) { return d.custodian === c; }); }
const EP_SDRL_CUSTODIANS = ['PMT','ENGINEERING','INSPECTION','QUALITY','CERTIFICATION','COMMISSIONING','EXPEDITING'];
const EP_SDRL_CLASS_HELP = {
  1:'Contractor may not proceed until written comments have been given by Company',
  2:'Contractor may proceed if Company has made no comment as per the contractual turnaround duration',
  3:'Company reserves the right to comment but Contractor may continue with the WORK',
};

/* ------------------------------------------ THE MINIMUM SCHEDULE SKELETON
   The rows every expediting schedule must carry, as the minimum requirement
   says. The expeditor registers these against the SDRL codes that apply to
   this order and then dates them: baseline (contractual, never moves) and
   forecast/actual (what the vendor now says).                              */
const EP_EXP_SCHEDULE_MIN = [
  { act:'PO acknowledgement',                        sdrl:'', dur:30 },
  { act:'Drg, Datasheet, ITP, SVL, Schedule submission', sdrl:'' },
  { act:'Kick off meeting',                          sdrl:'' },
  { act:'Drg, Datasheet, ITP, SVL approval',          sdrl:'' },
  { act:'Pre-inspection meeting',                    sdrl:'' },
  { act:'Sub-orders placement',                       sdrl:'Z002' },
  { act:'Sub-orders manufacturing',                   sdrl:'Z002' },
  { act:'Sub-orders delivery',                        sdrl:'Z002' },
  { act:'Start Fabrication',                          sdrl:'Z003' },
  { act:'End Fabrication',                           sdrl:'Z003' },
  { act:'Assembly',                                   sdrl:'' },
  { act:'Internal Testing',                           sdrl:'' },
  { act:'Inspection notification',                    sdrl:'' },
  { act:'FAT / Inspection',                           sdrl:'X010' },
  { act:'Punch point closure',                        sdrl:'X009' },
  { act:'IRN issuance',                              sdrl:'X009' },
  { act:'Exw readiness',                             sdrl:'' },
  { act:'FOB Port of dispatch (for FOB orders)',      sdrl:'' },
  { act:'CFR Port of arrival (for CFR orders)',      sdrl:'' },
  { act:'Delivered at destination (for DDP/DDU/DAP)', sdrl:'' },
  { act:'SPIR submission (if applicable)',            sdrl:'A004' },
  { act:'MRB submission',                            sdrl:'A002' },
];

/* --------------------------------------------------------------- STATUSES
   The expediting life. Each step carries a date once done; the record's
   status is the furthest step reached. Acknowledgement is a dated milestone,
   NOT a gate — the 72-hour rule is reported, not enforced.               */
const EP_EXP_STAGES = [
  { key:'issued',    label:'Issued',              sub:'order issued to the supplier' },
  { key:'ack',       label:'Acknowledged',        sub:'vendor signed & stamped the order' },
  { key:'docsOut',   label:'Docs Requested',      sub:'kickoff meeting held, documents requested' },
  { key:'docsIn',    label:'Docs Submitted',      sub:'vendor submitting the required documents' },
  { key:'docsOk',    label:'Docs Under Approval', sub:'documents with custodians for approval' },
  { key:'pim',       label:'PIM Done',            sub:'pre-inspection meeting at supplier\u2019s premises' },
  { key:'fab',       label:'In Manufacture',      sub:'fabrication started at the supplier' },
  { key:'insp',      label:'Inspection',          sub:'stage / external inspections running' },
  { key:'release',   label:'Ready for Dispatch',   sub:'final inspection done, IRN issued, punch closed' },
  { key:'shipped',   label:'Shipped',             sub:'collected / despatched' },
  { key:'delivered', label:'Delivered',            sub:'MRV raised at stores' },
  { key:'mrbSub',    label:'MRB Submitted',       sub:'databook with the vendor register' },
  { key:'closed',    label:'Closed',              sub:'MRB approved — the order is finished' },
];
function epExpStageIndex(key) { return EP_EXP_STAGES.findIndex(function (s) { return s.key === key; }); }

/* ------------------------------------------------------------ THE RECORDS
   One record per issued PO, born on "Notify Expediting". Stored under
   ep_exp_records as an array, keyed by PO number so the register and the
   detail page read the same thing.                                     */
const EP_EXP_KEY = 'ep_exp_records';

function epExpLoad() {
  try { return JSON.parse(epStore.get(EP_EXP_KEY) || '[]') || []; }
  catch (e) { return []; }
}
function epExpSave(list) {
  epStore.set(EP_EXP_KEY, JSON.stringify(list || []));
  if (typeof epBroadcast === 'function') epBroadcast(EP_EXP_KEY);
}
function epExpFind(poNo) {
  return epExpLoad().find(function (r) { return r.po === poNo; }) || null;
}
function epExpIdx(poNo) {
  return epExpLoad().findIndex(function (r) { return r.po === poNo; });
}

/* Build the record from the notify payload the PO module already makes.
   Everything the expeditor studies on the Order Head comes from the PO and
   MR — nothing is retyped.                                                */
function epExpFromPayload(p) {
  return {
    po:        p.po, letter: p.letter, rev: p.rev,
    supplier:  p.supplier, supplierShort: p.supplierShort,
    enquiry:   p.enquiry, mrRef: p.mrRef, project: p.project, head: p.head,
    ccy:       p.ccy || 'USD', value: p.value, lines: p.lines, qty: p.qty, hold: p.hold,
    incoterm:  p.incoterm, deliveryPoint: p.deliveryPoint,
    lots:      (p.lots || []).map(function (l) { return { id:l.id, date:l.date, grace:l.grace, ld:!!l.ld }; }),
    issuedOn:  p.issuedOn, issuedAt: p.issuedAt, awardRev: p.awardRev,
    buyer:     p.buyer, notifiedOn: new Date().toISOString(),
    client:    p.client || '', payment: p.payment || '', origin: p.origin || '', shipMode: p.ship || '',
    items:     (p.items || []).slice(),
    /* assignment */
    assignedTo:'', assignedBy:'', assignedOn:'',
    /* the expediting life */
    stage:     'issued',
    ackDate:   '',                 /* vendor signed & stamped (72h KPI) */
    kickoffOn: '', kickoffNotes:'',
    /* study findings the expeditor records before the kickoff */
    study:     { done:false, on:'', notes:'',
                 payment:'', bg:'', pim:'', itr:'', sdr:'' },
    /* Document Control: the VDR rows (vendor document register) */
    vdr:       [],
    /* the schedule: minimum rows, dated baseline vs forecast */
    schedule:  [],
    /* Manufacturing tracking */
    mfg:       { subOrders:[], fabStart:'', fabEnd:'', stageInsp:[], extInsp:'',
                 punch:'', irn:'' },
    /* Shipment */
    ship:      { mode:'', doc:'', docNo:'', carrier:'', etd:'', eta:'',
                 customs:'', mrvNo:'', mrvOn:'', mrvQty:'' },
    /* Closeout */
    close:     { mrbSubOn:'', mrbApprOn:'', reason:'' },
    /* Follow-up log: dated contacts with the vendor */
    log:       [],
  };
}

/* The PO module calls this when the buyer presses "Notify Expediting".
   Idempotent: notifying twice does not create two records. */
function epExpCreateFromNotify(p) {
  const list = epExpLoad();
  if (list.some(function (r) { return r.po === p.po; })) return { ok:false, msg:'already' };
  const rec = epExpFromPayload(p);
  /* seed the schedule from the minimum requirement, dates blank */
  rec.schedule = EP_EXP_SCHEDULE_MIN.map(function (s) {
    return { act:s.act, sdrl:s.sdrl, dur:s.dur || '',
             bStart:'', bEnd:'', fStart:'', fEnd:'', dep:'', pct:'' };
  });
  /* seed the study fields from what the PO knows */
  rec.study.payment = p.payment || '';
  list.push(rec);
  epExpSave(list);
  return { ok:true, rec:rec };
}

/* ----------------------------------------------------------- ASSIGNMENT */
function epExpAssign(poNo, to, by) {
  const list = epExpLoad();
  const r = list.find(function (x) { return x.po === poNo; });
  if (!r) return { ok:false, msg:'no record' };
  r.assignedTo = to; r.assignedBy = by || EP_EXP_MANAGER; r.assignedOn = new Date().toISOString().slice(0, 10);
  epExpSave(list);
  return { ok:true };
}

/* --------------------------------------------------------------- DATING */
function epExpSetStage(poNo, key) {
  const list = epExpLoad();
  const r = list.find(function (x) { return x.po === poNo; });
  if (!r) return { ok:false };
  const now = epExpStageIndex(key), cur = epExpStageIndex(r.stage);
  if (now > cur) r.stage = key;                 /* forward only */
  epExpSave(list);
  return { ok:true };
}
function epExpAddLog(poNo, by, txt) {
  const list = epExpLoad();
  const r = list.find(function (x) { return x.po === poNo; });
  if (!r) return { ok:false };
  (r.log = r.log || []).push({ on:new Date().toISOString(), by:by, txt:txt });
  epExpSave(list);
  return { ok:true };
}

/* -------------------------------------------------------------- AGING */
function epExpDays(iso) {
  if (!iso) return null;
  const d = new Date(iso); if (isNaN(d)) return null;
  const t = new Date(); t.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((t - d) / 86400000));
}
/* Per record: order aging (days since notify) and, per lot, days past
   promised +grace. Late means past the grace window, and LD applies only
   if the lot says so.                                                     */
function epExpAging(r) {
  const order = epExpDays(r.notifiedOn);
  let late = 0, lateLots = 0, ldLots = 0;
  (r.lots || []).forEach(function (l) {
    if (!l.date) return;
    const d = epExpDays(l.date);
    if (d == null) return;
    const over = d - (l.grace || 0);
    if (over > 0) { lateLots++; late = Math.max(late, over); if (l.ld) ldLots++; }
  });
  return { order:order, late:late, lateLots:lateLots, ldLots:ldLots };
}
function epExpStatusLabel(r) {
  const s = EP_EXP_STAGES.find(function (x) { return x.key === r.stage; });
  return s ? s.label : r.stage;
}
function epExpIsClosed(r) { return r.stage === 'closed'; }

/* ------------------------------------------------------ REGISTER FILTERS */
function epExpRegister() {
  return epExpLoad().slice().sort(function (a, b) {
    return (a.notifiedOn || '').localeCompare(b.notifiedOn || '');
  });
}

/* ============================================================ START DEMO
   Mohamed Amin's request: open Expediting and start the 74259 demo straight
   away, without walking Bid Tabulation and PO Issuance by hand first.

   This does NOT fake the earlier modules — it drives their own engines, in the
   order a buyer would:
     1. Bid Tabulation — every line with a quantity awarded to its best price on
        the round the award module itself would pick (epAwardDefaultRound);
        submitted, then signed by all five award signatories in order, which
        freezes the approval snapshot the PO module reads.
     2. PO Issuance — one order per awarded supplier (A, B, C … in award order),
        built by epPoFromAward, given a delivery date, submitted, signed by the
        five PO signatories in order, and issued.
     3. Each issued order is sent with "Notify Expediting & PMT", which is what
        creates its expediting record — so the queue fills exactly as it would
        from the PO screen.
   Everything earlier for the demo state is reset first (epStore.clear()).
   Prices are the bid tab's MODELLED prices. The lot date is the issue date plus
   the longest week figure in the supplier's quoted delivery — derived, not
   real, and every record carries demo:true so the screens can say so.      */
const EP_EXP_DEMO_NEEDS = ['epQLoad', 'epQSheet', 'epAwardLoad', 'epAwardSave', 'epAwardPco',
  'epAwardView', 'epAwardSnapshot', 'epAwardDefaultRound', 'epAwardFingerprint',
  'epPoFromAward', 'epPoIssue', 'epPoNotify', 'epPoSave', 'epPoFingerprint', 'epQWeeks'];

function epExpDemoReady() {
  return EP_EXP_DEMO_NEEDS.every(function (f) { return typeof window[f] === 'function'; }) &&
         typeof EP_TENDER !== 'undefined' && typeof EP_BIDDERS !== 'undefined';
}

function epExpStartDemo() {
  if (!epExpDemoReady()) return { ok:false, msg:'The Bid Tabulation / PO engines are not loaded on this page.' };
  /* timestamps a few seconds apart, so the logs read in the order things happened */
  let clock = Date.now();
  const tick = function () { clock += 4000; return new Date(clock).toISOString(); };

  epStore.clear();

  /* ---- 1. Bid Tabulation: best price on every line that has a quantity ---- */
  const q = epQLoad();
  const V = EP_BIDDERS.filter(function (b) { return b.state === 'submitted' && epPasses(b); }).map(function (b) {
    const o = epOfferOf(b.code) || {};
    return { code:b.code, name:b.name, short:b.shortName, ccy:o.ccy, deliv:o.deliv };
  });
  const rounds = JSON.parse(JSON.stringify(EP_ROUNDS_SEED));
  const round = epAwardDefaultRound(rounds, V);
  const sheet = epQSheet(round, V, rounds, null, q);
  const a = epAwardLoad();
  a.round = round; a.alloc = {}; a.excl = a.excl || {}; a.log = a.log || [];
  let awarded = 0;
  sheet.rows.forEach(function (x) {
    if (x.best && x.qty > 0) { a.alloc[x.item] = [{ code:x.best, qty:x.qty, how:'cherry' }]; awarded++; }
  });
  a.log.push({ on:tick(), by:EP_TENDER.buyer, txt:'Start Demo (Expediting): every line awarded to its best price — ' + awarded + ' line(s).' });
  const pco = epAwardPco(round);
  const view = epAwardView(a, sheet, pco, q);
  a.submittedOn = tick(); a.signs = [];
  a.fingerprint = epAwardFingerprint(a, view, round);
  a.log.push({ on:a.submittedOn, by:EP_TENDER.buyer, txt:'submitted for management approval — ' + awarded + ' line(s).' });
  EP_AWARD_SIGNATORIES.forEach(function (who, i) {
    const on = tick();
    a.signs.push({ role:who.role, name:who.name, on:on });
    a.log.push({ on:on, by:who.name, txt:'signed as ' + who.role + (i === EP_AWARD_SIGNATORIES.length - 1 ? ' — award approved.' : '.') });
  });
  a.approvals = [epAwardSnapshot(a, view, sheet, round, q, rounds, pco)];
  epAwardSave(a);

  /* ---- 2. PO Issuance: one order per supplier, signed and issued ---- */
  const sups = a.approvals[0].suppliers;
  const pos = [];
  sups.forEach(function (s, i) {
    const letter = String.fromCharCode(65 + i);
    const p = epPoFromAward({ tender:EP_TENDER, supplier:s, letter:letter });
    if (!p.incotermPlace) p.incotermPlace = String(s.origin || '').split(',')[0] || 'Mussafah';
    if (!p.incoterm) { p.incoterm = 'DAP'; p.incotermPlace = 'Mussafah'; }
    const wk = epQWeeks(s.deliv || '');
    const weeks = wk && (wk.max || wk.min) ? (wk.max || wk.min) : 12;
    const d = new Date(); d.setDate(d.getDate() + weeks * 7);
    p.lots = [{ id:'Lot 1', date:d.toISOString().slice(0, 10), grace:2, ld:true }];
    p.submittedOn = tick(); p.signs = []; p.fingerprint = epPoFingerprint(p);
    p.log.push({ on:p.submittedOn, by:p.buyer, txt:'Rev ' + epPoRevLabel(p) + ' submitted for approval (Start Demo).' });
    EP_PO_SIGNATORIES.forEach(function (who) {
      const on = tick();
      p.signs.push({ role:who.role, name:who.name, on:on });
      p.log.push({ on:on, by:who.name, txt:'signed as ' + who.role + '.' });
    });
    epPoIssue(p);
    pos.push(p);
  });
  epPoSave(EP_TENDER.ref, pos);

  /* ---- 3. Notify Expediting & PMT on each — this is what creates the records ---- */
  pos.forEach(function (p) { epPoNotify(p, EP_TENDER.buyer, 'both'); });
  epPoSave(EP_TENDER.ref, pos);
  const list = epExpLoad();
  list.forEach(function (r) {
    const p = pos.find(function (x) { return x.no === r.po; });
    r.demo = true;
    r.lotBasis = p ? 'issue date + quoted delivery "' + (p.quotedDeliv || '') + '"' : '';
  });
  epExpSave(list);

  return { ok:true, lines:awarded, orders:pos.map(function (p) {
    return { po:p.no, letter:p.letter, supplier:p.vendorShort, value:epPoTotals(p).total,
             lines:epPoTotals(p).count, incoterm:p.incoterm + ' ' + p.incotermPlace, lot:p.lots[0].date, deliv:p.quotedDeliv };
  }) };
}
