import os
import json
import xml.etree.ElementTree as ET
from scriptUtils import get_nth_level_parent, get_attribute, has_children, string_num, get_optional_value

LIST_META_PREFIX = "__list_meta__"
LIST_ITEM_META_KEY = "__list_item_meta"
OVERRIDE_PARENT_META_KEY = "__override_parent"

def parse_removed_ids(value):
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def get_list_meta_key(list_name):
    return f"{LIST_META_PREFIX}{list_name}"


def get_list_item_meta(element: ET.Element):
    meta = {}

    if "List.ItemID" in element.attrib:
        meta["item_id"] = element.attrib["List.ItemID"]

    if "List.ParentItemID" in element.attrib:
        meta["parent_item_id"] = element.attrib["List.ParentItemID"]

    if "List.ListAction" in element.attrib:
        meta["action"] = element.attrib["List.ListAction"]

    return meta

def parse_weapon_xml_data(element: ET.Element,blacklist:list = []) -> dict:
    """Parses XML data from a given ElementTree element and returns a dictionary.

    Added blacklist mechanic. Extensions listed in /blacklists/[FILE]_ext_bl.txt are
    not exported. 

    Args:
        element (xml.etree.ElementTree.Element): An ElementTree element to parse.
        blacklis List : String array with blacklisted extensions

    Returns:
        dict: A dictionary containing the parsed XML data.

    Raises:
        Exception: If there is a parsing error.

    """
    result = {}

    # add tag metadata for certain tag types
    if element.tag == 'template_reference':
        result[element.tag] = {
            'name': get_attribute(element, "name"),
            'value': get_attribute(element, "value"),
        }

        if element.attrib.get("overrideParent", "").strip().lower() == "true":
            result[OVERRIDE_PARENT_META_KEY] = True
        
        ## check for blacklisting extensions -> don't export
        #extName = os.path.splitext(os.path.basename(result[element.tag]['value']))[0]
        extName = result[element.tag]['value']
        if extName in blacklist : 
            return None

    elif element.tag == 'locstring':
        result[element.tag] = {'name':get_attribute(element,"name"), 'value':get_attribute(element,"value")}
        
    if has_children(element):
        for child in element:
            if child.tag == "list":
                list_name = get_attribute(child, "name")

                result[list_name] = []

                list_meta = {}

                removed_ids = parse_removed_ids(child.attrib.get("removedIds"))
                if removed_ids:
                    list_meta["removed_ids"] = removed_ids

                if child.attrib.get("overrideParent", "").strip().lower() == "true":
                    list_meta[OVERRIDE_PARENT_META_KEY] = True

                if list_meta:
                    result[get_list_meta_key(list_name)] = list_meta

                for item in child:
                    item_name = get_attribute(item, "name")
                    parsed_item = parse_weapon_xml_data(item, blacklist)

                    if parsed_item is not None:
                        list_item = {
                            item_name: parsed_item,
                        }

                        item_meta = get_list_item_meta(item)
                        if item_meta:
                            list_item[LIST_ITEM_META_KEY] = item_meta

                        result[list_name].append(list_item)
            else:
                try:
                    value = parse_weapon_xml_data(child,blacklist)
                    if value is not None:
                        result[get_attribute(child,"name")] = value
                except Exception as e:
                    print(e)
                    pass

    else:
        # create marking key if the tag is instance_reference
        if element.tag == "instance_reference":
            formated_path = get_attribute(element,"value").replace("""\\""", """/""")   # using forward slashes!
            result[element.tag] = formated_path
        elif element.tag == "template_reference":
            pass # template_reference metadata already included in result!
        elif element.tag == 'locstring':
            pass # locstring metadata already included in result!
        elif element.tag == 'file':
            formated_path = get_attribute(element,"value").replace("""\\""", """/""")   # using forward slashes!
            result = formated_path 
        else:
            # else xml element doesn't have any children, return the value.
            # Normal leaf stat.
            # Missing value means "no override"; inheritance should keep the parent value.
            result = string_num(get_optional_value(element))

    return result



#######################################################################################################
# This is just for testing purposes
# if __name__ == "__main__":
#
#     # this script cwd
#     script_root_dir = os.path.abspath(os.getcwd())
#     # 2 levels up to the repository
#     source_xml_dir = os.path.abspath(os.path.join(
#         get_nth_level_parent(script_root_dir, 2), 'xml'))
#     # pathStr
#     print(source_xml_dir)
#
#     tommy_path_relative = "attrib/instances/weapon/american/small_arms/machine_gun/sub_machine_gun/thompson_ranger_us.xml";
#
#     weapon_file = os.path.join(source_xml_dir, tommy_path_relative)
#     #eapon_file = "C:/GIT/coh3-data/xml/attrib/instances/weapon/american/small_arms/machine_gun/sub_machine_gun/thompson_ranger_us.xml"
#     weapon_file = "C:/GIT/coh3-data/xml/attrib/instances/ebps/races/american/infantry/assault_engineer_us.xml"
#     print(weapon_file)
#
#     # load weapon_file xml
#     xmltree = ET.parse(weapon_file)
#     xmlroot = xmltree.getroot()
#     # get the default weapon variant(not the single player version!)
#     default_variant = xmlroot.findall("variant[@name='default']")[0]
#     weapon = parse_weapon_xml_data(default_variant)
#     weapon_json = json.dumps(weapon)
