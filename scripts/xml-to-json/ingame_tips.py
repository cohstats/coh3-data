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


def parse_tip(instance_reference):
    variant = load_variant(instance_reference)
    group = find_named(variant, "group", "tip")
    if group is None:
        raise ValueError("No tip group in " + instance_reference)

    tip_id = instance_reference.replace("\\", "/").rsplit("/", 1)[-1]

    return {
        "id": tip_id,
        "path": as_path(instance_reference),
        "pbgid": as_int(find_named_value(variant, "uniqueid", "pbgid")),
        "locstring": as_locstring(find_named_value(group, "locstring", "loadtip")),
        "category": category_of(tip_id),
        "winConditions": list_values(group, "win_conditions"),
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

    os.makedirs(EXPORT_DIR, exist_ok=True)
    export_path = os.path.join(EXPORT_DIR, EXPORT_FILE)
    with open(export_path, "w", encoding="utf-8") as file:
        json.dump({"tips": tips}, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("Parsing done. " + str(len(tips)) + " tips written to " + export_path)


if __name__ == "__main__":
    main()
