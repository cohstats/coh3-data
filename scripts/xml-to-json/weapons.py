import os
import json
import xml.etree.ElementTree as ET
from scriptUtils import get_nth_level_parent, get_attribute, has_children, string_num




def parse_weapon_xml_data(element: ET.Element) -> dict:
    """Parses XML data from a given ElementTree element and returns a dictionary.

    Args:
        element (xml.etree.ElementTree.Element): An ElementTree element to parse.

    Returns:
        dict: A dictionary containing the parsed XML data.

    Raises:
        Exception: If there is a parsing error.

    """
    result = {}

    # add tag metadata for certain tag types
    if element.tag == 'template_reference':
        result[element.tag] = {'name':get_attribute(element,"name"), 'value':get_attribute(element,"value")}
    elif element.tag == 'locstring':
        result[element.tag] = {'name':get_attribute(element,"name"), 'value':get_attribute(element,"value")}
        
    if has_children(element):
        for child in element:
            if child.tag == "list":
                # create a list
                result[child.attrib["name"]] = []
                # for all children of a list node
                for item in child:
                    listItem = {}
                    listItem[get_attribute(item,"name")] = parse_weapon_xml_data(item)
                    result[get_attribute(child,"name")].append(listItem)
            else:
                try:
                    result[get_attribute(child,"name")] = parse_weapon_xml_data(child)
                except Exception as e:
                    print(e)
                    pass

    else:
        # create marking key if the tag is instance_reference
        if element.tag == "instance_reference":
            result[element.tag] = string_num(get_attribute(element,"value"))
        elif element.tag == "template_reference":
            pass # template_reference metadata already included in result!
        elif element.tag == 'locstring':
            pass # locstring metadata already included in result!
        else:
            # else xml element doesn't have any children, return the value.
            result = string_num(get_attribute(element,"value"))

    return result



#######################################################################################################
if __name__ == "__main__":

    # this script cwd
    script_root_dir = os.path.abspath(os.getcwd())
    # 2 levels up to the repository
    source_xml_dir = os.path.abspath(os.path.join(
        get_nth_level_parent(script_root_dir, 2), 'xml'))
    # pathStr
    print(source_xml_dir)
    
    tommy_path_relative = "attrib/instances/weapon/american/small_arms/machine_gun/sub_machine_gun/thompson_ranger_us.xml";
    
    weapon_file = os.path.join(source_xml_dir, tommy_path_relative)
    #eapon_file = "C:/GIT/coh3-data/xml/attrib/instances/weapon/american/small_arms/machine_gun/sub_machine_gun/thompson_ranger_us.xml"
    weapon_file = "C:/GIT/coh3-data/xml/attrib/instances/ebps/races/american/infantry/assault_engineer_us.xml"
    print(weapon_file)
    
    # load weapon_file xml
    xmltree = ET.parse(weapon_file)
    xmlroot = xmltree.getroot()
    # get the default weapon variant(not the single player version!)
    default_variant = xmlroot.findall("variant[@name='default']")[0]
    weapon = parse_weapon_xml_data(default_variant)
    weapon_json = json.dumps(weapon)
