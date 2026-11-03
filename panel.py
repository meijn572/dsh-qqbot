"""小面板 HTTP 生命周期。"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from panel_routes import handle_get, handle_post
from settings import PANEL_PORT


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        ctype = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
            ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
            ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store" if path.suffix.lower() in {".js", ".css", ".html"} else "max-age=60")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._html(INDEX)
        elif path.startswith("/static/"):
            self._file(WEB_DIR / path.rsplit("/", 1)[-1])
        else:
            handle_get(self, path, parsed)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        handle_post(self, parsed.path, parsed)

    def log_message(self, *args) -> None:  # noqa: D401
        return


WEB_DIR = Path(__file__).parent / "web"
INDEX = (WEB_DIR / "index.html").read_text(encoding="utf-8")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PANEL_PORT), Handler)
    print(f"panel on http://127.0.0.1:{PANEL_PORT}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
