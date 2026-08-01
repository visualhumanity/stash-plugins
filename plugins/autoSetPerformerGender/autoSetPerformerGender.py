import json
import sys

from PythonDepManager import ensure_import

ensure_import("stashapi:stashapp-tools>=0.2.58")

import stashapi.log as log
from stashapi.stashapp import StashInterface

PLUGIN_ID = "autoSetPerformerGender"

VALID_GENDERS = {
    "MALE",
    "FEMALE",
    "TRANSGENDER_MALE",
    "TRANSGENDER_FEMALE",
    "INTERSEX",
    "NON_BINARY",
}


def resolve_default_gender(settings: dict) -> str | None:
    raw = (settings.get("defaultGender") or "").strip().upper()
    if not raw:
        log.error(f"{PLUGIN_ID}: defaultGender setting is not configured; skipping")
        return None
    if raw not in VALID_GENDERS:
        log.error(
            f"{PLUGIN_ID}: defaultGender setting '{raw}' is not a valid gender "
            f"({', '.join(sorted(VALID_GENDERS))}); skipping"
        )
        return None
    return raw


def handle_performer_create(stash: StashInterface, settings: dict, performer_id: str):
    performer = stash.find_performer(performer_id, fragment="id gender")
    if performer is None:
        log.error(f"{PLUGIN_ID}: performer {performer_id} not found; skipping")
        return

    if performer.get("gender"):
        log.debug(f"{PLUGIN_ID}: performer {performer_id} already has a gender set; not overwriting")
        return

    gender = resolve_default_gender(settings)
    if gender is None:
        return

    stash.update_performer({"id": performer_id, "gender": gender})
    log.info(f"{PLUGIN_ID}: set performer {performer_id} gender to {gender}")


def main():
    json_input = json.loads(sys.stdin.read())
    server_connection = json_input["server_connection"]
    stash = StashInterface(server_connection)

    config = stash.get_configuration()
    settings = config.get("plugins", {}).get(PLUGIN_ID, {})

    args = json_input.get("args", {})
    hook_context = args.get("hookContext")
    if hook_context and hook_context.get("type") == "Performer.Create.Post":
        handle_performer_create(stash, settings, hook_context["id"])


if __name__ == "__main__":
    main()
