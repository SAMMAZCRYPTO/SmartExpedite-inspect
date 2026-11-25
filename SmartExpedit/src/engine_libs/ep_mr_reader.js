/* ============================================================================
   SmartExpedit — MR READER (MR Study)
   ----------------------------------------------------------------------------
   Mohamed Amin's mechanism, step by step:
     1. read the TABLE OF CONTENTS (pages 1-3 of a ProMat MR) and find the
        attachments titled ITR (Inspection Test Requirements) and SDR
        (Supplier Data Requirements) — ATTACH-VI and ATTACH-VII on 74259, but
        the numbers are read, never assumed;
     2. find those attachments' pages by their own header
        ("Attachment - VII ... Page n of 5"), searching from the back of the
        file — counting pages from the contents does not work, every
        attachment carries a cover sheet;
     3. render the pages so the expeditor checks them with his own eye;
     4. turn the SDR into a table (code, copies with bid, priority, first
        issue, date required, review class, dossier, remarks, and the long
        description from the notes pages) and the ITR into a table
        (activity x inspection level I-IV + Company, H/W/R/M).

   The PDF engine is pdf.js (ep_pdf_lib.js), loaded from a blob URL so it
   works on file:// with no CDN. Everything here is plain functions; the page
   that calls it owns the UI.
   ============================================================================ */

var EP_PDF = null;
async function epPdfLib() {
  if (EP_PDF) return EP_PDF;
  if (typeof EP_PDF_LIB_SRC === 'undefined') throw new Error('PDF reader not loaded (ep_pdf_lib.js)');
  const lib = await import(URL.createObjectURL(new Blob([EP_PDF_LIB_SRC], { type:'text/javascript' })));
  lib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(new Blob([EP_PDF_WORKER_SRC], { type:'text/javascript' }));
  EP_PDF = lib;
  return lib;
}

async function epPdfOpen(buf) {
  const lib = await epPdfLib();
  return lib.getDocument({ data: new Uint8Array(buf), verbosity: 0 }).promise;
}

/* one page -> lines (top to bottom), each line its items left to right */
async function epPdfLines(doc, pn) {
  const pg = await doc.getPage(pn);
  const tc = await pg.getTextContent();
  const items = tc.items.filter(function (it) { return it.str && it.str.trim(); })
    .map(function (it) { return { x: it.transform[4], y: it.transform[5], s: it.str.trim() }; })
    .sort(function (a, b) { return b.y - a.y || a.x - b.x; });
  const lines = [];
  items.forEach(function (it) {
    const L = lines.find(function (l) { return Math.abs(l.y - it.y) <= 3; });
    if (L) L.items.push(it); else lines.push({ y: it.y, items: [it] });
  });
  lines.forEach(function (l) {
    l.items.sort(function (a, b) { return a.x - b.x; });
    l.text = l.items.map(function (i) { return i.s; }).join(' ');
  });
  lines.sort(function (a, b) { return b.y - a.y; });
  return lines;
}

async function epPdfText(doc, pn) {
  const pg = await doc.getPage(pn);
  const tc = await pg.getTextContent();
  return tc.items.map(function (i) { return i.str; }).join(' ');
}

const EP_ROMAN = { I:1, II:2, III:3, IV:4, V:5, VI:6, VII:7, VIII:8, IX:9, X:10, XI:11, XII:12 };

/* ---------------------------------------------------------- 1. CONTENTS */
async function epMrReadToc(doc, onStep) {
  const head = { req:'', client:'', job:'', material:'', rev:'', date:'' };
  const atts = [];
  const tocPages = [];
  const upto = Math.min(4, doc.numPages);
  for (let pn = 1; pn <= upto; pn++) {
    const lines = await epPdfLines(doc, pn);
    const all = lines.map(function (l) { return l.text; }).join('\n');
    if (pn === 1 || !head.req) {
      const m = all.match(/(\d{4}\/\d{4}\/\d{4,6})/); if (m && !head.req) head.req = m[1];
      /* a labelled field: the label item, then the value items a little to its right
         on the same line or one within a few points (the cover's two-column grid) */
      const items = []; lines.forEach(function (l) { l.items.forEach(function (it) { items.push(it); }); });
      const field = function (label) {
        const L = items.find(function (it) { return it.s === label; });
        if (!L) return '';
        return items.filter(function (it) { return it !== L && Math.abs(it.y - L.y) <= 4 && it.x > L.x + 20 && it.x < 400; })
          .sort(function (a, b) { return a.x - b.x; }).map(function (it) { return it.s; }).join(' ').trim();
      };
      if (!head.client) head.client = field('Client');
      if (!head.job) head.job = field('Job Name');
      if (!head.material) head.material = field('Material');
      const d = all.match(/(\d{2}[-\/](?:[A-Za-z]{3}|\d{2})[-\/]\d{4})/); if (d && !head.date) head.date = d[1];
    }
    if (!/TABLE\s*OF\s*CONTENTS|T A B L E/.test(all)) continue;
    tocPages.push(pn);
    lines.forEach(function (l, i) {
      const a = l.text.match(/ATTACH\s*-\s*([IVX]+)\b/);
      if (!a) return;
      /* the title sits on the same line or one a few points above/below */
      const near = lines.filter(function (k) { return Math.abs(k.y - l.y) <= 4; });
      const text = near.map(function (k) { return k.text; }).join(' ');
      const title = text.replace(/^\s*\d+\s*/, '').replace(/ATTACH\s*-\s*[IVX]+/, '').replace(/\s-\s/, ' ')
        .replace(/\bNot Used\b/i, '').replace(/\s+\d+\s*$/, '').replace(/^\s*[-\d\s]*\s*/, '').trim();
      const pagesM = text.match(/(\d+)\s*$/);
      if (atts.some(function (x) { return x.roman === a[1]; })) return;
      atts.push({ roman: a[1], no: EP_ROMAN[a[1]] || 0, title: title, pages: pagesM ? +pagesM[1] : 0,
                  notUsed: /Not Used/i.test(text), tocPage: pn });
    });
    if (onStep) onStep('Contents page ' + pn + ' read');
  }
  /* titles of attachments that list sub-documents can sit on the line above the number */
  const itr = atts.find(function (x) { return /\bITR\b|INSPECTION\s+TEST/i.test(x.title); }) || null;
  const sdr = atts.find(function (x) { return /\bSDR\b|SUPPLIER\s+DATA/i.test(x.title); }) || null;
  return { head: head, tocPages: tocPages, attachments: atts, itr: itr, sdr: sdr };
}

/* ---------------------------------------------- 2. LOCATE BY PAGE HEADER */
async function epMrLocate(doc, romans, onStep) {
  const found = {}; romans.forEach(function (r) { found[r] = { pages: {}, of: 0, cover: 0 }; });
  const done = function () {
    return romans.every(function (r) { const f = found[r]; return f.of && Object.keys(f.pages).length >= f.of; });
  };
  let scanned = 0;
  for (let pn = doc.numPages; pn >= 1; pn--) {
    const t = await epPdfText(doc, pn);
    scanned++;
    const a = t.match(/Attachment\s*-\s*([IVX]+)\b/i);
    const p = t.match(/Page\s+(\d+)\s+of\s+(\d+)/i);
    if (a && p) {
      const r = a[1].toUpperCase();
      if (found[r]) { found[r].pages[+p[1]] = pn; found[r].of = +p[2]; }
    }
    if (onStep && scanned % 10 === 0) onStep('Searching from the back — page ' + pn);
    if (done()) break;
    if (scanned > 400) break;          /* attachments VI/VII sit at the back of a ProMat MR */
  }
  romans.forEach(function (r) {
    const f = found[r];
    f.list = Object.keys(f.pages).map(Number).sort(function (a, b) { return a - b; }).map(function (k) { return f.pages[k]; });
    f.cover = f.list.length ? f.list[0] - 1 : 0;   /* the cover sheet sits just before page 1 */
  });
  return { found: found, scanned: scanned };
}

/* ------------------------------------------------------- 3. RENDER PAGES */
async function epMrRender(doc, pn, scale, quality) {
  const pg = await doc.getPage(pn);
  const vp = pg.getViewport({ scale: scale || 1.25 });
  const c = document.createElement('canvas');
  c.width = Math.round(vp.width); c.height = Math.round(vp.height);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
  await pg.render({ canvasContext: ctx, viewport: vp }).promise;
  return c.toDataURL('image/jpeg', quality || 0.72);
}

/* ------------------------------------------------------- 4a. SDR TABLE */
function epMrParseSdr(pagesLines) {
  const rows = [], notes = {};
  let cols = null, inTable = true, notesMode = false, cur = null, curNote = null;
  const codeRe = /^[A-Z]\d{3}$/;
  pagesLines.forEach(function (lines) {
    lines.forEach(function (l) {
      const t = l.text;
      if (/Supplier Data Requirements|PR No\.|Attachment\s*-|ProMat|^\d{4}\/\d{4}\/\d+$|Rev\s*-\s*\d/.test(t) && !codeRe.test(l.items[0].s)) return;
      /* column markers (1)..(7) */
      if (/\(1\).*\(2\).*\(3\)/.test(t) && !/Quantity/.test(t)) {
        cols = l.items.filter(function (i) { return /^\(\d\)$/.test(i.s); }).map(function (i) { return i.x + 4; });
        return;
      }
      /* legend ends the table; the per-code descriptions follow */
      if (/Quantity and type of submi/.test(t)) { inTable = false; cur = null; return; }
      if (/^\(\d\)/.test(t) && !inTable) return;
      const first = l.items[0];
      if (inTable && cols && cols.length >= 7) {
        const descEnd = cols[0] - 14, remStart = cols[5] + (cols[6] - cols[5]) * 0.4;
        if (codeRe.test(first.s)) {
          cur = { code: first.s, desc: '', withBid: '', priority: '', firstIssue: '', dateReq: '', review: '', dossier: '', remarks: '' };
          rows.push(cur);
          l.items.slice(1).forEach(place);
        } else if (cur) {
          l.items.forEach(place);
        }
        return;
      }
      if (!inTable) {
        if (codeRe.test(first.s)) {
          curNote = first.s; notes[curNote] = notes[curNote] || [];
          return;                     /* the title repeats the table */
        }
        if (curNote) notes[curNote].push(t);
      }
      function place(it) {
        const descEnd = cols[0] - 14, remStart = cols[5] + (cols[6] - cols[5]) * 0.4;
        if (it.x < descEnd) { cur.desc = (cur.desc ? cur.desc + ' ' : '') + it.s; return; }
        if (it.x >= remStart) { cur.remarks = (cur.remarks ? cur.remarks + ' ' : '') + it.s; return; }
        let best = 0, bd = 1e9;
        for (let k = 0; k < 6; k++) { const d = Math.abs(it.x - cols[k]); if (d < bd) { bd = d; best = k; } }
        const key = ['withBid', 'priority', 'firstIssue', 'dateReq', 'review', 'dossier'][best];
        cur[key] = (cur[key] ? cur[key] + ' ' : '') + it.s;
      }
    });
  });
  rows.forEach(function (r) {
    r.note = (notes[r.code] || []).join(' ').replace(/\s+/g, ' ').trim();
    r.remarks = r.remarks.replace(/wherevever/g, 'wherever');
  });
  return rows;
}

/* "2W" -> 14 days, "5W" -> 35, "3D" -> 3, "1M" -> 30; FINAL / WM -> null */
function epMrSdrDays(dateReq) {
  const m = String(dateReq || '').trim().match(/^(\d+)\s*([DWM])$/i);
  if (!m) return null;
  return +m[1] * ({ D: 1, W: 7, M: 30 }[m[2].toUpperCase()]);
}

/* ------------------------------------------------------- 4b. ITR TABLE */
function epMrParseItr(pagesLines) {
  const out = { rows: [], notes: [], levelCols: null, compCol: null, level: '', criticality: '' };
  let section = '', cur = null, inTable = false, inNotes = false, lvlX = null;
  pagesLines.forEach(function (lines) {
    lines.forEach(function (l) {
      const t = l.text;
      if (/Inspection \/ Test Activity/.test(t)) {
        inTable = true;
        const c = l.items.find(function (i) { return /^Comp\.?$/.test(i.s); });
        const rm = l.items.find(function (i) { return /^Remarks$/.test(i.s); });
        out.compCol = c ? c.x : null; out.remCol = rm ? rm.x : null;
        return;
      }
      if (!inTable) return;
      if (/^Level/.test(t) && l.items.every(function (i) { return /^Level$/.test(i.s); })) {
        lvlX = l.items.map(function (i) { return i.x; }); out.levelCols = lvlX; return;
      }
      if (/^I\b/.test(t) && lvlX && l.items.length <= 4 && t.replace(/[IV\s]/g, '') === '') return;
      if (/^Notes$/.test(t)) { inNotes = true; cur = null; return; }
      if (/ProMat|Inspection and Testing Requirements|PR No\.|Attachment\s*-/.test(t)) return;
      if (inNotes) {
        if (/^\d+\./.test(t)) out.notes.push(t); else if (out.notes.length) out.notes[out.notes.length - 1] += ' ' + t;
        return;
      }
      const left = l.items.filter(function (i) { return i.x < (lvlX ? lvlX[0] - 10 : 300); });
      const vals = l.items.filter(function (i) { return i.x >= (lvlX ? lvlX[0] - 10 : 300) && (!out.remCol || i.x < out.remCol - 25); });
      const rem = l.items.filter(function (i) { return out.remCol && i.x >= out.remCol - 25; });
      if (left.length && !vals.length && !rem.length && left[0].x < 40) { section = left.map(function (i) { return i.s; }).join(' '); cur = null; return; }
      if (left.length) {
        cur = { section: section, activity: left.map(function (i) { return i.s; }).join(' '), I: '', II: '', III: '', IV: '', Comp: '', remarks: '' };
        out.rows.push(cur);
      }
      if (!cur) return;
      vals.forEach(function (v) {
        const cands = (lvlX || []).map(function (x, k) { return { k: ['I', 'II', 'III', 'IV'][k], x: x + 6 }; });
        if (out.compCol != null) cands.push({ k: 'Comp', x: out.compCol + 8 });
        let best = null, bd = 1e9;
        cands.forEach(function (c) { const d = Math.abs(v.x - c.x); if (d < bd) { bd = d; best = c.k; } });
        if (best) cur[best] = (cur[best] ? cur[best] + ' ' : '') + v.s;
      });
      rem.forEach(function (r) { cur.remarks = (cur.remarks ? cur.remarks + ' ' : '') + r.s; });
    });
  });
  const lv = out.notes.join(' ').match(/Inspection level\s*\/\s*Class:\s*(\d)/i);
  const cr = out.notes.join(' ').match(/Criticality rating:\s*(\d)/i);
  out.level = lv ? ['', 'I', 'II', 'III', 'IV'][+lv[1]] || lv[1] : '';
  out.criticality = cr ? cr[1] : '';
  if (!out.level) {
    const used = ['I', 'II', 'III', 'IV'].filter(function (k) { return out.rows.some(function (r) { return r[k]; }); });
    if (used.length === 1) out.level = used[0];
  }
  return out;
}

/* hold / witness points the schedule must carry (template rule 4) */
function epMrItrPoints(itr) {
  if (!itr || !itr.rows) return [];
  const lv = itr.level || 'III';
  return itr.rows.map(function (r) {
    const n = r[lv] || '', c = r.Comp || '';
    const kind = /H/.test(n + c) ? 'H' : /W/.test(n + c) ? 'W' : '';
    return { activity: r.activity, section: r.section, npcc: n, company: c, kind: kind };
  }).filter(function (p) { return p.kind; });
}

/* ------------------------------------------------------- THE WHOLE RUN */
async function epMrExtract(buf, fileName, onStep, opts) {
  opts = opts || {};
  const step = function (s) { if (onStep) onStep(s); };
  step('Opening ' + (fileName || 'the MR') + '…');
  const doc = await epPdfOpen(buf);
  step(doc.numPages + ' pages — reading the table of contents');
  const toc = await epMrReadToc(doc, step);
  const romans = [toc.itr && toc.itr.roman, toc.sdr && toc.sdr.roman].filter(Boolean);
  if (!romans.length) return { ok: false, msg: 'No ITR or SDR attachment found in the table of contents.', toc: toc, pages: doc.numPages };
  step('Contents say ' + romans.map(function (r) { return 'ATTACH-' + r; }).join(' and ') + ' — finding their pages');
  const loc = await epMrLocate(doc, romans, step);
  const res = { ok: true, file: fileName || '', pages: doc.numPages, toc: toc, scanned: loc.scanned,
                itr: null, sdr: null, images: {}, readOn: new Date().toISOString() };
  for (const kind of ['itr', 'sdr']) {
    const a = toc[kind]; if (!a) continue;
    const f = loc.found[a.roman];
    const lines = [];
    for (const pn of f.list) lines.push(await epPdfLines(doc, pn));
    res[kind] = { roman: a.roman, title: a.title, tocPages: a.pages, pages: f.list, cover: f.cover,
                  complete: f.list.length === (f.of || a.pages) };
    if (kind === 'sdr') res.sdr.rows = epMrParseSdr(lines);
    else Object.assign(res.itr, epMrParseItr(lines));
    if (opts.render !== false) {
      for (const pn of f.list) {
        step('Rendering page ' + pn + ' for review');
        res.images[pn] = await epMrRender(doc, pn, opts.scale || 1.25, opts.quality || 0.72);
      }
    }
  }
  step('Done — ' + (res.sdr ? res.sdr.rows.length + ' SDR codes' : 'no SDR') + ', ' +
       (res.itr ? res.itr.rows.length + ' ITR activities' : 'no ITR'));
  return res;
}
