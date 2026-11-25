/* MR reader — Saudi Aramco fallback.
   Some Aramco MRs mark Attachment VI (ITR) and VII (SDR) "Not Used" and refer to Attachment V,
   where the Saudi Aramco ITR forms (175-xxxxxx) and NMR forms (SA-79xx) are listed.
   This fallback reads that list from the contents, finds the filled NMR forms by their own page
   header ("Saudi Aramco 7902 (08/06) Page 1 of 3"), and reads the NMR items (601, 602 …) with
   their priority. The standard reader runs first; this only runs when it cannot finish. */
(function () {
  var std = window.epMrExtract;
  var FORM_RE = /\b(175-\d{6}|SA-\d{4}|\d{4}-[A-Z]-SITR-\d+|SAEP-\d+)\b\s+([0-9A-Z\/]{1,6})\s+(ITR|NMR)\s*:\s*(.+?)\s+(\d{1,3})\s*$/;

  async function aramco(buf, fileName, onStep, opts, first) {
    opts = opts || {};
    var pct = 0, step = function (s, p) { if (p != null) pct = Math.max(pct, Math.min(100, Math.round(p))); if (onStep) onStep(s + ' — ' + pct + '%'); };
    var doc = await epPdfOpen(buf);
    step('Aramco format check: reading the contents', 2);
    /* contents and head: the first 10 pages */
    var lines = [], toc = (first && first.toc) || null, upto = Math.min(10, doc.numPages), tocPages = [], text = '';
    for (var pn = 1; pn <= upto; pn++) {
      var L = await epPdfLines(doc, pn), t = L.map(function (l) { return l.text; }).join('\n');
      text += t + '\n';
      if (/T\s*A\s*B\s*L\s*E\s*O\s*F\s*C\s*O\s*N\s*T\s*E\s*N\s*T\s*S/.test(t)) { tocPages.push(pn); L.forEach(function (l) { lines.push({ pn:pn, l:l }); }); }
      step('Contents page ' + pn, 2 + pn);
    }
    var refersV = /Not Used[\s\S]{0,120}ITR[\s\S]{0,200}Refer\s+ATTACHMENT\s*-\s*V/i.test(text) || /Refer\s+ATTACHMENT\s*-\s*V\s+of\s+the\s+MR\s+for\s+Saudi\s+Aramco/i.test(text);
    if (!refersV) return first;
    if (!toc) toc = await epMrReadToc(doc);
    /* attachments from all contents pages (the standard reader stops at page 4) */
    var atts = [];
    lines.forEach(function (x) {
      var a = x.l.text.match(/ATTACH\s*-\s*([IVX]+)\b/); if (!a || atts.some(function (q) { return q.roman === a[1]; })) return;
      var tt = x.l.text, title = tt.replace(/^\s*\d+\s*/, '').replace(/ATTACH\s*-\s*[IVX]+/, '').replace(/\bNot Used\b/i, '').replace(/\s+\d+\s*$/, '').replace(/^[-\s\d]*/, '').trim();
      atts.push({ roman:a[1], no:EP_ROMAN[a[1]] || 0, title:title, pages:+((tt.match(/(\d+)\s*$/) || [])[1] || 0), notUsed:/Not Used/i.test(tt), tocPage:x.pn });
    });
    toc.attachments = atts.length ? atts : toc.attachments; toc.tocPages = tocPages;
    /* forms listed under Attachment V */
    var forms = [], last = null;
    lines.forEach(function (x) {
      var m = x.l.text.match(FORM_RE);
      if (m) { last = { no:m[1], rev:m[2], kind:m[3], title:m[4].trim(), pages:+m[5], tocPage:x.pn }; if (!forms.some(function (f) { return f.no === last.no; })) forms.push(last); else last = null; return; }
      /* a wrapped title continues on the next line, in the title column, with no document number */
      if (last && /^[A-Z&(),\/\- ]{3,}$/.test(x.l.text.trim()) && !/ATTACH|TABLE|CONTENTS|PLATFORMS|Job Name|Requisition/.test(x.l.text)) last.title += ' ' + x.l.text.trim();
      else last = null;
    });
    var itrForms = forms.filter(function (f) { return f.kind === 'ITR'; }), nmrForms = forms.filter(function (f) { return f.kind === 'NMR'; });
    step('Attachment V lists ' + itrForms.length + ' ITR forms and ' + nmrForms.length + ' NMR forms', 15);
    /* inspection level stated in the technical requirements (first 40 pages) */
    var level = '', lm = text.match(/Inspection level for this requisition is Level\s*(\d)/i);
    for (var p2 = upto + 1; !lm && p2 <= Math.min(40, doc.numPages); p2++) { lm = (await epPdfText(doc, p2)).match(/Inspection level for this requisition is Level\s*(\d)/i); step('Looking for the inspection level, page ' + p2, 15 + (p2 - upto) / 30 * 5); }
    if (lm) level = lm[1];
    /* find the filled NMR forms by their page header, from the back */
    var want = {}; nmrForms.forEach(function (f) { want[f.no.replace(/^SA-/, '')] = { form:f, pages:{}, of:f.pages || 0 }; });
    var keys = Object.keys(want), done = function () { return keys.every(function (k) { var w = want[k]; return w.of && Object.keys(w.pages).length >= w.of; }); };
    var limit = Math.min(doc.numPages, 1200), scanned = 0;
    for (var pg = doc.numPages; pg >= 1 && keys.length && !done() && scanned < limit; pg--) {
      var tx = await epPdfText(doc, pg); scanned++;
      var h = tx.match(/Saudi Aramco\s+(79\d\d)\s*\(\d\d\/\d\d\)\s*Page\s+(\d+)\s+of\s+(\d+)/i);
      if (h && want[h[1]] && !want[h[1]].pages[+h[2]]) { want[h[1]].pages[+h[2]] = pg; want[h[1]].of = +h[3]; }
      if (scanned % 10 === 0) step('Searching for the NMR forms from the back, page ' + pg, 20 + scanned / limit * 50);
    }
    /* read NMR items: "601. PRELIMINARY DRAWINGS …" then "1. GA DRAWING … 1" (last number = priority) */
    var rows = [], nmrPages = [], kk = 0;
    for (var k of keys) {
      var w = want[k], list = Object.keys(w.pages).map(Number).sort(function (a, b) { return a - b; }).map(function (q) { return w.pages[q]; });
      w.list = list; nmrPages = nmrPages.concat(list); var sec = null, cur = null;
      for (var lp of list) {
        var LL = await epPdfLines(doc, lp); if (!LL.some(function (l) { return /NONMATERIAL REQUIREMENTS/.test(l.text); })) { kk++; continue; }
        LL.forEach(function (l) {
          var t = l.text.trim(), s = t.match(/^(\d{3})\.\s+(.+)$/), it = t.match(/^(?:\d+\s+)?(\d{1,2})\.\s+(.+?)\s+(\d)\s*$/);
          if (/^NOTES?\s*:|^\(?[A-E]\)\s|BIDDER'S SIGNATURE|^Saudi Aramco/.test(t)) { cur = null; if (/^NOTES?\s*:/.test(t)) sec = null; return; }
          if (s && +s[1] >= 100) { sec = { code:s[1], title:s[2].trim() }; cur = null; return; }
          if (sec && it) { cur = { code:k + '/' + sec.code + '.' + it[1], desc:it[2].trim(), section:sec.code + ' ' + sec.title, priority:it[3], form:'SA-' + k, formTitle:w.form.title, withBid:'', firstIssue:'', dateReq:'', review:'', dossier:'', remarks:'' }; rows.push(cur); return; }
          if (cur && /^[A-Z0-9][A-Z0-9 ,;:&\/()\-.'+]*$/.test(t) && t.length > 3 && !/^\d+$/.test(t)) cur.desc += ' ' + t;
        });
        kk++; step('Reading NMR form SA-' + k + ', page ' + lp, 70 + kk / Math.max(1, nmrPages.length + 4) * 15);
      }
    }
    var res = { ok:true, aramco:true, file:fileName || '', pages:doc.numPages, toc:toc, scanned:scanned, readOn:new Date().toISOString(), images:{},
      itr:{ roman:'V', title:'Saudi Aramco ITR forms (listed in Attachment V)', tocPages:itrForms.length, pages:tocPages.slice(), cover:0, complete:true, level:level, criticality:'', notes:[],
        rows:itrForms.map(function (f) { return { section:'ITR form', activity:f.no + ' — ' + f.title, I:'', II:'', III:'', IV:'', Comp:'', remarks:'Rev ' + f.rev + ' · ' + f.pages + ' page(s)' }; }), forms:itrForms },
      sdr:{ roman:'V', title:'Saudi Aramco NMR forms (Attachment V)', tocPages:nmrForms.length, pages:nmrPages, cover:0, complete:keys.every(function (q) { return want[q].of && want[q].list.length >= want[q].of; }), rows:rows, forms:nmrForms.map(function (f) { var w = want[f.no.replace(/^SA-/, '')]; return Object.assign({ found:w.list.length, of:w.of }, f); }) } };
    if (opts.render !== false) {
      var all = tocPages.concat(nmrPages), r = 0;
      for (var pr of all) { res.images[pr] = await epMrRender(doc, pr, opts.scale || 1.25, opts.quality || 0.72); r++; step('Rendering page ' + pr + ' for review', 85 + r / all.length * 15); }
    }
    step('Done — ' + itrForms.length + ' ITR forms, ' + nmrForms.length + ' NMR forms, ' + rows.length + ' NMR items' + (res.sdr.complete ? '' : ' (some NMR pages not found)'), 100);
    return res;
  }

  window.epMrExtract = async function (buf, fileName, onStep, opts) {
    var copy = buf.slice(0), first = null;
    try { first = await std(buf, fileName, onStep, opts); } catch (e) { first = { ok:false, msg:e.message }; }
    var notUsed = first && first.toc && ((first.toc.itr && first.toc.itr.notUsed) || (first.toc.sdr && first.toc.sdr.notUsed));
    if (first && first.ok && !notUsed && ((first.sdr && first.sdr.rows.length) || (first.itr && first.itr.rows.length))) return first;
    if (onStep) onStep('Standard reader could not finish (' + ((first && first.msg) || 'ITR and SDR marked Not Used') + '). Trying the Saudi Aramco format.');
    var r = await aramco(copy, fileName, onStep, opts, first && first.toc ? first : null);
    return r || first;
  };
})();
