"""เปิดเว็บ StockLens บนเครื่องนี้

    python serve.py            -> http://localhost:8000 (เปิดได้เฉพาะเครื่องนี้)
    python serve.py 8080       -> เปลี่ยนพอร์ต
    python serve.py --lan      -> ให้มือถือ/เครื่องอื่นในวง Wi-Fi เดียวกันเปิดได้ด้วย

ต่างจาก `python -m http.server` ตรงที่สั่งให้เบราว์เซอร์ตรวจไฟล์ใหม่ทุกครั้ง
จึงเห็นข้อมูล/หน้าเว็บเวอร์ชันล่าสุดเสมอหลังอัปเดต
"""
import functools
import http.server
import socket
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(args[0]) if args else 8000
    lan = "--lan" in sys.argv
    host = "0.0.0.0" if lan else "127.0.0.1"
    handler = functools.partial(Handler, directory=str(WEB))
    with http.server.ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"StockLens: http://localhost:{port}")
        if lan:
            ip = socket.gethostbyname(socket.gethostname())
            print(f"เปิดจากมือถือในวง Wi-Fi เดียวกัน: http://{ip}:{port}")
        print("กด Ctrl+C เพื่อปิด")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
