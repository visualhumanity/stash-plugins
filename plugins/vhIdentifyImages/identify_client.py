"""Minimal Stash GraphQL client over the stdlib, using the connection Stash passes on stdin."""

import json
import urllib.request

PAGE_SIZE = 500
REGEX_SPECIAL = set("\\.+*?()|[]{}^$")

CONFIGURATION = """
query PluginConfiguration($include: [ID!]) {
  configuration { plugins(include: $include) }
}"""

FIND_IMAGE_IDS = """
query FindImageIds($image_filter: ImageFilterType, $filter: FindFilterType) {
  findImages(image_filter: $image_filter, filter: $filter) {
    count
    images { id visual_files { ... on ImageFile { path } ... on VideoFile { path } } }
  }
}"""

FIND_IMAGE = """
query FindImage($id: ID!) {
  findImage(id: $id) {
    id title code details date organized urls
    performers { id name }
    tags { id name }
    visual_files { ... on ImageFile { path } ... on VideoFile { path } }
  }
}"""

SCRAPE_IMAGE = """
query ScrapeSingleImage($source: ScraperSourceInput!, $input: ScrapeSingleImageInput!) {
  scrapeSingleImage(source: $source, input: $input) {
    title code details photographer urls date
    performers { stored_id name disambiguation urls }
    tags { stored_id name }
  }
}"""

IMAGE_UPDATE = """
mutation ImageUpdate($input: ImageUpdateInput!) {
  imageUpdate(input: $input) { id }
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

    def find_images(self, prefixes, limit):
        """List (id, path) for images under the prefixes, sorted by path, up to limit (0 = all)."""
        image_filter = {}
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

    def update_image(self, update_input):
        return self.call(IMAGE_UPDATE, {"input": update_input})["imageUpdate"]
