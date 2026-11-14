# Rebuilds the demo data, then serves the demo page on localhost.
# A double-clicked file:// page can't fetch() local files, which is why there's a server.
#
# python -m demo.serve
# python -m demo.serve --port 8001 --no-build

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import plotly

from demo import build

# The page's folder, and the Plotly.js file that ships inside the pip package, so it works offline
PAGE = Path(__file__).resolve().parent
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


# Serves the page folder, plus /plotly.min.js from the plotly package.
class DemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/plotly.min.js":
            self.send_file(PLOTLY_JS, "text/javascript")
        else:
            super().do_GET()

    # The Reload button posts here: rebuild the data from the latest pipeline outputs
    def do_POST(self) -> None:
        if self.path != "/rebuild":
            self.send_error(404)
            return
        try:
            build.main()
            self.send_response(204)
        except Exception as error:
            print(f"rebuild failed: {error}")
            self.send_response(500)
        self.end_headers()

    # Send one file as is.
    def send_file(self, path: Path, content_type: str) -> None:
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # Never cache, so Reload always gets the newest data
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # Keep the terminal quiet
    def log_message(self, format: str, *args) -> None:
        pass


def main() -> None:
    # Get the options from the command line
    parser = argparse.ArgumentParser(description="Serve the Straight Rows demo page")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-build", action="store_true", help="skip rebuilding the data"
    )
    options = parser.parse_args()

    # Rebuild the data from the latest pipeline outputs
    if not options.no_build:
        build.main()

    # Serve the page folder
    handler = functools.partial(DemoHandler, directory=str(PAGE))
    server = ThreadingHTTPServer(("127.0.0.1", options.port), handler)
    print(f"demo at http://localhost:{options.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
