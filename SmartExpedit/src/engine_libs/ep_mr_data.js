/* ============================================================================
   SmartExpedit — Material Requisition register
   ----------------------------------------------------------------------------
   The buyer's MR inbox. An MR arrives here once the Commodity Lead has assigned
   it, and every later revision from Engineering arrives here too. Nothing moves
   downstream until the buyer approves the revision — that approval is what bumps
   the enquiry revision and restarts the cycle from the technical phase.

   Rev 0.00 is the MR this whole tender was floated on.
   Rev 1.00 is what Engineering issued after the technical phase closed.
   ============================================================================ */

/* ---------------------------------------------------------- Rev 1.00 BOM
   Rev 1.00 is not a second copy of the schedule — it is Rev 0.00 with the lines
   Engineering actually touched. Declaring it as a change set keeps the two
   revisions honestly in step: every line nobody touched is the SAME line, so
   the delta can never show a phantom difference from a transcription slip.

   The story: sour-service scope revised after the NACE MR0175 clarification,
   and coated items adjusted once the Xylan deviation was closed.             */

/* itemNo -> new TOTAL quantity */
const EP_MR_REV1_QTY = {
  /* top-ups — more sour-service scope than first released */
  1591: 42800, 1571: 9200, 1331: 3610, 1021: 2900, 3201: 1320, 1211: 1407,
  2121: 470,   2861: 400,  1483: 26,   1262: 18,   1053: 6,    1233: 24,
  /* reductions — scope pulled back after the coating clarification */
  1332: 310, 2541: 157, 1641: 120, 3401: 12,
  /* deletions — dropped from the scope entirely */
  1382: 0, 2871: 0, 1133: 0,
};

/* genuinely new line items — never quoted, so each needs its own TC round */
const EP_MR_REV1_NEW = [
  [60041,"SBLT021880","STUD BOLT 1\" x 165mm Lg CONTINUOUS THREADED;ASME B18.2.1/18.2.2;ASTM A320 L7M;ASTM A194 7M;HEAVY HEX HEAD NUT;WITH 2 NUT(S);PTFE COATED;NACE MR-01-75 / ISO 15156","EA",420,60,480,1,0.62,"5311.2820.202100201"],
  [60042,"SBLT021881","STUD BOLT 1-1/8\" x 190mm Lg CONTINUOUS THREADED;ASME B18.2.1/18.2.2;ASTM A320 L7M;ASTM A194 7M;HEAVY HEX HEAD NUT;WITH 2 NUT(S);PTFE COATED;NACE MR-01-75 / ISO 15156","EA",186,24,210,1,0.41,"5311.2820.202100201"],
  [60043,"WASH009914","WASHER SPRING 1\" NOM;ASME B18.21.1;ASTM A193 B7M;PTFE COATED;NACE MR-01-75 / ISO 15156","EA",960,0,960,1,0.18,"5311.2820.202100201"],
  [60044,"SBLT022310","STUD BOLT 1-1/2\" x 360mm Lg CONTINUOUS THREADED;ASME B18.2.1/18.2.2;ASTM B637 UNS N09925;ASTM B805 UNS N09925;HEAVY HEX HEAD NUT;WITH 3 NUT(S);NACE MR-01-75 / ISO 15156","EA",64,8,72,1,0.51,"5311.2820.202100201"],
];

/* Build Rev 1.00 from Rev 0.00 + the change set. Release/hold split moves with
   the total, and the weight scales with it — a top-up weighs more. */
function epBuildRev1() {
  const out = EP_MR_ITEMS.map(function (r) {
    if (!(r[0] in EP_MR_REV1_QTY)) return r.slice();
    const next = EP_MR_REV1_QTY[r[0]], prev = r[6];
    const c = r.slice();
    c[6] = next;
    c[5] = Math.min(r[5], next);            /* hold cannot exceed the total */
    c[4] = next - c[5];                     /* the rest is released */
    c[8] = prev ? Math.round(r[8] * next / prev * 1000) / 1000 : r[8];
    return c;
  });
  return out.concat(EP_MR_REV1_NEW.map(function (r) { return r.slice(); }));
}
const EP_MR_REV1_ITEMS = epBuildRev1();

/* The four new lines never existed at float, so they have no modelled base price
   yet. Derive them the same way every other line was derived — kg per piece from
   the real weight, times the rate its material grade implies. */
(function priceNewLines() {
  if (typeof EP_BASE_AED === 'undefined') return;
  const rate = function (d) {
    const u = (d || '').toUpperCase();
    if (u.indexOf('N09925') >= 0 || u.indexOf('B637') >= 0) return 380;
    if (u.indexOf('A320 L7M') >= 0 || u.indexOf('A194 7M') >= 0) return 22;
    if (u.indexOf('B7M') >= 0 || u.indexOf('2HM') >= 0) return 17;
    if (u.indexOf('WASHER') >= 0) return 15;
    return 13;
  };
  const SCALE = 1.3201;      /* the one calibration constant, same as the rest */
  EP_MR_REV1_NEW.forEach(function (r) {
    if (EP_BASE_AED[r[0]] !== undefined) return;
    const kg = r[6] ? (r[8] * 1000 / r[6]) : 0;
    EP_BASE_AED[r[0]] = Math.round(Math.max(0.35, kg * rate(r[2]) * SCALE) * 100) / 100;
  });
})();

/* ------------------------------------------------------------ MR register
   status: actioned  — enquiry already raised on this revision
           pending   — sitting with the buyer for approval
           superseded— replaced by a later approved revision                */
const EP_MR_REGISTER = [
  {
    ref: '2820-2025-74259', rev: '0.00',
    project: '2820', projectName: 'Lower Zakum LTDP-1 EPC Works for EPS-2 and PDP Project',
    client: 'ADNOC Offshore', materialHead: 'Bolts, Nuts & Washers',
    discipline: 'PIPING', commodityCode: 'H100 Piping', requisitionType: 'NORMAL',
    requisitionDate: '2026-07-17', receivedOn: '2026-07-18',
    assignedBy: 'Mohammed Khaled Bakkala', assignedByRole: 'Commodity Lead',
    assignedTo: 'Mohamed Amin', originator: 'REEMAL',
    engineer: 'Javid Sajith', reviewer: 'Kumar', approver: 'Arun Kumar',
    budget: 'USD 12,982,183',
    status: 'actioned', approvedOn: '2026-07-18',
    enquiryRef: '2025-74259', enquiryRev: '0.00',
    reason: 'Original issue — issued for purchase.',
    items: null,          /* null = the baseline, EP_MR_ITEMS */
  },
  {
    ref: '2820-2025-74259', rev: '1.00',
    project: '2820', projectName: 'Lower Zakum LTDP-1 EPC Works for EPS-2 and PDP Project',
    client: 'ADNOC Offshore', materialHead: 'Bolts, Nuts & Washers',
    discipline: 'PIPING', commodityCode: 'H100 Piping', requisitionType: 'NORMAL',
    requisitionDate: '2026-09-10', receivedOn: '2026-09-10',
    assignedBy: 'Mohammed Khaled Bakkala', assignedByRole: 'Commodity Lead',
    assignedTo: 'Mohamed Amin', originator: 'REEMAL',
    engineer: 'Javid Sajith', reviewer: 'Kumar', approver: 'Arun Kumar',
    budget: 'USD 12,982,183',
    status: 'pending', approvedOn: '',
    enquiryRef: '2025-74259', enquiryRev: '',
    reason: 'Re-issued after the technical phase. Sour-service scope revised following ' +
            'NACE MR0175 clarification; coated items adjusted after the Xylan deviation was closed.',
    items: 'REV1',        /* EP_MR_REV1_ITEMS */
  },
];

function epMrItems(entry) {
  return entry.items === 'REV1' ? EP_MR_REV1_ITEMS : EP_MR_ITEMS;
}

/* =========================================================================
   BOM DELTA — the same classification Module 3 (MR-PO Analysis) uses,
   matched on Vocab: Top-up / Reduction / Deletion / New Item / No Change.
   This is what the buyer approves, and what the vendors are asked to re-quote.
   ========================================================================= */
function epBomDelta(prevItems, nextItems) {
  const byItem = arr => { const m = {}; arr.forEach(r => m[r[0]] = r); return m; };
  const P = byItem(prevItems), N = byItem(nextItems);
  const keys = Object.keys(P).concat(Object.keys(N).filter(k => !P[k]));
  const rows = keys.map(k => {
    const p = P[k], n = N[k];
    if (!n) return { item:+k, vocab:p[1], desc:p[2], unit:p[3], prevQty:p[6], nextQty:0,
                     delta:-p[6], type:'Deletion' };
    if (!p) return { item:+k, vocab:n[1], desc:n[2], unit:n[3], prevQty:0, nextQty:n[6],
                     delta:n[6], type:'New Item' };
    const d = n[6] - p[6];
    /* A line taken to zero is out of scope, not merely reduced — a real MR keeps
       the line number in the schedule at zero rather than deleting the row. */
    return { item:+k, vocab:n[1], desc:n[2], unit:n[3], prevQty:p[6], nextQty:n[6], delta:d,
             type: d > 0 ? 'Top-up' : d < 0 ? (n[6] === 0 ? 'Deletion' : 'Reduction') : 'No Change' };
  });
  rows.sort((a, b) => a.item - b.item);
  const count = t => rows.filter(r => r.type === t).length;
  return { rows,
    summary: { topup:count('Top-up'), reduction:count('Reduction'), deletion:count('Deletion'),
               newItem:count('New Item'), noChange:count('No Change'),
               prevQty: prevItems.reduce((s, r) => s + r[6], 0),
               nextQty: nextItems.reduce((s, r) => s + r[6], 0) } };
}

/* How much confirmation a change needs, in the buyer's own words:
   a quantity top-up only needs quick word from Engineering; a NEW LINE ITEM
   needs a TC round, because the vendor may deviate on something never quoted. */
function epDeltaEffort(delta) {
  const needsTc = delta.rows.filter(r => r.type === 'New Item');
  const quick   = delta.rows.filter(r => r.type === 'Top-up' || r.type === 'Reduction' || r.type === 'Deletion');
  return { needsTc, quick,
    level: needsTc.length ? 'tc' : quick.length ? 'quick' : 'none' };
}

/* =========================================================================
   ENQUIRY REGISTER — the handover point between the Enquiry module and
   E-Procurement. Publish reads this; publishing an entry is what puts a
   tender on the Tender Desk.
     state: notready  — signature loop incomplete
            ready     — 5/5 signed, waiting to be floated
            published — live on the Tender Desk
            reissue   — an approved MR revision means it must go out again
   ========================================================================= */
const EP_ENQUIRY_REGISTER = [
  { ref:'2025-74259', rev:'0.00', project:'2820', head:'Bolts, Nuts & Washers',
    commodity:'H100 Piping', mrRef:'2820-2025-74259', bidders:6, signed:5,
    due:'2026-08-31T23:59:00', state:'published', publishedOn:'2026-08-04',
    value:'$9.7M', buyer:'Mohamed Amin' },
  { ref:'2024-73079', rev:'0.00', project:'2745', head:'Ball Valves',
    commodity:'H100 Piping', mrRef:'2745-2024-73079', bidders:8, signed:5,
    due:'2026-09-09T23:59:00', state:'published', publishedOn:'2026-08-18',
    value:'$1.2M', buyer:'Mohamed Amin' },
  { ref:'2025-74251', rev:'0.00', project:'2820', head:'Pipes - CS/LTCS',
    commodity:'H100 Piping', mrRef:'2820-2025-74251', bidders:7, signed:5,
    due:'2026-09-14T23:59:00', state:'published', publishedOn:'2026-08-25',
    value:'$540K', buyer:'Mohamed Amin' },
  { ref:'2024-72649', rev:'0.00', project:'2800', head:'Fittings',
    commodity:'H100 Piping', mrRef:'2800-2024-72649', bidders:6, signed:5,
    due:'2026-09-25T23:59:00', state:'published', publishedOn:'2026-09-01',
    value:'$68K', buyer:'Mohamed Amin' },

  /* the one waiting to be floated */
  { ref:'2026-75612', rev:'0.00', project:'2820', head:'Gaskets - Spiral Wound',
    commodity:'H100 Piping', mrRef:'2820-2026-75612', bidders:9, signed:5,
    due:'', state:'ready', publishedOn:'', value:'$310K', buyer:'Mohamed Amin' },

  /* still going round the signature loop */
  { ref:'2026-75640', rev:'0.00', project:'2745', head:'Pipe Supports',
    commodity:'H300 Structural', mrRef:'2745-2026-75640', bidders:5, signed:3,
    due:'', state:'notready', publishedOn:'', value:'$92K', buyer:'Mohamed Amin' },
];

/* =========================================================================
   REVISION CYCLE — one state machine, shared by all three modules.
   ---------------------------------------------------------------------
   Approving an MR revision does NOT put anything in front of the bidders.
   The buyer chooses one of two routes at the moment of approval:

     route 'cycle'  (the governed route — any change needing fresh approval)
       drafting  the revision is unlocked in the Enquiry module, nothing else
       signing   the revised enquiry was submitted; 5-signature loop running
       signed    management approved it; it now appears in Publish
       floated   re-issued to the bidders; the new BOM is finally live

     route 'direct' (no new enquiry — the change rides on the enquiry that is
       already out there, e.g. a pure quantity movement)
       signing   released for signature WITHOUT raising an enquiry revision
       signed    approved; it now appears in Publish
       floated   re-issued to the bidders on the same enquiry revision

   Both routes are signed before anything reaches a bidder. The only difference
   is whether a new enquiry revision is created to carry the change.

   Nothing downstream reads "approved". Everything reads "floated", which is
   the only moment the bidders actually hold the new MR and BOM.
   ========================================================================= */
const EP_REV_KEY = 'ep_enq_revisions';

/* ---------------------------------------------------------------- storage
   These three modules are separate pages. sessionStorage is per TAB and, on
   file://, often per FRAME too — which is why an approval made in the MR page
   could be invisible to E-Procurement sitting in the next iframe. localStorage
   is shared across tabs and frames on the same origin, so that is the store;
   sessionStorage is only the fallback if localStorage is blocked, and an
   in-memory map is the last resort so nothing ever throws.                  */
const EP_MEM = {};
const epStore = {
  get: function (k) {
    try { const v = localStorage.getItem(k); if (v !== null) return v; } catch (e) {}
    try { const v = sessionStorage.getItem(k); if (v !== null) return v; } catch (e) {}
    return EP_MEM[k] === undefined ? null : EP_MEM[k];
  },
  set: function (k, v) {
    EP_MEM[k] = v;
    try { localStorage.setItem(k, v); } catch (e) {
      try { sessionStorage.setItem(k, v); } catch (e2) {}
    }
    epBroadcast(k);
  },
  clear: function () {
    /* the Bid Tabulation module's quotations and award reset with the demo too */
    const extra = [];
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i);
      if (k && (k.indexOf('ep_quotes_') === 0 || k.indexOf('ep_award_') === 0 || k.indexOf('ep_pos_') === 0 || k === 'ep_po_open')) extra.push(k); } } catch (e) {}
    Object.keys(EP_MEM).forEach(function (k) { if (k.indexOf('ep_quotes_') === 0 || k.indexOf('ep_award_') === 0 || k.indexOf('ep_pos_') === 0 || k === 'ep_po_open') extra.push(k); });
    [EP_REV_KEY, 'ep_mr_approvals', 'ep_state', 'ep_exp_records'].concat(extra).forEach(function (k) {
      delete EP_MEM[k];
      try { localStorage.removeItem(k); } catch (e) {}
      try { sessionStorage.removeItem(k); } catch (e) {}
    });
    epBroadcast('*');
  },
};

/* Tell every other page in this window (and the shell's other iframes) that the
   shared state moved, so they re-render instead of showing a stale screen. A
   different TAB picks the same change up through the native 'storage' event. */
function epBroadcast(key) {
  const msg = { epState: true, key: key };
  try { window.postMessage(msg, '*'); } catch (e) {}
  try { if (window.parent && window.parent !== window) window.parent.postMessage(msg, '*'); } catch (e) {}
  try {
    if (window.parent && window.parent !== window && window.parent.frames) {
      for (let i = 0; i < window.parent.frames.length; i++) {
        try { window.parent.frames[i].postMessage(msg, '*'); } catch (e) {}
      }
    }
  } catch (e) {}
}

/* Every module calls this once with its own refresh function. */
function epOnStateChange(fn) {
  window.addEventListener('message', function (ev) {
    if (ev && ev.data && ev.data.epState) { try { fn(); } catch (e) {} }
  });
  window.addEventListener('storage', function (ev) {
    if (!ev.key || ev.key.indexOf('ep_') === 0) { try { fn(); } catch (e) {} }
  });
}

function epRevisions() {
  try { return JSON.parse(epStore.get(EP_REV_KEY) || '[]') || []; }
  catch (e) { return []; }
}
function epSaveRevisions(list) {
  epStore.set(EP_REV_KEY, JSON.stringify(list));
}
function epRevisionFor(enquiryRef) {
  const l = epRevisions().filter(r => r.enquiryRef === enquiryRef);
  return l.length ? l[l.length - 1] : null;
}
function epRevisionForMr(mrRef) {
  const l = epRevisions().filter(r => r.mrRef === mrRef);
  return l.length ? l[l.length - 1] : null;
}
/* called by the MR module the moment the buyer approves a revision */
function epStartRevision(rec) {
  const list = epRevisions().filter(r => !(r.mrRef === rec.mrRef && r.rev === rec.rev));
  const direct = rec.route === 'direct';
  list.push({
    enquiryRef: rec.enquiryRef, mrRef: rec.mrRef, rev: rec.rev,
    route: rec.route, approvedOn: rec.approvedOn,
    issuedOn: rec.issuedOn || '',        /* when Engineering issued the revision */
    /* the direct route skips raising an enquiry revision, NOT the signatures —
       it goes straight into the loop on the enquiry that is already out there */
    noEnquiryRev: direct,
    stage: direct ? 'signing' : 'drafting',
    signed: 0,
    submittedOn: direct ? rec.approvedOn : '', signedOn: '',
    floatedOn: '',
  });
  epSaveRevisions(list);
  return list[list.length - 1];
}
function epSetRevisionStage(mrRef, rev, stage, signed) {
  const list = epRevisions();
  const r = list.find(x => x.mrRef === mrRef && x.rev === rev);
  if (!r) return null;
  const today = new Date().toISOString().slice(0, 10);
  r.stage = stage;
  if (typeof signed === 'number') r.signed = signed;
  if (stage === 'signing' && !r.submittedOn) r.submittedOn = today;
  if (stage === 'signed'  && !r.signedOn)    r.signedOn    = today;
  if (stage === 'floated' && !r.floatedOn)   r.floatedOn   = today;
  epSaveRevisions(list);
  return r;
}
/* The enquiry's own revision number. It stays at the floated revision until the
   revised enquiry is actually submitted — a draft nobody signed is not Rev 1.00. */
function epEnquiryRev(enquiryRef, baseRev) {
  const r = epRevisionFor(enquiryRef);
  /* a direct release never bumps the enquiry — that is the whole point of it */
  if (!r || r.stage === 'drafting' || r.noEnquiryRev) return baseRev || '0.00';
  return r.rev;
}
/* Is the buyer allowed to revise this enquiry right now? Only an approved MR
   revision on the 'cycle' route unlocks it — nothing else bumps a revision. */
function epCanRevise(enquiryRef) {
  const r = epRevisionFor(enquiryRef);
  if (!r) return { ok:false, reason:'No approved MR revision. Engineering must issue a revision and ' +
                                   'you must approve it in Material Requisition first.' };
  if (r.route === 'direct') return { ok:false, rev:r.rev,
    reason:'MR Rev ' + r.rev + ' was approved for release without a new enquiry revision — it rides on ' +
           'the enquiry already out there, so there is nothing to revise here. Its signatures are ' +
           'collected in the Material Requisition module.' };
  if (r.stage === 'drafting') return { ok:true, rev:r.rev };
  return { ok:false, rev:r.rev,
    reason:'Rev ' + r.rev + ' is already ' + (r.stage === 'signing' ? 'out for signature'
          : r.stage === 'signed' ? 'signed and waiting to be floated in E-Procurement'
          : 'floated to the bidders') + '.' };
}

/* Fold the live revision cycle into the enquiry register Publish reads. */
function epApplyMrApprovals(register) {
  register.forEach(e => {
    const r = epRevisionFor(e.ref);
    if (!r) return;
    e.revStage = r.stage; e.revRoute = r.route; e.reissueOn = r.approvedOn;
    if (r.stage === 'floated') {
      /* keep the ORIGINAL float date — Rev 0.00's cycle is reconstructed from it,
         and a re-issue must not rewrite when the tender was first floated */
      if (!e.firstPublishedOn) e.firstPublishedOn = e.publishedOn;
      if (!r.noEnquiryRev) e.rev = r.rev;      /* a direct release leaves the enquiry rev alone */
      e.mrRevOut = r.rev;                      /* but the bidders do hold this MR revision */
      e.state = 'published';
      e.publishedOn = r.floatedOn || r.approvedOn;
      delete e.pendingRev;
    } else if (r.stage === 'signed') {
      e.state = 'reissue'; e.pendingRev = r.rev; e.signed = 5;
    } else {
      e.state = 'revpending'; e.pendingRev = r.rev; e.signed = r.signed || 0;
    }
  });
  return register;
}

/* =========================================================================
   REVISION TRAIL — every revision an enquiry has ever had, oldest first.
   Rev 0.00 is not in sessionStorage: it is the original float, and it is
   reconstructed from the enquiry register so the trail is never missing its
   first entry. Everything after it comes from the live cycle.
   ========================================================================= */
/* The same five names the Enquiry module routes to. Declared here because the MR
   module needs them too and does not load the E-Procurement data layer. */
const EP_MR_SIGNATORIES = [
  { name:'Anand Bakshi',            code:'Anandb',      role:'Lead Buyer' },
  { name:'Mohammed Khaled Bakkala', code:'Mohamed MKB', role:'Commodity Lead' },
  { name:'Ahmed Al Nuami',          code:'Ahmedan',     role:'Engineering (Piping)' },
  { name:'Sherif Elbheiry',         code:'Sherife',     role:'QA / QC' },
  { name:'Sherife Aboelgheit',      code:'Sherifa',     role:'Procurement Manager' },
];

const EP_REV_STAGES = [
  { key:'issued',    label:'Revision issued by Engineering', sub:'lands in the buyer’s MR inbox' },
  { key:'approved',  label:'Approved by the buyer',          sub:'in Material Requisition' },
  { key:'submitted', label:'Released for signature',         sub:'revised enquiry submitted for signature' },
  { key:'signed',    label:'Signature loop complete',        sub:'management authorises the float' },
  { key:'floated',   label:'Floated to the bidders',         sub:'from E-Procurement → Publish' },
  { key:'quoted',    label:'Offers received',                sub:'priced against this revision' },
];

function epRevisionTrail(enq) {
  const trail = [];
  /* Rev 0.00 — the original issue, reconstructed from the register */
  const floated0 = enq.state === 'published' || enq.publishedOn;
  trail.push({
    rev: '0.00', origin: 'original', route: 'cycle',
    stage: floated0 ? (enq.state === 'published' || enq.rev !== '0.00' ? 'quoted' : 'floated')
                    : (enq.signed >= 5 ? 'signed' : 'submitted'),
    signed: enq.signed, mrRef: enq.mrRef, enquiryRef: enq.ref,
    issuedOn: '', approvedOn: '', submittedOn: '',
    signedOn: '', floatedOn: enq.firstPublishedOn || enq.publishedOn || '',
  });
  epRevisions().filter(r => r.enquiryRef === enq.ref)
    .sort((a, b) => parseFloat(a.rev) - parseFloat(b.rev))
    .forEach(r => trail.push(Object.assign({ origin: 'revision' }, r)));
  return trail;
}

/* Which stage a revision is currently ON — everything before it is done.
   1-based against EP_REV_STAGES; one past the end means the cycle is finished. */
function epRevStageIndex(r) {
  const order = { drafting:3, signing:4, signed:5, floated:6, quoted:7 };
  if (r.origin === 'original') {
    return r.stage === 'quoted' ? 7 : r.stage === 'floated' ? 6 : r.stage === 'signed' ? 5 : 4;
  }
  return order[r.stage] || 1;
}
function epRevStageDate(r, key) {
  return ({ issued: r.issuedOn, approved: r.approvedOn, submitted: r.submittedOn,
            signed: r.signedOn, floated: r.floatedOn, quoted: '' })[key] || '';
}
function epMrFmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso); if (isNaN(d)) return iso;
  const M = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return String(d.getDate()).padStart(2, '0') + '-' + M[d.getMonth()] + '-' + d.getFullYear();
}
function epRevLabel(r) {
  if (r.origin === 'original') return r.floatedOn ? 'Floated ' + epMrFmtDate(r.floatedOn) : 'Original issue';
  return ({ drafting:'Approved — revision not yet raised',
            signing:'Out for signature (' + (r.signed || 0) + '/5)',
            signed:'Signed — ready to re-issue',
            floated: (r.route === 'direct' ? 'Released directly to bidders ' : 'Re-issued to bidders ')
                     + epMrFmtDate(r.floatedOn)
          })[r.stage] || r.stage;
}
