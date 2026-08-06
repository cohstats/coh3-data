"""Extract the Final Stand (HOFF) perk trees into data/fs-perks.json.

The game stores the perk trees in two places under xml/attrib/instances/perks:

  persistent_perk_tree/hoff/<tree>.xml   one file per faction, the tier layout
  persistent_perk/hoff/<faction>/*.xml   one file per perk, name / cost / modifiers

This script joins the two into a single view friendly file. All text stays as
locstring IDs (strings) so the website can resolve them per language against
data/locales/<lang>-locstring.json.

Most faction perks only store their differences against a generic perk in
persistent_perk/hoff/ (parent_pbg), so the XML is merged with its parent chain
before it is read - see merge_element().

Usage (from anywhere):  python scripts/xml-to-json/fs_perks.py
"""

import copy
import json
import os
import xml.etree.ElementTree as ET

# xml folder must be 2 levels upwards in the folder hierarchy
PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/../.."))
INSTANCES_DIR = os.path.join(PROJECT_ROOT_DIR, "xml", "attrib", "instances")
PERK_TREE_DIR = os.path.join(INSTANCES_DIR, "perks", "persistent_perk_tree", "hoff")
EXPORT_DIR = os.path.join(PROJECT_ROOT_DIR, "data")
EXPORT_FILE = "fs-perks.json"

# racebps reference -> the race key used by the other data files (battlegroup.json etc.)
RACE_KEYS = {
    "racebps\\afrika_korps": "afrika_korps",
    "racebps\\americans": "american",
    "racebps\\british_africa": "british",
    "racebps\\germans": "german",
}

# custom property lists that carry the actual perk modifiers, and how to read a value
CUSTOM_PROPERTY_LISTS = {
    "custom_float_properties": ("float", lambda e: as_float(e.get("value"))),
    "custom_int32_properties": ("int", lambda e: as_int(e.get("value"))),
    "custom_bool_properties": ("bool", lambda e: e.get("value") == "True"),
    "custom_enum_properties": ("enum", lambda e: e.get("value")),
    "custom_hash_key_properties": ("hash_key", lambda e: e.get("value")),
    "custom_loc_string_properties": ("locstring", lambda e: e.get("value")),
    "custom_pbgid_properties": ("pbgid", lambda e: as_path(e.get("value"))),
    "custom_vector3f_properties": ("vector3f", lambda e: e.get("value")),
}


def as_int(value):
    return int(float(value)) if value not in (None, "") else None


def as_float(value):
    return float(value) if value not in (None, "") else None


def as_path(value):
    """Backslash instance paths are exported with forward slashes, like the other files."""
    return value.replace("\\", "/") if value else value


def as_locstring(value):
    """0 means "not set" in the attribute editor - export it as None instead."""
    return value if value not in (None, "", "0") else None


def find_named(parent, tag, name):
    for child in parent.findall(tag):
        if child.get("name") == name:
            return child
    return None


def find_named_value(parent, tag, name):
    element = find_named(parent, tag, name)
    return element.get("value") if element is not None else None


def match_in_parent(parent, child):
    """Find the element of parent that child overrides.

    Inside a list an override carries List.ParentItemID pointing at the parent item,
    everywhere else an element is identified by its tag and name.
    """
    parent_item_id = child.get("List.ParentItemID")
    if parent_item_id is not None:
        for element in parent:
            if element.get("List.ItemID") == parent_item_id:
                return element
        return None

    for element in parent:
        if element.tag == child.tag and element.get("name") == child.get("name"):
            return element
    return None


def merge_element(parent, child):
    """Overlay a child instance element on top of its parent instance element."""
    merged = copy.deepcopy(parent)

    for key, value in child.attrib.items():
        if key != "overrideParent":
            merged.set(key, value)

    for child_element in child:
        parent_element = match_in_parent(merged, child_element)
        if parent_element is None:
            merged.append(copy.deepcopy(child_element))
        else:
            merged[list(merged).index(parent_element)] = merge_element(parent_element, child_element)

    return merged


_resolved_variants = {}


def load_variant(instance_reference):
    """Load an instance and merge it with its parent chain. Cached, parents are shared."""
    if instance_reference in _resolved_variants:
        return _resolved_variants[instance_reference]

    path = os.path.join(INSTANCES_DIR, instance_reference.replace("\\", os.sep) + ".xml")
    if not os.path.isfile(path):
        raise FileNotFoundError("Instance not found: " + path)

    variant = ET.parse(path).getroot().find("variant")
    parent_reference = find_named_value(variant, "instance_reference", "parent_pbg")
    if parent_reference:
        variant = merge_element(load_variant(parent_reference), variant)

    _resolved_variants[instance_reference] = variant
    return variant


def parse_ui_info(element):
    """Read the interesting fields of a tables\\ui_game_item_info template reference."""
    if element is None:
        return {}

    ui = {
        "screenName": as_locstring(find_named_value(element, "locstring", "screen_name")),
        "screenNameShort": as_locstring(find_named_value(element, "locstring", "screen_name_short")),
        "briefText": as_locstring(find_named_value(element, "locstring", "brief_text")),
        "helpText": as_locstring(find_named_value(element, "locstring", "help_text")),
        "extraText": as_locstring(find_named_value(element, "locstring", "extra_text")),
        "icon": as_path(find_named_value(element, "file", "icon_name")) or None,
        "iconAlternate": as_path(find_named_value(element, "file", "icon_alternate_name")) or None,
    }

    # The per level description is usually a formatter ("%1:.p%") plus its arguments,
    # so the website has to format it itself - keep both parts.
    for key, source in (
        ("screenNameFormatter", "screen_name_formatter"),
        ("briefTextFormatter", "brief_text_formatter"),
        ("helpTextFormatter", "help_text_formatter"),
    ):
        formatter = parse_formatter(find_named(element, "template_reference", source))
        if formatter is not None:
            ui[key] = formatter

    return {key: value for key, value in ui.items() if value is not None}


def parse_formatter(element):
    if element is None or not element.get("value"):
        return None

    formatter = as_locstring(find_named_value(element, "locstring", "formatter"))
    if formatter is None:
        return None

    arguments = []
    argument_list = find_named(element, "list", "formatter_arguments")
    if argument_list is not None:
        for argument in argument_list:
            name = argument.get("name")
            value = argument.get("value")
            if name == "int_value":
                arguments.append(as_int(value))
            elif name == "float_value":
                arguments.append(as_float(value))
            elif name == "locstring_value":
                arguments.append(as_locstring(value))
            else:
                arguments.append(value)

    return {"formatter": formatter, "arguments": arguments}


def parse_modifiers(level_element):
    """Flatten every non empty custom property list into one list of modifiers."""
    modifiers = []
    properties = find_named(level_element, "template_reference", "custom_properties")
    if properties is None:
        return modifiers

    for list_name, (value_type, read_value) in CUSTOM_PROPERTY_LISTS.items():
        property_list = find_named(properties, "list", list_name)
        if property_list is None:
            continue
        for entry in property_list:
            modifier_id = find_named_value(entry, "enum", "id")
            # pbgid properties hold their value in a pbg reference, everything else
            # in a <type name="value" /> element
            pbg = find_named(entry, "instance_reference", "pbg")
            if pbg is not None:
                value = as_path(pbg.get("value"))
            else:
                value_element = next(
                    (child for child in entry if child.get("name") == "value"), None
                )
                if value_element is None:
                    continue
                value = read_value(value_element)

            modifiers.append({"id": modifier_id, "type": value_type, "value": value})

    return modifiers


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
