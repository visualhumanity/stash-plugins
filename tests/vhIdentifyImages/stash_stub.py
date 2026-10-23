"""Local stand-in for Stash's GraphQL endpoint, plus a runner for the plugin entry point.

The stub keeps canned images, plugin settings and scrape results, answers the
queries the plugin sends, and records every request so tests can check which
calls went out and with what input.
"""

import copy
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


def _strip_arguments(text):
    previous = None
    while previous != text:
        previous, text = text, re.sub(r"\([^()]*\)", "", text)
    return text


class UnsupportedQuery(ValueError):
    pass


def _parse_selection(tokens, i):
    """Parse a selection set starting just after "{"; return (selection, index after "}")."""
    selection = {}
    while tokens[i] != "}":
        if tokens[i] == "...":
            if tokens[i + 1] != "on":
                raise UnsupportedQuery(f"named fragment spread ...{tokens[i + 1]} is not supported")
            # inline fragment: ... on Type { fields }
            sub, i = _parse_selection(tokens, i + 4)
            for name, value in sub.items():
                selection.setdefault(name, value)
            continue
        name = tokens[i]
        i += 1
        if tokens[i] == "{":
            selection[name], i = _parse_selection(tokens, i + 1)
        else:
            selection[name] = None
    return selection, i + 1


def selection_set(query):
    """The fields a GraphQL query selects, as nested dicts (None for a leaf).

    Supports fields, arguments, nesting and inline fragments. Raises
    UnsupportedQuery for anything else (aliases, directives, named
    fragments, string literals) rather than guessing.
    """
    if '"' in query:
        raise UnsupportedQuery("string literals are not supported")
    if "@" in query:
        raise UnsupportedQuery("directives are not supported")
    if re.search(r"\bfragment\b", query):
        raise UnsupportedQuery("fragment definitions are not supported")
    text = _strip_arguments(query)
    body = text[text.index("{") :]
    if ":" in body:
        raise UnsupportedQuery("aliases are not supported")
    tokens = re.findall(r"\.\.\.|\w+|[{}]", body)
    selection, _ = _parse_selection(tokens, 1)
    return selection


def project(value, selection):
    """Keep only the selected fields, as a GraphQL server does. Missing fields come back null."""
    if selection is None or value is None:
        return value
    if isinstance(value, list):
        return [project(v, selection) for v in value]
    return {name: project(value.get(name), sub) for name, sub in selection.items()}


def image_scraper(scraper_id, supported=("FRAGMENT",)):
    return {"id": scraper_id, "name": scraper_id, "image": {"supported_scrapes": list(supported)}}


DEFAULT_SCRAPERS = (image_scraper("GalleryDlReddit"), image_scraper("ExampleScraper"))


_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _fold(text):
    return (text or "").translate(_ASCII_LOWER)


def _like(value, pattern):
    """SQLite LIKE, which Stash uses for EQUALS: % and _ are wildcards, ASCII case is ignored."""
    regex = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in _fold(pattern))
    return re.fullmatch(regex, _fold(value), re.DOTALL) is not None


# mutation -> (entity kind, find query field, result list key)
ENTITY_MUTATIONS = {
    "performerCreate": ("performers", "findPerformers", "performers"),
    "tagCreate": ("tags", "findTags", "tags"),
    "studioCreate": ("studios", "findStudios", "studios"),
}
SINGULAR = {"performers": "performer", "tags": "tag", "studios": "studio"}


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
        "studio": None,
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
        entities=None,
        before=None,
    ):
        # copies, because updates are applied to the stored images
        self.images = {img["id"]: copy.deepcopy(img) for img in images}
        # operation name -> function(stub) run once just before that operation is answered,
        # to simulate an edit made by someone else while the plugin works
        self.before = dict(before or {})
        # effective result of every image update: {"id", <input key>: resulting value}
        self.applied = []
        self.settings = settings
        # image id -> list of ScrapedImage dicts (missing means an empty list)
        self.scrapes = scrapes or {}
        self.scrape_errors = set(scrape_errors)
        self.update_errors = set(update_errors)
        # names whose performerCreate / tagCreate / studioCreate is rejected
        self.create_errors = set(create_errors)
        self.next_id = 100
        # performers, tags and studios that exist in Stash: kind -> list of {"id", "name", ...}.
        # Creating a name that exists fails as in Stash; the plugin's scrapes never
        # match these, which is how a create racing a parallel scan looks.
        self.entities = {kind: list((entities or {}).get(kind, [])) for kind in ("performers", "tags", "studios")}
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
        response = self.answer(body["query"], body.get("variables") or {})
        if "data" in response:
            response = {"data": project(response["data"], selection_set(body["query"]))}
        return response

    def answer(self, query, variables):
        operation = query.split("(")[0].split("{")[0].split()[-1]
        if operation in self.before:
            self.before.pop(operation)(self)
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
            results = self.scrapes.get(image_id, [])
            for result in results:
                parent = (result.get("studio") or {}).get("parent") or {}
                # Stash matches a scraped image's studio, never its parent
                assert parent.get("stored_id") is None, "Stash never sends a stored_id on a scraped parent studio"
            return {"data": {"scrapeSingleImage": results}}
        if "studioUpdate" in query:
            return {"data": {"studioUpdate": {"id": variables["input"]["id"]}}}
        for mutation, (kind, finder, key) in ENTITY_MUTATIONS.items():
            if mutation in query:
                return self.create_entity(mutation, kind, variables["input"])
            if finder in query:
                return {"data": {finder: {key: self.find_entities(kind, variables)}}}
        if "bulkImageUpdate" in query:
            return self.bulk_image_update(variables["input"])
        return {"errors": [{"message": "stub does not know this query"}]}

    def bulk_image_update(self, update):
        """Apply a BulkImageUpdateInput as Stash does: SET replaces a list, ADD appends missing values."""
        assert len(update["ids"]) == 1, "the plugin sends one image per update"
        image_id = update["ids"][0]
        if image_id in self.update_errors:
            return {"errors": [{"message": "update rejected"}]}
        img = self.images[image_id]
        applied = {"id": image_id}
        for key, value in update.items():
            if key == "ids":
                continue
            if key in ("urls", "performer_ids", "tag_ids"):
                assert value["mode"] in ("SET", "ADD"), value
                values = value["values"] if key == "urls" else value["ids"]
                if key == "urls":
                    current = img["urls"]
                else:
                    current = [e["id"] for e in img[key.replace("_ids", "s")]]
                result = list(values) if value["mode"] == "SET" else current + [v for v in values if v not in current]
                if key == "urls":
                    img["urls"] = result
                else:
                    img[key.replace("_ids", "s")] = [{"id": i, "name": self.entity_name(key, i)} for i in result]
                applied[key] = result
            elif key == "studio_id":
                img["studio"] = {"id": value, "name": None} if value else None
                applied[key] = value
            else:
                img[key] = value
                applied[key] = value
        self.applied.append(applied)
        return {"data": {"bulkImageUpdate": [{"id": image_id}]}}

    def entity_name(self, key, entity_id):
        kind = "performers" if key == "performer_ids" else "tags"
        return next((e["name"] for e in self.entities[kind] if e["id"] == entity_id), None)

    def create_entity(self, mutation, kind, create_input):
        name = create_input["name"]
        if name in self.create_errors:
            return {"errors": [{"message": f"{mutation} rejected"}]}
        disambiguation = create_input.get("disambiguation") or ""
        if kind != "performers":
            for entity in self.entities[kind]:
                if any(_fold(alias) == _fold(name) for alias in entity.get("aliases") or []):
                    return {"errors": [{"message": f"name '{name}' is used as alias for '{entity['name']}'"}]}
        for entity in self.entities[kind]:
            same_disambiguation = kind != "performers" or _fold(entity.get("disambiguation")) == _fold(disambiguation)
            if _fold(entity["name"]) == _fold(name) and same_disambiguation:
                return {"errors": [{"message": f"{SINGULAR[kind]} with name '{name}' already exists"}]}
        self.next_id += 1
        self.entities[kind].append({"id": str(self.next_id), "name": name, "disambiguation": disambiguation or None})
        return {"data": {mutation: {"id": str(self.next_id)}}}

    def find_entities(self, kind, variables):
        filters = next((v for k, v in variables.items() if k.endswith("_filter")), None) or {}
        matches = self.entities[kind]
        for field, criterion in filters.items():
            assert criterion["modifier"] == "EQUALS", criterion
            if field == "aliases":
                matches = [e for e in matches if any(_like(a, criterion["value"]) for a in e.get("aliases") or [])]
            else:
                matches = [e for e in matches if _like(e.get(field), criterion["value"])]
        return matches

    def find_images(self, variables):
        image_filter = variables.get("image_filter") or {}
        find_filter = variables.get("filter") or {}
        matches = sorted(self.images.values(), key=lambda img: _path(img) or "")
        if variables.get("ids"):
            # as in Stash: with ids, image_filter and filter are ignored
            ids = {str(i) for i in variables["ids"]}
            return {"count": len(ids), "images": [img for img in matches if img["id"] in ids]}
        if "id" in image_filter:
            assert image_filter["id"]["modifier"] == "EQUALS", image_filter
            matches = [img for img in matches if img["id"] == str(image_filter["id"]["value"])]
        path = image_filter.get("path")
        if path:
            assert path["modifier"] == "MATCHES_REGEX", path
            pattern = re.compile(path["value"])
            # an image with no file never matches a path filter
            matches = [img for img in matches if _path(img) is not None and pattern.search(_path(img))]
        if "organized" in image_filter:
            matches = [img for img in matches if img["organized"] == image_filter["organized"]]
        page, per_page = find_filter.get("page", 1), find_filter.get("per_page", 25)
        start = (page - 1) * per_page
        window = matches[start : start + per_page]
        return {"count": len(matches), "images": window}

    # Request views for assertions

    def calls(self, name):
        return [r["body"] for r in self.requests if name in r["body"]["query"]]

    def scraped_ids(self):
        return [b["variables"]["input"]["image_id"] for b in self.calls("scrapeSingleImage")]

    def scrape_sources(self):
        return [b["variables"]["source"] for b in self.calls("scrapeSingleImage")]

    def mutations(self):
        return [b for b in (r["body"] for r in self.requests) if b["query"].lstrip().startswith("mutation")]

    def operations(self):
        """Operation names of every request, in order."""
        return [r["body"]["query"].split("(")[0].split("{")[0].split()[-1] for r in self.requests]

    def creates(self, mutation):
        return [b["variables"]["input"] for b in self.calls(mutation)]

    def updates(self):
        """The effective result of each image update (resulting lists for ADD and SET)."""
        return list(self.applied)

    def update_inputs(self):
        return [b["variables"]["input"] for b in self.calls("bulkImageUpdate")]


def hook_args(image_id, hook_type="Image.Create.Post"):
    """Args as Stash sends them for a post hook fired by a scan (input is null)."""
    return {"hookContext": {"id": int(image_id), "type": hook_type, "input": None}}


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
