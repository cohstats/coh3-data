"""Shared reader for the raw attribute instances under xml/attrib/instances.

The Final Stand (HOFF) exports (fs_perks.py, fs_technologies.py) all work on the same
instance XML: a file holds only its differences against a parent instance (parent_pbg),
so an instance has to be merged with its whole parent chain before anything can be read
off it - see merge_element() and load_variant().

Everything here is generic; the export specific logic lives in the scripts themselves.
"""

import copy
import os
import xml.etree.ElementTree as ET

# xml folder must be 2 levels upwards in the folder hierarchy
PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/../.."))
INSTANCES_DIR = os.path.join(PROJECT_ROOT_DIR, "xml", "attrib", "instances")
EXPORT_DIR = os.path.join(PROJECT_ROOT_DIR, "data")

# racebps reference -> the race key used by the other data files (battlegroup.json etc.)
RACE_KEYS = {
    "racebps\\afrika_korps": "afrika_korps",
    "racebps\\americans": "american",
    "racebps\\british_africa": "british",
    "racebps\\germans": "german",
}

# custom property lists that carry the actual modifiers, and how to read a value
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

    An item which only has a List.ItemID is a new one the child adds to the list (the
    attribute editor marks those with List.ListAction="Append"). It must not fall through to
    the tag / name match below - every item of a list shares the same tag and name, so the
    new item would silently be merged into the first item of the parent list instead of being
    appended to it, which loses a level of the perk.
    """
    parent_item_id = child.get("List.ParentItemID")
    if parent_item_id is not None:
        for element in parent:
            if element.get("List.ItemID") == parent_item_id:
                return element
        return None

    if child.get("List.ItemID") is not None:
        return None

    for element in parent:
        if element.tag == child.tag and element.get("name") == child.get("name"):
            return element
    return None


def removed_item_ids(child):
    """Items of the parent list the child removes, eg. removedIds="123, -456"."""
    removed = child.get("removedIds")
    if not removed:
        return set()

    return {item_id.strip() for item_id in removed.split(",") if item_id.strip()}


def merge_element(parent, child):
    """Overlay a child instance element on top of its parent instance element."""
    merged = copy.deepcopy(parent)

    for key, value in child.attrib.items():
        if key not in ("overrideParent", "removedIds"):
            merged.set(key, value)

    # A list drops the parent items it lists in removedIds, eg. the Afrikakorps unit training
    # time perk replaces the second level of the generic perk with one of its own.
    for item_id in removed_item_ids(child):
        for element in list(merged):
            if element.get("List.ItemID") == item_id:
                merged.remove(element)

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


def parse_custom_properties(element, property_group="custom_properties", include_lists=False):
    """Flatten every non empty custom property list into one list of {id, type, value}.

    element is the group / instance that holds the custom_property_template reference.
    With include_lists a custom_..._list_property (a property whose value is a list of pbgs,
    like SQUAD_STATUS_DECORATOR_PBG) is read as well and its value is a list.
    """
    properties = []
    container = find_named(element, "template_reference", property_group)
    if container is None:
        return properties

    for list_name, (value_type, read_value) in CUSTOM_PROPERTY_LISTS.items():
        property_list = find_named(container, "list", list_name)
        if property_list is None:
            continue
        for entry in property_list:
            property_id = find_named_value(entry, "enum", "id")

            # a ..._list_property holds its values in a nested <list name="list" />
            value_list = find_named(entry, "list", "list") if include_lists else None
            if value_list is not None:
                properties.append({
                    "id": property_id,
                    "type": value_type,
                    "value": [as_path(item.get("value")) for item in value_list],
                })
                continue

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

            properties.append({"id": property_id, "type": value_type, "value": value})

    return properties
