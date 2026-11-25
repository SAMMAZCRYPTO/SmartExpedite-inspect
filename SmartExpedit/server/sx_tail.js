/* SmartExpedit server link, part 2 — loaded last.
   Uploaded files and MR page images go to the server (with a % line while uploading), other users'
   saves are picked up every 20 seconds, and a "Saved / Saving" line shows in the top bar.          */
(function () {
  var S = window.SXS, cfg = window.SX_SERVER || { demo:false };
  function authHeaders(extra) {
    var h = Object.assign({}, extra || {});
    try {
      var tok = window.sessionStorage ? (sessionStorage.getItem('if_auth_token') || '') : '';
      if (tok) h['Authorization'] = 'Bearer ' + tok;
    } catch (e) {}
    return h;
  }
  /* files: the server replaces the browser's own file store */
  window.fxPut = function (k, v) { return new Promise(function (res) { var isBlob = v instanceof Blob, tries = 0;
    (function go() { var x = new XMLHttpRequest(); x.open('PUT', '/api/blob/' + encodeURIComponent(k)); x.withCredentials = true;
      var tok = ''; try { tok = window.sessionStorage ? (sessionStorage.getItem('if_auth_token') || '') : ''; } catch (e) {}
      if (tok) x.setRequestHeader('Authorization', 'Bearer ' + tok);
      x.setRequestHeader('Content-Type', isBlob ? (v.type || 'application/octet-stream') : 'application/json'); if (isBlob && v.name) x.setRequestHeader('X-SX-Name', encodeURIComponent(v.name));
      var el = document.getElementById('sx-sync'); if (isBlob && x.upload) x.upload.onprogress = function (e) { if (el && e.lengthComputable) { el.textContent = 'Uploading ' + (v.name || 'file') + ' — ' + Math.round(e.loaded / e.total * 100) + '%'; el.className = 'sx-sync busy'; } };
      x.onload = function () {
        if (x.status >= 200 && x.status < 300) { S.status(); res(true); }
        else if (x.status >= 400 && x.status < 500 && x.status !== 408 && x.status !== 429) {
          if (el) { el.textContent = 'Upload rejected (' + x.status + ')'; el.className = 'sx-sync bad'; }
          res(false);
        } else again();
      }; x.onerror = again; x.send(isBlob ? v : JSON.stringify(v));
      function again() { tries++; if (el) { el.textContent = 'Upload failed — retrying (' + tries + ')'; el.className = 'sx-sync bad'; } if (tries > 10) { S.status(); return res(false); } setTimeout(go, Math.min(60000, 2000 * Math.pow(1.5, tries))); } })(); }); };
  window.fxGet = function (k) { return fetch('/api/blob/' + encodeURIComponent(k), { cache:'no-store', credentials:'include', headers: authHeaders() }).then(function (r) { if (!r.ok) return null; return /json/.test(r.headers.get('Content-Type') || '') ? r.json() : r.blob(); }).catch(function () { return null; }); };
  /* MR page images of every order, from the server */
  function loadImages() { var L = []; try { L = JSON.parse(S.cache.ep_exp_records || '[]'); } catch (e) {} return Promise.all(L.filter(function (r) { return r.mrStudy && r.mrStudy.extract && r.mrStudy.extract.images === '__idb' && !FX.imgs[r.po]; }).map(function (r) { return fxGet('img:' + r.po).then(function (im) { if (im) FX.imgs[r.po] = im; }); })); }
  /* the status line in the top bar */
  var st = document.createElement('style'); st.textContent = '.sx-sync{font-size:12px;padding:4px 9px;border-radius:999px;white-space:nowrap}.sx-sync.ok{background:#ecfdf5;color:#047857}.sx-sync.busy{background:#fffbeb;color:#b45309}.sx-sync.bad{background:#fff1f2;color:#be123c}'; document.head.appendChild(st);
  var top = document.querySelector('.sx-top'); if (top) { var s = document.createElement('span'); s.id = 'sx-sync'; s.setAttribute('role', 'status'); top.insertBefore(s, top.querySelector('#sx-alert')); S.status(); }
  /* Reset demo: on a shared server it resets everyone, so ask first, or hide it */
  var rb = document.querySelector('.sx-top [data-s="reset"]'); if (rb) { if (!cfg.demo) rb.remove(); else { rb.title = 'Put the sample data back for every user of this server'; window.addEventListener('click', function (ev) { if (ev.target.closest && ev.target.closest('.sx-top [data-s="reset"]') && !confirm('Reset the demo data on the server? This replaces the data for every user.')) { ev.stopImmediatePropagation(); ev.preventDefault(); } }, true); } }
  /* someone else's save: take it in, and redraw when nobody is typing */
  function busy() { var a = document.activeElement; return (a && /INPUT|TEXTAREA|SELECT/.test(a.tagName)) || !(document.getElementById('modal-bg') || {}).hidden; }
  var redraw = false; function apply(k) { if (typeof EP_MEM !== 'undefined') delete EP_MEM[k]; if (k === FLDKEY) FX.F = null; if (k === 'ep_exp_records') loadImages().then(function () { redraw = true; tryDraw(); }); else { redraw = true; tryDraw(); } }
  function tryDraw() { if (!redraw || busy()) return; redraw = false; try { var y = window.scrollY; render(); window.scrollTo(0, y); } catch (e) {} }
  window.SXS_onMerged = apply;
  setInterval(function () { fetch('/api/kv/changes?since=' + S.seq, { cache:'no-store', credentials:'include', headers: authHeaders() }).then(function (r) { if (r.status === 401 || r.status === 403) { S.state = 'auth'; S.status(); return null; } return r.ok ? r.json() : null; }).then(function (d) { if (!d) return; S.seq = d.seq;
      Object.keys(d.items).forEach(function (k) { if (k in S.pending) return; var it = d.items[k]; if (it.version <= (S.ver[k] || 0)) return; S.ver[k] = it.version; S.cache[k] = it.value; S.base[k] = it.value; apply(k); }); }).catch(function () {}); tryDraw(); }, 20000);
  loadImages().then(function () { try { render(); } catch (e) {} });
})();
