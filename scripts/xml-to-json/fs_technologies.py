"""Extract the Final Stand (HOFF) technology choices into data/fs-technologies.json.

Final Stand calls these "Technology Choices": at the start of the game and at the start of
every wave the player is offered a small number of technologies (3 by default) and picks
one. It is the in-match progression, as opposed to the meta progression in fs-perks.json.

The data comes from two archives:

  ReferenceAttributes.sga -> xml/attrib/instances (unpacked by the README steps)

      custom_property_container/hoff/technologies/*.xml   the pool per faction, plus a
                                                          "common" pool added to all of them
      upgrade/hoff/**/technology/*.xml                    one file per technology

  Data.sga -> scar/hoff/hoff_technologymenu.scar

      the order of the twelve picks and the bucket (which technologies may be offered) each
      pick draws from. This is game script, not attributes, so it cannot be read from the
      xml folder - pass the folder Data.sga was unpacked into with --game-data.

A technology may be offered only when the current pick index is within its
THRESHOLD_MIN / THRESHOLD_MAX (exported as thresholdMin / thresholdMax), except for buckets
flagged ignoreThresholds. Which of the matching technologies are shown is a weighted random
draw, so this file describes what *can* appear, not a fixed tree.

All text stays as locstring IDs (strings) so the website can resolve them per language
against data/locales/<lang>-locstring.json.

Usage (from anywhere):
    python scripts/xml-to-json/fs_technologies.py --game-data ./game-data
"""

import argparse
import json
import os
import re

from hoff_instances import (
    EXPORT_DIR,
    INSTANCES_DIR,
    PROJECT_ROOT_DIR,
    RACE_KEYS,
    as_int,
    as_path,
    find_named,
    find_named_value,
    load_variant,
    parse_custom_properties,
    parse_ui_info,
)

TECHNOLOGY_LIST_DIR = os.path.join(INSTANCES_DIR, "custom_property_container", "hoff", "technologies")
TECHNOLOGY_LIST_REFERENCE = "custom_property_container\\hoff\\technologies\\"
STATE_MODEL_SCHEMA = "statemodel_schema\\technologymenu"
EXPORT_FILE = "fs-technologies.json"

# where hoff_technologymenu.scar sits inside an unpacked Data.sga
SCAR_RELATIVE_PATH = os.path.join("scar", "hoff", "hoff_technologymenu.scar")
DEFAULT_GAME_DATA_DIR = os.path.join(PROJECT_ROOT_DIR, "game-data")

# only upgrades whose ui_menu points here are treated as technologies by the game
# (see Technologies_IsTechnologyPBG in scar/hoff/technologymenu.scar)
TECHNOLOGY_UI_MENU = "menu\\technologies"

# the upgrade_type that decides which of the three menus a technology belongs to
CATEGORIES = {
    "Technology_Unit": "unit",
    "Technology_Ability": "ability",
    "Technology_Passive": "passive",
    "Technology_Legendary": "legendary",
    "Technology_Commander": "commander",
}
BUCKET_TYPE_PATTERN = re.compile(r"^Technology_\w+_Bucket\d+$")

# defaults the game falls back to when a technology does not set the property itself
DEFAULT_WEIGHT = 100
DEFAULT_THRESHOLD_MIN = 0
DEFAULT_THRESHOLD_MAX = 9999


#
# Technologies (xml/attrib)
#

def parse_technology_list(file_name):
    """Read one custom_property_container\\hoff\\technologies list instance.

    Returns (race_key, list_id, pbgid, race_reference, [technology references]). A list
    without an OWNER is the common pool the game adds to every faction pool.
    """
    list_id = os.path.splitext(file_name)[0]
    variant = load_variant(TECHNOLOGY_LIST_REFERENCE + list_id)
    bag = find_named(variant, "template_reference", "custom_property_bag")
    if bag is None:
        raise ValueError("No custom_property_bag in " + list_id)

    race_reference = None
    references = []
    for property_list in bag.findall("list"):
        for entry in property_list:
            property_id = find_named_value(entry, "enum", "id")
            if property_id == "OWNER":
                pbg = find_named(entry, "instance_reference", "pbg")
                race_reference = pbg.get("value") if pbg is not None else None
            elif property_id == "UPGRADE_PBG_1":
                value_list = find_named(entry, "list", "list")
                if value_list is not None:
                    references = [item.get("value") for item in value_list]

    if race_reference is None:
        return "common", list_id, as_int(find_named_value(variant, "uniqueid", "pbgid")), None, references

    race_key = RACE_KEYS.get(race_reference)
    if race_key is None:
        raise KeyError("Unknown race " + str(race_reference) + " in " + list_id + " - add it to RACE_KEYS")

    return (
        race_key,
        list_id,
        as_int(find_named_value(variant, "uniqueid", "pbgid")),
        as_path(race_reference),
        references,
    )


def parse_technology(reference, source):
    """Parse one upgrade\\hoff\\...\\technology\\... instance file."""
    variant = load_variant(reference)
    bag = find_named(variant, "group", "upgrade_bag")
    if bag is None:
        raise ValueError("No upgrade_bag in " + reference)

    upgrade_types = []
    type_list = find_named(bag, "list", "upgrade_type")
    if type_list is not None:
        upgrade_types = [entry.get("value") for entry in type_list]

    properties = parse_custom_properties(variant, include_lists=True)
    values = {entry["id"]: entry["value"] for entry in properties}

    technology = {
        "id": reference.replace("\\", "/").rsplit("/", 1)[-1],
        "path": as_path(reference),
        "pbgid": as_int(find_named_value(variant, "uniqueid", "pbgid")),
        "source": source,
        # a technology with no category is never matched by any bucket - the game can only
        # ever show it when it fills up an unfinished menu from the whole pool
        "category": next((CATEGORIES[name] for name in upgrade_types if name in CATEGORIES), None),
        "buckets": [name for name in upgrade_types if BUCKET_TYPE_PATTERN.match(name)],
        "tags": [
            name for name in upgrade_types
            if name not in CATEGORIES and not BUCKET_TYPE_PATTERN.match(name)
        ],
        "thresholdMin": values.get("THRESHOLD_MIN", DEFAULT_THRESHOLD_MIN),
        "thresholdMax": values.get("THRESHOLD_MAX", DEFAULT_THRESHOLD_MAX),
        "weight": values.get("WEIGHT", DEFAULT_WEIGHT),
        "commandCost": read_command_cost(bag),
        # the game only offers upgrades that are in the technologies menu, so a technology
        # with any other ui_menu is in the list but unreachable (usually disabled content)
        "enabled": find_named_value(bag, "instance_reference", "ui_menu") == TECHNOLOGY_UI_MENU,
        "ui": parse_ui_info(find_named(bag, "group", "ui_info")),
        "properties": properties,
    }

    # the thing the technology unlocks, for cross referencing sbps.json / abilities.json
    for key, property_id in (("squad", "SQUAD_PBG_1"), ("ability", "ABILITY_PBG"), ("upgrade", "UPGRADE_PBG_1")):
        if values.get(property_id):
            technology[key] = values[property_id]

    if values.get("NUM_SHOTS") is not None:
        technology["maxOfferingCount"] = values["NUM_SHOTS"]

    return technology


def read_command_cost(bag):
    """Every technology costs one command point (the "unlock point" of a pick)."""
    time_cost = find_named(bag, "group", "time_cost")
    if time_cost is None:
        return None
    cost = find_named(time_cost, "enum_table", "cost")
    if cost is None:
        return None
    return as_int(find_named_value(cost, "float", "command"))


def read_choices_per_pick():
    """Default of the technologies_num_choices state model property (3)."""
    variant = load_variant(STATE_MODEL_SCHEMA)
    bag = find_named(variant, "group", "schema_bag")
    int_properties = find_named(bag, "list", "int_properties")
    if int_properties is not None:
        for entry in int_properties:
            if find_named_value(entry, "enum", "int_property_id") == "technologies_num_choices":
                return as_int(find_named_value(entry, "int", "default"))
    return None


def read_slot_count():
    """How many technology slots the UI has (technologies_slot_a .. _e)."""
    variant = load_variant(STATE_MODEL_SCHEMA)
    bag = find_named(variant, "group", "schema_bag")
    pbgid_properties = find_named(bag, "list", "pbgid_properties")
    if pbgid_properties is None:
        return None
    return sum(
        1 for entry in pbgid_properties
        if (find_named_value(entry, "enum", "pbgid_property_id") or "").startswith("technologies_slot_")
    )


#
# Pick order (scar/hoff/hoff_technologymenu.scar out of Data.sga)
#

BUCKET_DEFINITION_PATTERN = re.compile(
    r"^(TECHNOLOGYBUCKET_\w+)\s*=\s*\{(.*?)^\}", re.MULTILINE | re.DOTALL
)
BUCKET_LIST_PATTERN = re.compile(
    r"local\s+technologyBuckets\s*=\s*\{(.*?)^[\t ]*\}", re.MULTILINE | re.DOTALL
)
# "$11274369" is a locstring reference in scar
LOCSTRING_PATTERN = re.compile(r'^\$?(\d+)$')


def read_scar(game_data_dir):
    path = os.path.join(game_data_dir, SCAR_RELATIVE_PATH)
    if not os.path.isfile(path):
        raise SystemExit(
            "hoff_technologymenu.scar not found at: " + path + "\n"
            "It lives in Data.sga, which has to be unpacked first, eg.\n"
            "  tools/AOEMods.Essence/AOEMods.Essence.CLI.exe sga-unpack "
            '"<game>/anvil/archives/Data.sga" "' + game_data_dir + '"'
        )
    with open(path, encoding="utf-8", errors="replace") as file:
        return file.read()


def parse_bucket_definitions(scar):
    """Read the TECHNOLOGYBUCKET_* tables at the bottom of hoff_technologymenu.scar."""
    buckets = {}
    for name, body in BUCKET_DEFINITION_PATTERN.findall(scar):
        bucket = {
            "id": name,
            "upgradeTypes": re.findall(r'^\s*"([^"]+)"\s*,', body, re.MULTILINE),
            "ignoreThresholds": bool(re.search(r"ignoreThresholds\s*=\s*true", body)),
            "ignoreRestrictions": bool(re.search(r"ignoreRestrictions\s*=\s*true", body)),
            # when a bucket runs out of matching technologies the game tops the menu up with
            # anything else the player can take, unless it says not to
            "fillEmptySlots": not re.search(r"doNotFillEmptySlots\s*=\s*true", body),
        }

        title = re.search(r'displayName\s*=\s*"([^"]+)"', body)
        if title:
            match = LOCSTRING_PATTERN.match(title.group(1))
            bucket["title"] = match.group(1) if match else title.group(1)

        choices = re.search(r"numChoices\s*=\s*(\d+)", body)
        if choices:
            bucket["choices"] = int(choices.group(1))

        buckets[name] = bucket
    return buckets


def parse_pick_order(scar, buckets):
    """Read the per player bucket list in Hoff_InitializeTechnologyMenu.

    The list is the schedule of the whole match: the first entry is the pick handed out at
    the start (before wave 1), the second the pick at the start of wave 1, and so on.
    """
    block = BUCKET_LIST_PATTERN.search(scar)
    if block is None:
        raise SystemExit(
            "Could not find the 'local technologyBuckets = {' list in hoff_technologymenu.scar - "
            "the script layout changed, fs_technologies.py needs updating."
        )

    # the scar clones TECHNOLOGYBUCKET_PASSIVE into a local so a perk can widen it
    aliases = dict(re.findall(r"local\s+(\w+)\s*=\s*Clone\((TECHNOLOGYBUCKET_\w+)\)", scar))

    picks = []
    for line in block.group(1).splitlines():
        code, _, comment = line.partition("--")
        name = code.strip().rstrip(",").strip()
        if not name or name == "nil":
            continue

        bucket = buckets.get(aliases.get(name, name))
        if bucket is None:
            raise SystemExit("Unknown technology bucket '" + name + "' in hoff_technologymenu.scar")

        pick = {
            "pick": len(picks) + 1,
            # the first pick is granted before the first wave starts
            "wave": len(picks),
            "bucket": bucket["id"],
            "category": next(
                (CATEGORIES[name] for name in bucket["upgradeTypes"] if name in CATEGORIES),
                next(
                    (CATEGORIES[name.rsplit("_Bucket", 1)[0]] for name in bucket["upgradeTypes"]
                     if BUCKET_TYPE_PATTERN.match(name)),
                    None,
                ),
            ),
            "upgradeTypes": bucket["upgradeTypes"],
            "ignoreThresholds": bucket["ignoreThresholds"],
            "fillEmptySlots": bucket["fillEmptySlots"],
        }
        if "title" in bucket:
            pick["title"] = bucket["title"]
        if "choices" in bucket:
            pick["choices"] = bucket["choices"]
        if comment.strip():
            pick["note"] = comment.strip()

        picks.append(pick)

    return picks


def parse_max_offering_count(scar):
    """maxOfferingCount from the Technologies_Initialize configuration (1 = offered once)."""
    match = re.search(r"maxOfferingCount\s*=\s*(\d+)", scar)
    return int(match.group(1)) if match else None


#
# Export
#

def build_export(game_data_dir):
    # read the game script first, so a missing Data.sga fails before the slow xml parsing
    scar = read_scar(game_data_dir)
    buckets = parse_bucket_definitions(scar)

    if not os.path.isdir(TECHNOLOGY_LIST_DIR):
        raise SystemExit(
            "Technology list folder not found: " + TECHNOLOGY_LIST_DIR + "\n"
            "Unpack ReferenceAttributes.sga into xml/attrib first (see the README)."
        )

    faction_lists = {}
    common = None
    for file_name in sorted(os.listdir(TECHNOLOGY_LIST_DIR)):
        if not file_name.endswith(".xml"):
            continue
        race_key, list_id, pbgid, race_reference, references = parse_technology_list(file_name)
        entry = {"id": list_id, "pbgid": pbgid, "race": race_reference, "references": references}
        if race_key == "common":
            common = entry
        else:
            faction_lists[race_key] = entry

    if not faction_lists:
        raise SystemExit("No faction technology lists found in " + TECHNOLOGY_LIST_DIR)

    races = {}
    for race_key, faction in sorted(faction_lists.items()):
        technologies = [parse_technology(reference, "faction") for reference in faction["references"]]
        lists = [faction["id"]]
        if common is not None:
            known = {technology["path"] for technology in technologies}
            for reference in common["references"]:
                technology = parse_technology(reference, "common")
                if technology["path"] not in known:
                    technologies.append(technology)
            lists.append(common["id"])

        races[race_key] = {
            "id": faction["id"],
            "pbgid": faction["pbgid"],
            "race": faction["race"],
            "lists": lists,
            "technologies": technologies,
        }

    return {
        "meta": {
            "choicesPerPick": read_choices_per_pick(),
            "maxSlots": read_slot_count(),
            "maxOfferingCount": parse_max_offering_count(scar),
            "defaultWeight": DEFAULT_WEIGHT,
            "picks": parse_pick_order(scar, buckets),
        },
        "races": races,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--game-data",
        default=DEFAULT_GAME_DATA_DIR,
        help="folder Data.sga was unpacked into, it must contain " + SCAR_RELATIVE_PATH,
    )
    parser.add_argument(
        "--output",
        default=os.path.join(EXPORT_DIR, EXPORT_FILE),
        help="path of the JSON file to write",
    )
    arguments = parser.parse_args()

    print("Parsing Final Stand (HOFF) technology choices...")
    print("## Root dir " + PROJECT_ROOT_DIR)

    export = build_export(arguments.game_data)

    for race_key, race in export["races"].items():
        technologies = race["technologies"]
        common = sum(1 for technology in technologies if technology["source"] == "common")
        disabled = sum(1 for technology in technologies if not technology["enabled"])
        print(
            "- " + race_key + ": " + str(len(technologies)) + " technologies ("
            + str(len(technologies) - common) + " faction + " + str(common) + " common"
            + (", " + str(disabled) + " not reachable in game" if disabled else "") + ")"
        )
    print("- " + str(len(export["meta"]["picks"])) + " picks per match, "
          + str(export["meta"]["choicesPerPick"]) + " choices each")

    os.makedirs(os.path.dirname(os.path.abspath(arguments.output)), exist_ok=True)
    with open(arguments.output, "w", encoding="utf-8") as file:
        json.dump(export, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("Parsing done. Written to " + os.path.abspath(arguments.output))


if __name__ == "__main__":
    main()
