"""CIM26 — inicia a aplicação (interface web local + motor científico).

    python app.py                 # abre http://127.0.0.1:8765 no navegador
    python app.py --port 9000 --no-browser
"""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cim26.paths import ensure_dirs  # noqa: E402
from web.server import make_server  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="CIM26 — exatidão × custo computacional FV")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    ensure_dirs()
    srv = make_server(a.host, a.port)
    url = f"http://{a.host}:{a.port}/"
    print(f"CIM26 em {url}  (Ctrl+C para encerrar)", flush=True)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
