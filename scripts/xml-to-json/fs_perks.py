"""Extract the Final Stand (HOFF) perk trees into data/fs-perks.json.

The game stores the perk trees in two places under xml/attrib/instances/perks:

  persistent_perk_tree/hoff/<tree>.xml   one file per faction, the tier layout
  persistent_perk/hoff/<faction>/*.xml   one file per perk, name / cost / modifiers

This script joins the two into a single view friendly file. All text stays as
locstring IDs (strings) so the website can resolve them per language against
data/locales/<lang>-locstring.json.

Most faction perks only store their differences against a generic perk in
persistent_perk/hoff/ (parent_pbg), so the XML is merged with its parent chain
before it is read - that, and the rest of the raw instance reading, lives in
hoff_instances.py.

Usage (from anywhere):  python scripts/xml-to-json/fs_perks.py
"""

import json
import os
import xml.etree.ElementTree as ET

from hoff_instances import (
    EXPORT_DIR,
    INSTANCES_DIR,
    PROJECT_ROOT_DIR,
    RACE_KEYS,
    as_int,
    as_locstring,
    as_path,
    find_named,
    find_named_value,
    load_variant,
    parse_custom_properties,
    parse_ui_info,
)

PERK_TREE_DIR = os.path.join(INSTANCES_DIR, "perks", "persistent_perk_tree", "hoff")
EXPORT_FILE = "fs-perks.json"


def parse_modifiers(level_element):
    """Flatten every non empty custom property list into one list of modifiers."""
    return parse_custom_properties(level_element)


def parse_perk(perk_reference):
    """Parse one perks\\persistent_perk\\hoff\\... instance file."""
    variant = load_variant(perk_reference)
    bag = find_named(variant, "group", "persistent_perk_bag")
    if bag is None:
        raise ValueError("No persistent_perk_bag in " + perk_reference)

    levels = []
    level_list = find_named(bag, "list", "levels")
    if level_list is not None:
        for index, level in enumerate(level_list.findall("group"), start=1):
            levels.append(
                {
                    "level": index,
                    "cost": as_int(find_named_value(level, "int", "level_cost")),
                    "modifiers": parse_modifiers(level),
                    "ui": parse_ui_info(find_named(level, "template_reference", "ui_info_override")),
                }
            )

    return {
        "id": perk_reference.replace("\\", "/").rsplit("/", 1)[-1],
        "path": as_path(perk_reference),
        "pbgid": as_int(find_named_value(variant, "uniqueid", "pbgid")),
        "playerUpgrade": as_path(find_named_value(bag, "instance_reference", "player_upgrade")),
        "ui": parse_ui_info(find_named(bag, "template_reference", "ui_info")),
        "maxLevel": len(levels),
        "totalCost": sum(level["cost"] or 0 for level in levels),
        "levels": levels,
    }


def parse_perk_tree(path):
    """Parse one perks\\persistent_perk_tree\\hoff\\<faction>.xml file."""
    variant = ET.parse(path).getroot().find("variant")
    bag = find_named(variant, "group", "persistent_perk_tree_bag")

    race = find_named_value(bag, "instance_reference", "race")
    race_key = RACE_KEYS.get(race)
    if race_key is None:
        raise KeyError("Unknown race " + str(race) + " in " + path + " - add it to RACE_KEYS")

    tiers = []
    level_list = find_named(bag, "list", "levels")
    if level_list is not None:
        for index, level in enumerate(level_list.findall("group"), start=1):
            perk_list = find_named(level, "list", "perks")
            perks = []
            if perk_list is not None:
                perks = [parse_perk(perk.get("value")) for perk in perk_list]
            tiers.append(
                {
                    "tier": index,
                    "unlockThreshold": as_int(find_named_value(level, "int", "unlock_threshold")),
                    "perks": perks,
                }
            )

    # the tree ui_info is a plain group, not a tables\ui_game_item_info template
    ui = {}
    ui_group = find_named(bag, "group", "ui_info")
    if ui_group is not None:
        ui = {
            "name": as_locstring(find_named_value(ui_group, "locstring", "name")),
            "icon": as_path(find_named_value(ui_group, "file", "icon")) or None,
            "backgroundImage": as_path(find_named_value(ui_group, "file", "background_image")) or None,
        }
        ui = {key: value for key, value in ui.items() if value is not None}

    return race_key, {
        "id": os.path.splitext(os.path.basename(path))[0],
        "pbgid": as_int(find_named_value(variant, "uniqueid", "pbgid")),
        "race": as_path(race),
        "perkPool": find_named_value(bag, "string", "perk_pool"),
        "perkPointsPool": find_named_value(bag, "string", "perk_points_pool"),
        "ui": ui,
        "tiers": tiers,
    }


def main():
    print("Parsing Final Stand (HOFF) perk trees...")
    print("## Root dir " + PROJECT_ROOT_DIR)

    if not os.path.isdir(PERK_TREE_DIR):
        raise SystemExit(
            "Perk tree folder not found: " + PERK_TREE_DIR + "\n"
            "Unpack ReferenceAttributes.sga into xml/attrib first (see the README)."
        )

    tree_files = sorted(
        os.path.join(PERK_TREE_DIR, name)
        for name in os.listdir(PERK_TREE_DIR)
        if name.endswith(".xml")
    )
    if not tree_files:
        raise SystemExit("No perk tree files found in " + PERK_TREE_DIR)

    races = {}
    for path in tree_files:
        race_key, tree = parse_perk_tree(path)
        perk_count = sum(len(tier["perks"]) for tier in tree["tiers"])
        print("- " + race_key + ": " + str(len(tree["tiers"])) + " tiers, " + str(perk_count) + " perks")
        races[race_key] = tree

    os.makedirs(EXPORT_DIR, exist_ok=True)
    export_path = os.path.join(EXPORT_DIR, EXPORT_FILE)
    with open(export_path, "w", encoding="utf-8") as file:
        json.dump({"races": dict(sorted(races.items()))}, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("Parsing done. Written to " + export_path)


if __name__ == "__main__":
    main()
