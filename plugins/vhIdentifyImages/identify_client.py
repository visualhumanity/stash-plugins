"""Minimal Stash GraphQL client over the stdlib, using the connection Stash passes on stdin."""

import json
import urllib.request

PAGE_SIZE = 500
REGEX_SPECIAL = set("\\.+*?()|[]{}^$")

CONFIGURATION = """
query PluginConfiguration($include: [ID!]) {
  configuration { plugins(include: $include) }
}"""

LIST_IMAGE_SCRAPERS = """
query ListImageScrapers($types: [ScrapeContentType!]!) {
  listScrapers(types: $types) { id image { supported_scrapes } }
}"""

FIND_IMAGE_IDS = """
query FindImageIds($image_filter: ImageFilterType, $filter: FindFilterType) {
  findImages(image_filter: $image_filter, filter: $filter) {
    images { id visual_files { ... on ImageFile { path } ... on VideoFile { path } } }
  }
}"""

FIND_IMAGE = """
query FindImage($id: ID!) {
  findImage(id: $id) {
    id title code details date organized urls
    performers { id name }
    tags { id name }
    studio { id name }
    visual_files { ... on ImageFile { path } ... on VideoFile { path } }
  }
}"""

SCRAPE_IMAGE = """
query ScrapeSingleImage($source: ScraperSourceInput!, $input: ScrapeSingleImageInput!) {
  scrapeSingleImage(source: $source, input: $input) {
    title code details photographer urls date
    performers { stored_id name disambiguation urls }
    tags { stored_id name }
    studio {
      stored_id name url urls details aliases
      parent { stored_id name url urls details aliases parent { stored_id name } }
    }
  }
}"""

PERFORMER_CREATE = """
mutation PerformerCreate($input: PerformerCreateInput!) {
  performerCreate(input: $input) { id }
}"""

TAG_CREATE = """
mutation TagCreate($input: TagCreateInput!) {
  tagCreate(input: $input) { id }
}"""

STUDIO_CREATE = """
mutation StudioCreate($input: StudioCreateInput!) {
  studioCreate(input: $input) { id }
}"""

STUDIO_UPDATE = """
mutation StudioUpdate($input: StudioUpdateInput!) {
  studioUpdate(input: $input) { id }
}"""

# field -> (query, root field, filter argument, result list key)
FIND_BY_NAME = {
    "performers": (
        """
query FindPerformersByName($performer_filter: PerformerFilterType, $filter: FindFilterType) {
  findPerformers(performer_filter: $performer_filter, filter: $filter) { performers { id name disambiguation } }
}""",
        "findPerformers",
        "performer_filter",
        "performers",
    ),
    "tags": (
        """
query FindTagsByName($tag_filter: TagFilterType, $filter: FindFilterType) {
  findTags(tag_filter: $tag_filter, filter: $filter) { tags { id name } }
}""",
        "findTags",
        "tag_filter",
        "tags",
    ),
    "studio": (
        """
query FindStudiosByName($studio_filter: StudioFilterType, $filter: FindFilterType) {
  findStudios(studio_filter: $studio_filter, filter: $filter) { studios { id name } }
}""",
        "findStudios",
        "studio_filter",
        "studios",
    ),
}

# bulkImageUpdate, one image at a time, because only it can ADD to lists
# (imageUpdate always replaces them). It fires Image.Update.Post like imageUpdate.
IMAGE_UPDATE = """
mutation ImageUpdate($input: BulkImageUpdateInput!) {
  bulkImageUpdate(input: $input) { id }
}"""


def prefix_regex(prefixes):
    """Regex matching paths that start with any of the prefixes, taken literally.

    Escapes only regex metacharacters, so the result is valid for both Go
    (Stash's filter) and Python.
    """
    escaped = ["".join("\\" + c if c in REGEX_SPECIAL else c for c in p) for p in prefixes]
    return "^(?:" + "|".join(escaped) + ")"


def image_path(image):
    files = image.get("visual_files") or []
    return files[0].get("path") if files else None


class StashClient:
    def __init__(self, connection):
        host = connection.get("Host") or "localhost"
        if host in ("0.0.0.0", "::"):
            host = "localhost"
        scheme = connection.get("Scheme") or "http"
        self.url = f"{scheme}://{host}:{connection.get('Port') or 9999}/graphql"
        cookie = connection.get("SessionCookie") or {}
        self.cookie = f"{cookie['Name']}={cookie['Value']}" if cookie.get("Name") else None

    def call(self, query, variables=None):
        body = json.dumps({"query": query, "variables": variables or {}})
        request = urllib.request.Request(
            self.url, data=body.encode(), headers={"Content-Type": "application/json"}
        )
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.load(response)
        if payload.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "unknown error") for e in payload["errors"]))
        return payload["data"]

    def plugin_settings(self, plugin_id):
        data = self.call(CONFIGURATION, {"include": [plugin_id]})
        return (data["configuration"]["plugins"] or {}).get(plugin_id)

    def image_scrapers(self):
        """Map each installed image scraper's ID to its supported scrape types (NAME, FRAGMENT, URL)."""
        scrapers = self.call(LIST_IMAGE_SCRAPERS, {"types": ["IMAGE"]})["listScrapers"] or []
        return {s["id"]: (s.get("image") or {}).get("supported_scrapes") or [] for s in scrapers}

    def find_images(self, prefixes, limit, skip_organized=False, image_id=None):
        """List (id, path) for images under the prefixes, sorted by path, up to limit (0 = all).

        With skip_organized, organized images are filtered out by Stash, so the
        limit counts only images that will be processed. image_id limits the
        search to that one image through the same filter, so the scan hook
        checks it exactly as a run would. (findImages' ids argument cannot be
        used: Stash ignores every filter when it is given.)
        """
        image_filter = {}
        if image_id is not None:
            image_filter["id"] = {"value": int(image_id), "modifier": "EQUALS"}
        if skip_organized:
            image_filter["organized"] = False
        if prefixes:
            image_filter["path"] = {"value": prefix_regex(prefixes), "modifier": "MATCHES_REGEX"}
        found, page = [], 1
        while True:
            find_filter = {"page": page, "per_page": PAGE_SIZE, "sort": "path", "direction": "ASC"}
            data = self.call(FIND_IMAGE_IDS, {"image_filter": image_filter, "filter": find_filter})
            images = data["findImages"]["images"]
            for image in images:
                found.append((image["id"], image_path(image)))
                if limit and len(found) >= limit:
                    return found
            if len(images) < PAGE_SIZE:
                return found
            page += 1

    def find_image(self, image_id):
        image = self.call(FIND_IMAGE, {"id": image_id})["findImage"]
        if image is None:
            raise RuntimeError("image not found")
        return image

    def scrape_image(self, scraper_id, image_id):
        variables = {"source": {"scraper_id": scraper_id}, "input": {"image_id": image_id}}
        return self.call(SCRAPE_IMAGE, variables)["scrapeSingleImage"] or []

    def create(self, field, create_input):
        """Create a performer, tag or studio (field 'performers', 'tags' or 'studio'); return its ID."""
        query, name = {
            "performers": (PERFORMER_CREATE, "performerCreate"),
            "tags": (TAG_CREATE, "tagCreate"),
            "studio": (STUDIO_CREATE, "studioCreate"),
        }[field]
        return self.call(query, {"input": create_input})[name]["id"]

    def find_by_name(self, field, name):
        """Performers, tags or studios whose name matches name under Stash's EQUALS (SQL LIKE).

        LIKE treats % and _ as wildcards, so callers must compare names themselves.
        """
        query, root, filter_arg, key = FIND_BY_NAME[field]
        variables = {filter_arg: {"name": {"value": name, "modifier": "EQUALS"}}, "filter": {"per_page": -1}}
        return self.call(query, variables)[root][key] or []

    def update_studio(self, update_input):
        return self.call(STUDIO_UPDATE, {"input": update_input})["studioUpdate"]

    def update_image(self, update_input):
        return self.call(IMAGE_UPDATE, {"input": update_input})["bulkImageUpdate"]
