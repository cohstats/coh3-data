import os
from pprint import PrettyPrinter
from typing import Callable, Literal, TypeVar, TypedDict, Union

from scriptUtils import (
    build_files_dictionary,
    get_nth_level_parent,
    get_path_as_string,
    resolve_dict_value_by_path,
)
from weapons import parse_weapon_xml_data

# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# xml data source folder
xml_data_dir = os.path.abspath(
    os.path.join(get_nth_level_parent(script_root_dir, 2), "xml")
)


class TemplateReference(TypedDict):
    name: str
    value: str


class UiInfo(TypedDict):
    brief_text: TypedDict("", {"locstring": TemplateReference})
    extra_help_text: TypedDict("", {"locstring": TemplateReference})
    extra_text: TypedDict("", {"locstring": TemplateReference})
    help_text: TypedDict("", {"locstring": TemplateReference})
    icon_name: str
    portrait_name: str
    screen_name: TypedDict("", {"locstring": TemplateReference})
    selection_group: str
    symbol_icon_name: str


class RawSbpsExtensionRaceListSchema:
    race_data: TypedDict("", {"info": UiInfo})


class RawSbpsExtensionUiSchema(TypedDict):
    race_list: list[RawSbpsExtensionRaceListSchema]
    template_reference: TemplateReference


class RawSbpsExtensionSchema(TypedDict):
    # Union of several types of extensions.
    squadexts: RawSbpsExtensionUiSchema


class RawSbpsParentPbgSchema(TypedDict):
    # Path to the parent sbps. If not set, null (None).
    instance_reference: Union[str, None]


class RawSbpsSchema(TypedDict):
    # Path to the parent blueprint.
    parent_pbg: RawSbpsParentPbgSchema
    # Unique ID of the squad blueprint
    pbgid: int
    # Extensions
    extensions: list[RawSbpsExtensionSchema]


FACTION = Literal["afrika_korps", "american", "british", "british_africa", "german"]

# Sub-folder of sbps/races
SBPS_RACES = Literal[
    "afrika_korps", "american", "british", "british_africa", "german", "common", "npc"
]

# Sub-folder of each sbps/races/xyz
SBPS_TYPES = Literal[
    "africa",
    "aircraft",
    "ally",
    "attachment",
    "campaign",
    "civilian",
    "company",
    "emplacements",
    "gameplay",
    "humans",
    "infantry",
    "italian",
    "italy",
    "mass_production",
    "naval",
    "north_africa",
    "parent",
    "sp",
    "special_operations",
    "special",
    "squad_size_variants",
    "team_weapons",
    "vehicles",
]


class SquadBlueprint(TypedDict):
    # Squad ID
    id: str
    # Faction
    faction: FACTION
    # Parent blueprint id, otherwise None.
    parent_pbg: str | None
    # Type obtained from the parent folder.
    parent_type: str


# Initialize our dictionary of squad (parent and inherited) blueprints.
SBPS_PARENT_DICT: dict[str, SquadBlueprint] = {}
SBPS_INHERIRED_DICT: dict[str, SquadBlueprint] = {}


# Get the SBPS source (one folder as example).
sbps_src_dir = os.path.abspath(
    os.path.join(xml_data_dir, "attrib\\instances\\sbps\\races")
)

T = TypeVar("T")


def traverseTree(
    entity: dict,
    checkRelevant: Callable[[str, dict], bool],
    mapper: Callable[[str, dict, str, str], T],
    path: str,
    parent: str,
) -> dict[str, T]:
    relevantSet: dict[str, T] = {}

    if parent == "":
        parent = path

    entityKeys: list[str] = entity.keys()

    for entityKey in entityKeys:
        # print(f'Parent: {parent} - Entity Key: {entityKey}')
        # Extend path
        currentPath = path + "/" + entityKey
        # check if object is relevant (eg. is weapon_bag?)
        isRelevant = checkRelevant(entityKey, entity[entityKey])

        if (
            not isRelevant
            and entity[entityKey] is not None
            and type(entity[entityKey]) is dict
        ):
            # Remember current node as parrent (parent folder e.g. rifle)
            newParent = entityKey

            # Going one step down in the object tree!!
            childSet = traverseTree(
                entity[entityKey], checkRelevant, mapper, currentPath, newParent
            )

            # Merge relevant object of child
            for [itemKey, itemSet] in childSet.items():
                relevantSet[itemKey] = itemSet

        elif isRelevant:
            if mapper:
                relevantSet[entityKey] = mapper(
                    entityKey, entity[entityKey], path, parent
                )
            else:
                relevantSet[entityKey] = entity[entityKey]

    return relevantSet


def mapperEbps(
    filename: str, subtree: RawSbpsSchema, jsonPath: str, parent: str
) -> SquadBlueprint:
    # print(f"Current EBPS -> {filename}")

    parent_pbg = subtree["parent_pbg"]["instance_reference"].rsplit("/", 1)[-1]

    sbpsEntity: SquadBlueprint = {
        "id": filename,
        "faction": jsonPath.split("/")[1] or jsonPath,
        "parent_pbg": parent_pbg or None,
        "parent_type": parent,
    }

    return sbpsEntity


def parseSquadBlueprintXML():
    generated_dict = build_files_dictionary(sbps_src_dir, parse_weapon_xml_data)
    parsed_json: dict[SBPS_RACES, dict[SBPS_TYPES, SquadBlueprint]] = dict(
        resolve_dict_value_by_path(generated_dict, get_path_as_string(sbps_src_dir))
    )

    # Store the count of types.
    sbps_types = {}

    for [raceKey, raceObj] in parsed_json.items():
        print(f"---------------- Processing set of {raceKey} ----------------")
        sbps_set = traverseTree(
            raceObj,
            lambda key, obj: "extensions" in obj.keys() if type(obj) is dict else False,
            mapperEbps,
            raceKey,
            raceKey,
        )

        for [squadId, squadDict] in sbps_set.items():
            # Misc, list the parent types and count each.
            parent_type = squadDict.get("parent_type") or None
            if sbps_types.get(parent_type) is not None:
                sbps_types[parent_type] += 1
            else:
                sbps_types[parent_type] = 1

            # Group by parent / inherited sbps.
            if squadDict.get("parent_pbg") is None:
                SBPS_PARENT_DICT[squadId] = squadDict
            else:
                SBPS_INHERIRED_DICT[squadId] = squadDict

    print(f"Total Parent Squad blueprints: {len(SBPS_PARENT_DICT.keys())}")
    # print(SBPS_PARENT_DICT.keys())

    print(f"Total Inherited Squad blueprints: {len(SBPS_INHERIRED_DICT.keys())}")
    # print(SBPS_INHERIRED_DICT.keys())

    # Pretty print parent dictionary
    print("{:<50} {:<20} {:<20} {:<20}".format("ID", "Faction", "Type", "PARENT PBG"))
    for k, v in SBPS_PARENT_DICT.items():
        id = v.get("id")
        faction = v.get("faction")
        parent_pbg = v.get("parent_pbg") or ""
        parent_type = v.get("parent_type")

        print(
            "{:<50} {:<20} {:<20} {:<20}".format(id, faction, parent_type, parent_pbg)
        )

    print("---------------------------------------------------------------------------")

    # Pretty print inherited dictionary
    for k, v in SBPS_INHERIRED_DICT.items():
        id = v.get("id")
        faction = v.get("faction")
        parent_pbg = v.get("parent_pbg")
        parent_type = v.get("parent_type")

        print(
            "{:<50} {:<20} {:<20} {:<20}".format(id, faction, parent_type, parent_pbg)
        )

    pp = PrettyPrinter()

    pp.pprint(sbps_types)
    print(sbps_types.keys())

    # Filter and find the parent blueprints.
    # parentSbps = getAllSquadParent(parsed_json)

    # Get a single entity to pretty print and extract the schemas.
    # bersaglieriSbps = parsed_json['bersaglieri_ak']
