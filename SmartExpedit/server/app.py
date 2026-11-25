"""SmartExpedit server.

Serves the SmartExpedit app and keeps all its data in one SQLite database, so every user
sees the same orders and the other application can read and write them through a JSON API.

Run:   python app.py            (http://localhost:8080)
Env:   SX_PORT      port, default 8080
       SX_HOST      default 0.0.0.0 (reachable from other PCs on the network)
       SX_DATA      folder for the database and uploaded files, default ./data
       SX_API_KEY   if set, the /api/v1 endpoints need the header  X-API-Key: <key>
       SX_DEMO      1 (default) shows the "Reset demo" button; 0 hides it
"""
import os, json, sqlite3, threading, time, uuid, mimetypes
from flask import Flask, request, jsonify, send_file, abort, Response

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('SX_DATA', os.path.join(BASE, 'data'))
BLOBS = os.path.join(DATA, 'blobs')
DB_PATH = os.path.join(DATA, 'smartexpedit.db')
API_KEY = os.environ.get('SX_API_KEY', '')
DEMO = os.environ.get('SX_DEMO', '1') != '0'
REC_KEY = 'ep_exp_records'            # all purchase orders (one JSON list), written by the app
FILES_KEY = 'sx_state_files'          # index of uploaded files
FIELD_KEY = 'sx_state_field'          # field expediting rows and visits
os.makedirs(BLOBS, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024
LOCK = threading.RLock()


# ---------------------------------------------------------------- database
def db():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with LOCK, db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, version INTEGER, seq INTEGER, updated REAL, by TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS blobs (key TEXT PRIMARY KEY, kind TEXT, name TEXT, type TEXT, size INTEGER, path TEXT, seq INTEGER, updated REAL)')
        c.execute('CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v INTEGER)')
        c.execute("INSERT OR IGNORE INTO meta VALUES ('seq', 0)")
        c.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, by TEXT, what TEXT)')


def next_seq(c):
    c.execute("UPDATE meta SET v = v + 1 WHERE k = 'seq'")
    return c.execute("SELECT v FROM meta WHERE k = 'seq'").fetchone()[0]


def kv_get(c, key):
    r = c.execute('SELECT value, version FROM kv WHERE key = ?', (key,)).fetchone()
    return (r['value'], r['version']) if r else (None, 0)


def kv_put(c, key, value, by):
    _, ver = kv_get(c, key)
    seq = next_seq(c)
    c.execute('INSERT INTO kv (key, value, version, seq, updated, by) VALUES (?,?,?,?,?,?) '
              'ON CONFLICT(key) DO UPDATE SET value=excluded.value, version=excluded.version, seq=excluded.seq, updated=excluded.updated, by=excluded.by',
              (key, value, ver + 1, seq, time.time(), by))
    return ver + 1


def who():
    return request.headers.get('X-SX-User') or request.remote_addr or 'unknown'


def records(c):
    v, _ = kv_get(c, REC_KEY)
    try:
        return json.loads(v) if v else []
    except ValueError:
        return []


def save_records(c, L, by, what):
    ver = kv_put(c, REC_KEY, json.dumps(L, separators=(',', ':')), by)
    c.execute('INSERT INTO audit (at, by, what) VALUES (?,?,?)', (time.time(), by, what))
    return ver


# ---------------------------------------------------------------- the app
STATIC = os.path.join(BASE, 'static')


@app.get('/')
def index():
    return send_file(os.path.join(STATIC, 'index.html'), max_age=0)


@app.get('/sx-config.js')
def config_js():
    return Response('window.SX_SERVER={demo:%s};' % ('true' if DEMO else 'false'), mimetype='application/javascript')


# ---- storage used by the page (every localStorage key lives here)
@app.get('/api/kv')
def kv_all():
    with LOCK, db() as c:
        rows = c.execute('SELECT key, value, version, seq FROM kv').fetchall()
        seq = c.execute("SELECT v FROM meta WHERE k='seq'").fetchone()[0]
    return jsonify({'seq': seq, 'items': {r['key']: {'value': r['value'], 'version': r['version']} for r in rows}})


@app.get('/api/kv/changes')
def kv_changes():
    since = int(request.args.get('since', 0))
    with LOCK, db() as c:
        rows = c.execute('SELECT key, value, version, seq FROM kv WHERE seq > ?', (since,)).fetchall()
        seq = c.execute("SELECT v FROM meta WHERE k='seq'").fetchone()[0]
    return jsonify({'seq': seq, 'items': {r['key']: {'value': r['value'], 'version': r['version']} for r in rows}})


@app.put('/api/kv/<path:key>')
def kv_set(key):
    body = request.get_json(force=True)
    value, base = body.get('value'), int(body.get('base') or 0)
    with LOCK, db() as c:
        cur, ver = kv_get(c, key)
        merged = None
        if value is None:
            c.execute('DELETE FROM kv WHERE key = ?', (key,))
            next_seq(c)
            return jsonify({'version': 0})
        if base and ver and base != ver and key == REC_KEY:
            # someone else saved the orders since this page loaded: keep their work,
            # apply only the orders this page changed (the page sends which ones)
            changed = body.get('changed') or []
            mine = {r.get('po'): r for r in json.loads(value)}
            L = json.loads(cur) if cur else []
            pos = [r.get('po') for r in L]
            for po in changed:
                if po in mine:
                    if po in pos:
                        L[pos.index(po)] = mine[po]
                    else:
                        L.append(mine[po])
                elif po in pos:
                    L.pop(pos.index(po)); pos.pop(pos.index(po))
            value = merged = json.dumps(L, separators=(',', ':'))
        newver = kv_put(c, key, value, who())
    out = {'version': newver}
    if merged is not None:
        out['value'] = merged
    return jsonify(out)


# ---- files and page images used by the page
@app.put('/api/blob/<path:key>')
def blob_put(key):
    kind = 'json' if request.mimetype == 'application/json' else 'file'
    fid = uuid.uuid4().hex
    path = os.path.join(BLOBS, fid)
    with open(path, 'wb') as f:
        f.write(request.get_data())
    name = request.headers.get('X-SX-Name', '')
    with LOCK, db() as c:
        old = c.execute('SELECT path FROM blobs WHERE key = ?', (key,)).fetchone()
        seq = next_seq(c)
        c.execute('INSERT OR REPLACE INTO blobs VALUES (?,?,?,?,?,?,?,?)', (key, kind, name, request.mimetype, os.path.getsize(path), fid, seq, time.time()))
    if old and old['path'] != fid:
        try:
            os.remove(os.path.join(BLOBS, old['path']))
        except OSError:
            pass
    return jsonify({'ok': True})


@app.get('/api/blob/<path:key>')
def blob_get(key):
    with LOCK, db() as c:
        r = c.execute('SELECT * FROM blobs WHERE key = ?', (key,)).fetchone()
    if not r:
        abort(404)
    return send_file(os.path.join(BLOBS, r['path']), mimetype=r['type'] or 'application/octet-stream', download_name=r['name'] or key.replace(':', '_'), max_age=0)


# ---------------------------------------------------------------- API for other applications (/api/v1)
def need_key():
    if API_KEY and request.headers.get('X-API-Key') != API_KEY:
        abort(401)


def summary(r):
    q = r.get('items') or []
    return {'po': r.get('po'), 'rev': r.get('rev'), 'supplier': r.get('supplier'), 'title': r.get('head'), 'currency': r.get('ccy'),
            'value': r.get('value'), 'stage': r.get('stage'), 'assigned_to': r.get('assignedTo'), 'issued_on': r.get('issuedOn'),
            'lots': [{'lot': l.get('id'), 'contractual_delivery': l.get('date'), 'qty': l.get('qty')} for l in (r.get('lots') or [])],
            'lines': len(q), 'client': r.get('client')}


def find(c, po):
    for r in records(c):
        if r.get('po') == po:
            return r
    abort(404, 'PO not found')


@app.get('/api/v1/health')
def health():
    with LOCK, db() as c:
        n = len(records(c))
    return jsonify({'ok': True, 'pos': n, 'time': time.strftime('%Y-%m-%dT%H:%M:%S')})


@app.get('/api/v1/pos')
def api_pos():
    need_key()
    with LOCK, db() as c:
        return jsonify([summary(r) for r in records(c)])


@app.get('/api/v1/pos/<po>')
def api_po(po):
    need_key()
    with LOCK, db() as c:
        r = find(c, po)
    part = request.args.get('part')   # documents | schedule | plan | items | irns | shipments | inspection
    if not part:
        return jsonify(r)
    parts = {'documents': (r.get('reg') or {}).get('rows', []), 'schedule': (r.get('sch') or {}).get('rows', []),
             'plan': (r.get('plan') or {}).get('rows', []), 'items': r.get('items', []), 'irns': r.get('irns', []),
             'shipments': {'shipments': r.get('ships', []), 'packing_lists': r.get('pls', []), 'bills_of_lading': r.get('bls', [])},
             'inspection': {'reports': r.get('irs', []), 'punch_list': r.get('punch', [])}, 'reviews': r.get('rvw', {}),
             'submissions': r.get('subs', []), 'mssr': r.get('mssrX', {})}
    if part not in parts:
        abort(400, 'part must be one of: ' + ', '.join(parts))
    return jsonify(parts[part])


@app.patch('/api/v1/pos/<po>')
def api_po_patch(po):
    """Merge fields into one PO (for example from IMS or the Logistics app). Lists given here replace the PO's list."""
    need_key()
    body = request.get_json(force=True)
    if not isinstance(body, dict):
        abort(400, 'send a JSON object')
    with LOCK, db() as c:
        L = records(c)
        r = next((x for x in L if x.get('po') == po), None)
        if not r:
            abort(404, 'PO not found')
        r.update(body)
        ver = save_records(c, L, who(), 'PATCH %s %s' % (po, ','.join(body)))
    return jsonify({'ok': True, 'version': ver})


@app.post('/api/v1/pos/<po>/<lst>')
def api_po_append(po, lst):
    """Add one entry to a PO list: irns, ships, pls, bls, irs (inspection reports) or punch."""
    need_key()
    if lst not in ('irns', 'ships', 'pls', 'bls', 'irs', 'punch'):
        abort(400, 'list must be irns, ships, pls, bls, irs or punch')
    e = request.get_json(force=True)
    if not isinstance(e, dict):
        abort(400, 'send a JSON object')
    e.setdefault('id', uuid.uuid4().hex[:10])
    if lst == 'ships':
        e.setdefault('modeLog', [])
    with LOCK, db() as c:
        L = records(c)
        r = next((x for x in L if x.get('po') == po), None)
        if not r:
            abort(404, 'PO not found')
        r.setdefault(lst, []).append(e)
        (r.setdefault('log', [])).append({'on': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()), 'by': 'API ' + who(), 'txt': 'Added to %s through the API.' % lst})
        ver = save_records(c, L, who(), 'POST %s %s' % (po, lst))
    return jsonify({'ok': True, 'id': e['id'], 'version': ver}), 201


@app.get('/api/v1/field')
def api_field():
    need_key()
    with LOCK, db() as c:
        v, _ = kv_get(c, FIELD_KEY)
    return jsonify(json.loads(v) if v else {'rows': []})


@app.get('/api/v1/files')
def api_files():
    need_key()
    po = request.args.get('po')
    with LOCK, db() as c:
        v, _ = kv_get(c, FILES_KEY)
    L = json.loads(v) if v else []
    return jsonify([f for f in L if not po or f.get('po') == po])


@app.get('/api/v1/files/<fid>')
def api_file(fid):
    need_key()
    return blob_get('file:' + fid)


@app.get('/api/v1/audit')
def api_audit():
    need_key()
    with LOCK, db() as c:
        rows = c.execute('SELECT at, by, what FROM audit ORDER BY id DESC LIMIT 200').fetchall()
    return jsonify([{'at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['at'])), 'by': r['by'], 'what': r['what']} for r in rows])


@app.errorhandler(404)
@app.errorhandler(400)
@app.errorhandler(401)
def err(e):
    return jsonify({'error': getattr(e, 'description', str(e))}), e.code


init_db()

if __name__ == '__main__':
    host, port = os.environ.get('SX_HOST', '0.0.0.0'), int(os.environ.get('SX_PORT', '8080'))
    print('SmartExpedit is running: http://localhost:%d  (data in %s)' % (port, DATA))
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8, max_request_body_size=app.config['MAX_CONTENT_LENGTH'])
    except ImportError:
        app.run(host=host, port=port, threaded=True)
