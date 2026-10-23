"""Local stand-in for Stash's GraphQL endpoint, plus a runner for the plugin entry point.

The stub keeps canned images, plugin settings and scrape results, answers the
queries the plugin sends, and records every request so tests can check which
calls went out and with what input.
"""

import json
import os
import re
import socketserver
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PLUGIN_ID = "vhIdentifyImages"
PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", PLUGIN_ID)
PLUGIN_SCRIPT = os.path.join(PLUGIN_DIR, PLUGIN_ID + ".py")

LOG_LINE = re.compile(r"^\x01(\w)\x02(.*)$")


class _Server(HTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind does a reverse DNS lookup that can take a while; skip it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def image_scraper(scraper_id, supported=("FRAGMENT",)):
    return {"id": scraper_id, "name": scraper_id, "image": {"supported_scrapes": list(supported)}}


DEFAULT_SCRAPERS = (image_scraper("GalleryDlReddit"), image_scraper("ExampleScraper"))


def _path(img):
    files = img.get("visual_files") or []
    return files[0]["path"] if files else None


def image(image_id, path, **fields):
    record = {
        "id": str(image_id),
        "title": None,
        "code": None,
        "details": None,
        "date": None,
        "organized": False,
        "urls": [],
        "performers": [],
        "tags": [],
        "visual_files": [{"path": path}] if path is not None else [],
    }
    record.update(fields)
    return record


class FakeStash:
    def __init__(
        self,
        images=(),
        settings=None,
        scrapes=None,
        scrape_errors=(),
        update_errors=(),
        create_errors=(),
        scrapers=DEFAULT_SCRAPERS,
    ):
        self.images = {img["id"]: img for img in images}
        self.settings = settings
        # image id -> list of ScrapedImage dicts (missing means an empty list)
        self.scrapes = scrapes or {}
        self.scrape_errors = set(scrape_errors)
        self.update_errors = set(update_errors)
        # names whose performerCreate / tagCreate / studioCreate is rejected
        self.create_errors = set(create_errors)
        self.next_id = 100
        # what listScrapers(types: [IMAGE]) returns
        self.scrapers = list(scrapers)
        self.requests = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                stub.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                payload = json.dumps(stub.respond(body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = _Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, args=(0.01,), daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def connection(self, **overrides):
        conn = {"Scheme": "http", "Host": "127.0.0.1", "Port": self.port}
        conn.update(overrides)
        return conn

    # GraphQL handling

    def respond(self, body):
        query, variables = body["query"], body.get("variables") or {}
        if "configuration" in query:
            plugins = {} if self.settings is None else {PLUGIN_ID: self.settings}
            return {"data": {"configuration": {"plugins": plugins}}}
        if "listScrapers" in query:
            assert variables.get("types") == ["IMAGE"], variables
            return {"data": {"listScrapers": self.scrapers}}
        if "findImages" in query:
            return {"data": {"findImages": self.find_images(variables)}}
        if "findImage" in query:
            return {"data": {"findImage": self.images.get(str(variables["id"]))}}
        if "scrapeSingleImage" in query:
            image_id = str(variables["input"]["image_id"])
            if image_id in self.scrape_errors:
                return {"errors": [{"message": "scraper failed for this image"}]}
            return {"data": {"scrapeSingleImage": self.scrapes.get(image_id, [])}}
        if "studioUpdate" in query:
            return {"data": {"studioUpdate": {"id": variables["input"]["id"]}}}
        for mutation in ("performerCreate", "tagCreate", "studioCreate"):
            if mutation in query:
                name = variables["input"]["name"]
                if name in self.create_errors:
                    return {"errors": [{"message": f"{mutation} rejected"}]}
                self.next_id += 1
                return {"data": {mutation: {"id": str(self.next_id)}}}
        if "imageUpdate" in query:
            update = variables["input"]
            if update["id"] in self.update_errors:
                return {"errors": [{"message": "update rejected"}]}
            return {"data": {"imageUpdate": {"id": update["id"]}}}
        return {"errors": [{"message": "stub does not know this query"}]}

    def find_images(self, variables):
        image_filter = variables.get("image_filter") or {}
        find_filter = variables.get("filter") or {}
        matches = sorted(self.images.values(), key=lambda img: _path(img) or "")
        path = image_filter.get("path")
        if path:
            assert path["modifier"] == "MATCHES_REGEX", path
            pattern = re.compile(path["value"])
            # an image with no file never matches a path filter
            matches = [img for img in matches if _path(img) is not None and pattern.search(_path(img))]
        page, per_page = find_filter.get("page", 1), find_filter.get("per_page", 25)
        start = (page - 1) * per_page
        window = matches[start : start + per_page]
        return {
            "count": len(matches),
            "images": [{"id": img["id"], "visual_files": img["visual_files"]} for img in window],
        }

    # Request views for assertions

    def calls(self, name):
        return [r["body"] for r in self.requests if name in r["body"]["query"]]

    def scraped_ids(self):
        return [b["variables"]["input"]["image_id"] for b in self.calls("scrapeSingleImage")]

    def scrape_sources(self):
        return [b["variables"]["source"] for b in self.calls("scrapeSingleImage")]

    def mutations(self):
        return [b for b in (r["body"] for r in self.requests) if b["query"].lstrip().startswith("mutation")]

    def creates(self, mutation):
        return [b["variables"]["input"] for b in self.calls(mutation)]

    def updates(self):
        return [b["variables"]["input"] for b in self.calls("imageUpdate")]


def run_plugin(stub, args=None, connection=None):
    """Run the plugin script as Stash does: stdin JSON in, log lines on stderr out.

    Returns the parsed log as a list of (level, message) tuples.
    """
    payload = {
        "server_connection": connection or stub.connection(),
        "args": {"mode": "identify"} if args is None else args,
    }
    result = subprocess.run(
        [sys.executable, PLUGIN_SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(f"plugin exited {result.returncode}: {result.stderr}")
    log = []
    for line in result.stderr.splitlines():
        match = LOG_LINE.match(line)
        if match:
            log.append((match.group(1), match.group(2)))
        else:
            log.append(("raw", line))
    return log
