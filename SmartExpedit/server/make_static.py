"""Builds static/index.html for the server from ../index.html (the one-file app).
Run it again whenever index.html is rebuilt:  python make_static.py"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, '..', 'index.html'), encoding='utf8').read()
head = open(os.path.join(HERE, 'sx_head.js'), encoding='utf8').read()
tail = open(os.path.join(HERE, 'sx_tail.js'), encoding='utf8').read()
i = src.index('<script')
out = src[:i] + '<script src="/sx-config.js"></script>\n<script>' + head + '</script>\n' + src[i:] + '\n<script>' + tail + '</script>\n'
os.makedirs(os.path.join(HERE, 'static'), exist_ok=True)
open(os.path.join(HERE, 'static', 'index.html'), 'w', encoding='utf8').write(out)
print('static/index.html written', round(len(out) / 1e6, 2), 'MB')
