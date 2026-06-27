"""MissAV Picker 局域网服务器(含图片代理+gzip)"""
import http.server
import socket
import sys
import gzip
import io
import re
import urllib.request
from pathlib import Path

PORT = 8699
ROOT = Path(__file__).parent

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith('/img/'):
            self.proxy_img()
        elif self.path in ('/', '/index.html'):
            self.serve_index()
        elif self.path.startswith('/picker_data.json'):
            data = (ROOT / 'picker_data.json').read_bytes()
            self._send_gzip(data, 'application/json', 'no-cache')
        else:
            super().do_GET()

    def serve_index(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        html = re.sub(r'<script id="DATA".*?</script>', '', html, flags=re.DOTALL)
        self._send_gzip(html.encode(), 'text/html; charset=utf-8', 'no-cache')

    def _send_gzip(self, data, mime, cache='public, max-age=86400'):
        accept = self.headers.get('Accept-Encoding', '')
        if 'gzip' in accept:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as f:
                f.write(data)
            compressed = buf.getvalue()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(compressed)))
            self.send_header('Cache-Control', cache)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(compressed)
        else:
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', cache)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)

    def proxy_img(self):
        raw = self.path[5:]
        url = 'https://' + raw if raw.startswith('fourhoi.com/') else 'https://' + raw
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'image/*,video/*',
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                ct = resp.headers.get('Content-Type', 'image/jpeg')
                self.send_response(200)
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(b'proxy failed')

    def end_headers(self):
        super().end_headers()

    def log_message(self, format, *args):
        msg = format % args
        if 'img/' in msg or '.json' in msg:
            return
        print(f'  {self.address_string()}  {msg}')

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

ip = get_lan_ip()
print(f'\n  封面/头像已走本地代理，无跨域问题')
print(f'  本机:  http://localhost:{PORT}')
print(f'  手机:  http://{ip}:{PORT}')
print(f'  按 Ctrl+C 停止\n')

with http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n  已停止')
        sys.exit(0)
