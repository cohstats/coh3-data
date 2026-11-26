"""Extract the loading screen tips into data/ingame-tips.json.

Every tip is one instance under xml/attrib/instances/load_tips (Final Stand tips live in
the hoff subfolder). The text stays as a locstring ID so the website can resolve it per
language against data/locales/<lang>-locstring.json, the same as the other exports.

Usage (from anywhere):  python scripts/xml-to-json/ingame_tips.py
"""

import json
import os
import re

from hoff_instances import (
    EXPORT_DIR,
    INSTANCES_DIR,
    PROJECT_ROOT_DIR,
    as_int,
    as_locstring,
    as_path,
    find_named,
    find_named_value,
    load_variant,
)

TIPS_FOLDER = "load_tips"
TIPS_DIR = os.path.join(INSTANCES_DIR, TIPS_FOLDER)
EXPORT_FILE = "ingame-tips.json"


def list_values(group, list_name):
    """Values of a simple list (e.g. win_conditions), empty entries dropped."""
    element = find_named(group, "list", list_name)
    if element is None:
        return []
    return [child.get("value") for child in element if child.get("value")]


def category_of(tip_id):
    """tipengineer7 -> engineer, hoff_tipwaves1 -> waves. Only a grouping hint."""
    name = re.sub(r"^hoff_", "", tip_id)
    name = re.sub(r"^tip", "", name)
    return re.sub(r"\d+$", "", name) or None


# Broader topic per category. A category the game adds later and that is not listed here
# lands in OTHER_TOPIC (and is reported when the script runs) - add it here then.
OTHER_TOPIC = "other"
CATEGORY_TOPICS = {
    # Combat basics
    "accuracy": "combat",
    "attackmove": "combat",
    "cover": "combat",
    "crewshock": "combat",
    "facing": "combat",
    "fire": "combat",
    "garrison": "combat",
    "holdfire": "combat",
    "prioritize": "combat",
    "suppress": "combat",
    "weapons": "combat",
    # Vehicles and support weapons
    "antiair": "vehicles",
    "armor": "vehicles",
    "artillery": "vehicles",
    "indirect": "vehicles",
    "transport": "vehicles",
    # Engineers and building
    "barbedwire": "engineering",
    "breach": "engineering",
    "bridge": "engineering",
    "engineer": "engineering",
    "explosives": "engineering",
    # Visibility
    "los": "visibility",
    "smoke": "visibility",
    # Economy
    "capture": "economy",
    "commandpoints": "economy",
    "resources": "economy",
    "upkeep": "economy",
    # Unit care
    "experience": "unit_care",
    "health": "unit_care",
    "restore": "unit_care",
    "retreat": "unit_care",
    "veterancy": "unit_care",
    # Controls and UI
    "audio": "controls",
    "commandcard": "controls",
    "controls": "controls",
    "groups": "controls",
    "move": "controls",
    # Abilities and units
    "grenades": "abilities",
    "rangers": "abilities",
    # Final Stand
    "perks": "final_stand",
    "waves": "final_stand",
}


def parse_tip(instance_reference):
    variant = load_variant(instance_reference)
    group = find_named(variant, "group", "tip")
    if group is None:
        raise ValueError("No tip group in " + instance_reference)

    tip_id = instance_reference.replace("\\", "/").rsplit("/", 1)[-1]
    category = category_of(tip_id)
    # Tips limited to a game mode list its win condition (e.g. hoff for Final Stand).
    win_conditions = list_values(group, "win_conditions")

    return {
        "id": tip_id,
        "path": as_path(instance_reference),
        "pbgid": as_int(find_named_value(variant, "uniqueid", "pbgid")),
        "locstring": as_locstring(find_named_value(group, "locstring", "loadtip")),
        "category": category,
        "topic": CATEGORY_TOPICS.get(category, OTHER_TOPIC),
        "gameMode": win_conditions[0] if win_conditions else None,
    }


def main():
    print("Parsing loading screen tips...")
    print("## Root dir " + PROJECT_ROOT_DIR)

    if not os.path.isdir(TIPS_DIR):
        raise SystemExit(
            "Tips folder not found: " + TIPS_DIR + "\n"
            "Unpack ReferenceAttributes.sga into xml/attrib first (see the README)."
        )

    references = []
    for root, _dirs, files in os.walk(TIPS_DIR):
        for name in files:
            if name.endswith(".xml"):
                relative = os.path.relpath(os.path.join(root, name[:-4]), INSTANCES_DIR)
                references.append(relative.replace(os.sep, "\\"))

    if not references:
        raise SystemExit("No tip files found in " + TIPS_DIR)

    tips = [parse_tip(reference) for reference in references]
    missing_text = [tip["id"] for tip in tips if not tip["locstring"]]
    if missing_text:
        print("Warning: tips without a locstring: " + ", ".join(missing_text))
    tips = [tip for tip in tips if tip["locstring"]]
    tips.sort(key=lambda tip: tip["path"])

    unmapped = sorted({tip["category"] for tip in tips if tip["category"] not in CATEGORY_TOPICS})
    if unmapped:
        print("Warning: categories without a topic (exported as other): " + ", ".join(map(str, unmapped)))

    os.makedirs(EXPORT_DIR, exist_ok=True)
    export_path = os.path.join(EXPORT_DIR, EXPORT_FILE)
    with open(export_path, "w", encoding="utf-8") as file:
        json.dump({"tips": tips}, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("Parsing done. " + str(len(tips)) + " tips written to " + export_path)


if __name__ == "__main__":
    main()
