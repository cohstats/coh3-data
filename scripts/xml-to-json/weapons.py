import os
import json
import xml.etree.ElementTree as ET
from typing import Literal

_PREFERRED_ATTRIBUTE = Literal["value", "name"]

def get_nth_level_parent(current_dir: str, n: int) -> str:
    """
    Get the absolute path of the n-th level parent directory of the given directory path.

    Args:
        current_dir (str): The absolute path of the current directory.
        n (int): The number of levels to navigate up the directory hierarchy.

    Returns:
        str: The absolute path of the resulting directory path after navigating up `n` levels.

    Raises:
        ValueError: If `n` is negative.

    """
    # Ensure n is not negative
    if n < 0:
        raise ValueError("n cannot be negative")

    # Navigate up n levels from the current directory
    for i in range(n):
        current_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

    # Return the absolute path of the resulting directory path
    return current_dir


def create_dict_from_xml_elements(xml_nodes: ET.Element, attribute_key: str, attribute_value: str) -> dict:
    """
    Extracts the values of the given attribute names from each node in an XML element tree, and returns a dictionary with attribute_key as the keys and attribute_value as the values.

    Args:
    xml_nodes (xml.etree.ElementTree.Element): An XML element tree to extract data from.
    attribute_key (str): A string representing the attribute name to be used as keys in the resulting dictionary.
    attribute_value (str): A string representing the attribute name to be used as values in the resulting dictionary.

    Returns:
    dict: A dictionary with attribute_key as the keys and attribute_value as the values for each node in the element tree.

    """
    dict_data = {}
    for node in xml_nodes:
        try:
            dict_data[node.attrib[attribute_key]
                      ] = node.attrib[attribute_value]
        except:
            pass
    return dict_data


def get_attribute(element: ET.Element, preffered_ : _PREFERRED_ATTRIBUTE = "value"):

    # prefered value, fallback to name
    if preffered_ == "value":
        if "value" in element.attrib:
            return element.attrib['value']
        elif "name" in element.attrib:
            return element.attrib['name']
        else:
            return "err_unknown_attrib"
      
    # prefered name, fallback to value  
    elif preffered_ == "name":
        if "name" in element.attrib:
            return element.attrib['name']
        elif "value" in element.attrib:
            return element.attrib['value'] 
        else:
            return "err_unknown_attrib"
    # uknown
    else:
        return "err_unknown_attrib"



def hasChildren(element: ET.Element):
    for child in element:
        return True
    return False


def parse_group_element(element: ET.Element):
    """
    Parse a group XML element and return a dictionary.
    """
    result = {}

    if hasChildren(element):
        for child in element:
            if child.tag == "list":
                # create a list
                result[child.attrib["name"]] = []
                # for all children of a list node
                for item in child:
                    listItem = {}
                    listItem[get_attribute(item,"name")] = parse_group_element(item)
                    result[get_attribute(child,"name")].append(listItem)
            else:
                try:
                    result[get_attribute(child,"name")] = parse_group_element(child)
                except:
                    print("parsing error")
                    pass

    else:
        # else xml element doesn't have any children, return the value.
        result = get_attribute(element,"value")

    return result



#######################################################################################################


# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# 2 levels up to the repository
source_xml_dir = os.path.abspath(os.path.join(
    get_nth_level_parent(script_root_dir, 2), 'xml'))
# pathStr
weapon_file = "C:/GIT/coh3-data/xml/attrib/instances/weapon/american/small_arms/machine_gun/sub_machine_gun/thompson_ranger_us.xml"
#weapon_file = "C:/GIT/coh3-data/xml/attrib/instances/ebps/races/american/infantry/assault_engineer_us.xml"


# load weapon_file xml
xmltree = ET.parse(weapon_file)
xmlroot = xmltree.getroot()
# get the default weapon variant(not the single player version!)
default_variant = xmlroot.findall("variant[@name='default']")[0]
weapon = parse_group_element(default_variant)
weapon_json = json.dumps(weapon)
