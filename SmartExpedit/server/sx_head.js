/* SmartExpedit server link, part 1 — loaded before everything else.
   Replaces browser-local storage with authenticated server KV persistence,
   fail-fast auth handling, serialized per-key flush queueing, and keepalive unload flush. */
(function () {
  var S = window.SXS = { cache:{}, ver:{}, base:{}, seq:0, pending:{}, inflight:{}, timers:{}, state:'ok', fails:0, user:'' };
  try { S.user = sessionStorage.getItem('sx_user') || ''; } catch (e) {}
  function authToken() {
    try { return window.sessionStorage ? (sessionStorage.getItem('if_auth_token') || '') : ''; } catch (e) { return ''; }
  }
  function load() {
    var x = new XMLHttpRequest();
    x.open('GET', '/api/kv', false);
    x.withCredentials = true;
    var tok = authToken();
    if (tok) x.setRequestHeader('Authorization', 'Bearer ' + tok);
    x.send(null);
    if (x.status === 401 || x.status === 403) {
      var authErr = Error('AUTH_' + x.status);
      authErr.status = x.status;
      throw authErr;
    }
    if (x.status !== 200) {
      var httpErr = Error('HTTP ' + x.status);
      httpErr.status = x.status;
      throw httpErr;
    }
    return JSON.parse(x.responseText);
  }
  var got = null, lastErr = null;
  for (var i = 0; i < 3 && !got; i++) {
    try {
      got = load();
    } catch (e) {
      lastErr = e;
      if (e && (e.status === 401 || e.status === 403)) break;
      if (i < 2) {
        var t0 = Date.now();
        while (Date.now() - t0 < 500 * (i + 1)) {}
      }
    }
  }
  if (!got) {
    var isAuth = lastErr && (lastErr.status === 401 || lastErr.status === 403);
    document.write(
      '<div style="font:15px system-ui;padding:40px;color:#0f172a">' +
      (isAuth
        ? 'Your SmartExpedit session is not signed in or has expired (' + lastErr.status + '). Please sign in to InspectFlow and reload.'
        : 'SmartExpedit could not reach its server. Check that the server is running, then reload this page.') +
      '</div>'
    );
    throw lastErr || Error('SmartExpedit server not reachable');
  }
  S.seq = got.seq;
  Object.keys(got.items).forEach(function (k) { S.cache[k] = got.items[k].value; S.ver[k] = got.items[k].version; S.base[k] = got.items[k].value; });
  function changedPOs(a, b) {
    try {
      var A = {}, B = {}, out = [];
      (a ? JSON.parse(a) : []).forEach(function (r) { A[r.po] = JSON.stringify(r); });
      (b ? JSON.parse(b) : []).forEach(function (r) { B[r.po] = JSON.stringify(r); });
      Object.keys(B).forEach(function (p) { if (A[p] !== B[p]) out.push(p); });
      Object.keys(A).forEach(function (p) { if (!(p in B)) out.push(p); });
      return out;
    } catch (e) { return []; }
  }
  S.status = function () {
    var el = document.getElementById('sx-sync');
    if (!el) return;
    var n = Object.keys(S.pending).length;
    el.textContent = S.state === 'auth'
      ? 'Session expired — re-login required'
      : S.state === 'error'
      ? 'Save rejected by server'
      : S.state === 'retry'
      ? 'Server not answering — retrying (' + n + ' waiting)'
      : n ? 'Saving…' : 'Saved';
    el.className = 'sx-sync ' + ((S.state === 'retry' || S.state === 'auth' || S.state === 'error') ? 'bad' : n ? 'busy' : 'ok');
  };
  S.flush = function (k) {
    if (!(k in S.pending)) return;
    if (S.inflight[k]) return;
    S.inflight[k] = true;
    var v = S.pending[k], body = { value:v, base:S.ver[k] || 0 };
    if (k === 'ep_exp_records') body.changed = changedPOs(S.base[k], v);
    var x = new XMLHttpRequest();
    x.open('PUT', '/api/kv/' + encodeURIComponent(k));
    x.withCredentials = true;
    x.setRequestHeader('Content-Type', 'application/json');
    var tok = authToken();
    if (tok) x.setRequestHeader('Authorization', 'Bearer ' + tok);
    if (S.user) x.setRequestHeader('X-SX-User', S.user);
    x.onload = function () {
      delete S.inflight[k];
      if (x.status >= 200 && x.status < 300) {
        var r = JSON.parse(x.responseText);
        S.ver[k] = r.version; S.fails = 0; S.state = 'ok';
        if (S.pending[k] === v) { delete S.pending[k]; }
        if (r.value != null) {
          S.cache[k] = r.value; S.base[k] = r.value;
          if (typeof EP_MEM !== 'undefined') delete EP_MEM[k];
          if (window.SXS_onMerged) window.SXS_onMerged(k);
        } else {
          S.base[k] = v;
        }
        if (k in S.pending) { queue(k, S.pending[k]); }
        S.status();
      } else if (x.status === 401 || x.status === 403) {
        S.state = 'auth';
        delete S.pending[k];
        S.status();
      } else if (x.status >= 400 && x.status < 500 && x.status !== 408 && x.status !== 409 && x.status !== 429) {
        S.state = 'error';
        delete S.pending[k];
        S.status();
      } else {
        retry(k);
      }
    };
    x.onerror = function () { delete S.inflight[k]; retry(k); };
    x.send(JSON.stringify(body));
  };
  function retry(k) {
    S.fails++; S.state = 'retry'; S.status();
    clearTimeout(S.timers[k]);
    S.timers[k] = setTimeout(function () { S.flush(k); }, Math.min(60000, 2000 * Math.pow(1.6, Math.min(S.fails, 10))));
  }
  function queue(k, v) { S.pending[k] = v; S.status(); clearTimeout(S.timers[k]); S.timers[k] = setTimeout(function () { S.flush(k); }, 400); }
  var shim = {
    getItem:function (k) { return k in S.cache ? S.cache[k] : null; },
    setItem:function (k, v) { v = String(v); if (S.cache[k] === v) return; S.cache[k] = v; queue(k, v); },
    removeItem:function (k) { if (!(k in S.cache)) return; delete S.cache[k]; queue(k, null); },
    key:function (i) { return Object.keys(S.cache)[i] || null; },
    clear:function () { Object.keys(S.cache).forEach(shim.removeItem); }
  };
  Object.defineProperty(shim, 'length', { get:function () { return Object.keys(S.cache).length; } });
  Object.defineProperty(window, 'localStorage', { value:shim, configurable:true });
  window.addEventListener('beforeunload', function (e) {
    var keys = Object.keys(S.pending);
    if (!keys.length) return;
    keys.forEach(function (k) {
      clearTimeout(S.timers[k]);
      try {
        var v = S.pending[k], body = { value:v, base:S.ver[k] || 0 };
        if (k === 'ep_exp_records') body.changed = changedPOs(S.base[k], v);
        var hdrs = { 'Content-Type': 'application/json' };
        var tok = authToken();
        if (tok) hdrs['Authorization'] = 'Bearer ' + tok;
        if (S.user) hdrs['X-SX-User'] = S.user;
        if (window.fetch) {
          fetch('/api/kv/' + encodeURIComponent(k), {
            method: 'PUT', credentials: 'include', keepalive: true, headers: hdrs, body: JSON.stringify(body)
          }).catch(function () {});
        }
      } catch (err) {}
    });
    e.preventDefault(); e.returnValue = '';
  });
})();
