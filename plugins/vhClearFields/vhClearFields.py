import json
import sys
import urllib.request

PLUGIN_ID = "vhClearFields"
TASK_MODE = "vhClearFields"

# field key -> (SceneUpdateInput key, factory for the empty value)
FIELD_CLEARS = {
    "title": ("title", str),
    "urls": ("urls", list),
    "date": ("date", lambda: None),
    "director": ("director", str),
    "performers": ("performer_ids", list),
    "studio": ("studio_id", lambda: None),
    "details": ("details", str),
    "stashIds": ("stash_ids", list),
    "code": ("code", str),
}
ALLOWED_FIELDS = tuple(FIELD_CLEARS)


def _as_list(args, key):
    value = args.get(key)
    if not isinstance(value, list):
        raise ValueError(f"'{key}' must be a list")
    return value


def validate_args(args):
    raw_ids = _as_list(args, "sceneIds")
    raw_fields = _as_list(args, "fields")

    scene_ids = []
    for raw in raw_ids:
        scene_id = str(raw)
        if not scene_id.isdigit():
            raise ValueError(f"invalid scene id: {scene_id!r}")
        if scene_id not in scene_ids:
            scene_ids.append(scene_id)

    unknown = [f for f in raw_fields if f not in FIELD_CLEARS]
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(map(str, unknown))}")

    fields = []
    for field in raw_fields:
        if field not in fields:
            fields.append(field)

    if not scene_ids:
        raise ValueError("no scenes given")
    if not fields:
        raise ValueError("no fields given")
    return scene_ids, fields


def build_update_input(scene_id, fields):
    update_input = {"id": scene_id}
    for field in fields:
        key, empty = FIELD_CLEARS[field]
        update_input[key] = empty()
    return update_input


def run(stash, scene_ids, fields, log):
    cleared = 0
    failed = []
    total = len(scene_ids)
    for index, scene_id in enumerate(scene_ids, start=1):
        try:
            stash.update_scene(build_update_input(scene_id, fields))
            cleared += 1
        except Exception as exc:
            failed.append(scene_id)
            log.error(f"{PLUGIN_ID}: scene {scene_id} failed: {exc}")
        log.progress(index / total)
    return cleared, failed


class Log:
    """Stash raw-plugin log protocol: level-prefixed lines on stderr."""

    @staticmethod
    def _emit(level, message):
        sys.stderr.write(f"\x01{level}\x02{message}\n")
        sys.stderr.flush()

    def info(self, message):
        self._emit("i", message)

    def error(self, message):
        self._emit("e", message)

    def progress(self, fraction):
        self._emit("p", fraction)


SCENE_UPDATE = "mutation SceneUpdate($input: SceneUpdateInput!) { sceneUpdate(input: $input) { id } }"


class StashClient:
    def __init__(self, connection):
        host = connection.get("Host") or "localhost"
        if host in ("0.0.0.0", "::"):
            host = "localhost"
        scheme = connection.get("Scheme") or "http"
        self.url = f"{scheme}://{host}:{connection.get('Port') or 9999}/graphql"
        cookie = connection.get("SessionCookie") or {}
        self.cookie = f"{cookie['Name']}={cookie['Value']}" if cookie.get("Name") else None

    def update_scene(self, update_input):
        body = json.dumps({"query": SCENE_UPDATE, "variables": {"input": update_input}})
        request = urllib.request.Request(
            self.url, data=body.encode(), headers={"Content-Type": "application/json"}
        )
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        if payload.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "unknown error") for e in payload["errors"]))
        return payload["data"]["sceneUpdate"]


def main():
    log = Log()
    json_input = json.loads(sys.stdin.read())
    args = json_input.get("args", {})
    if args.get("mode") != TASK_MODE:
        log.error(f"{PLUGIN_ID}: unrecognised task mode; nothing to do")
        return

    try:
        scene_ids, fields = validate_args(args)
    except ValueError as exc:
        log.error(f"{PLUGIN_ID}: refusing to run: {exc}")
        return

    stash = StashClient(json_input["server_connection"])
    log.info(
        f"{PLUGIN_ID}: clearing {len(fields)} field(s) on {len(scene_ids)} scene(s)"
    )
    cleared, failed = run(stash, scene_ids, fields, log)

    log.info(f"{PLUGIN_ID}: cleared {cleared}, failed {len(failed)}")
    if failed:
        log.error(f"{PLUGIN_ID}: failed scene ids: {', '.join(failed)}")


if __name__ == "__main__":
    main()
