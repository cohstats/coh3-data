import os
import json
import xml.etree.ElementTree as ET


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

def create_dict_from_xml_elements(xml_nodes : ET.Element, attribute_key : str, attribute_value: str) -> dict:
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
            dict_data[node.attrib[attribute_key]] = node.attrib[attribute_value]
        except:
            pass
    return dict_data

def parse_group_element(elem):
    """
    Parse a group XML element and return a dictionary.
    """
    result = {}
    for child in elem:
        if child.tag == "group":
            result[child.attrib["name"]] = parse_group_element(child)
        else:          
            try:
                result[child.attrib["name"]] = child.attrib['value']
            except:
                pass
    return result


# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# 2 levels up to the repository
source_xml_dir = os.path.abspath(os.path.join(get_nth_level_parent(script_root_dir,2), 'xml'))
#pathStr
weapon_file = "C:/GIT/coh3-data/xml/attrib/instances/weapon/american/small_arms/machine_gun/sub_machine_gun/thompson_ranger_us.xml"


# load weapon_file xml
xmltree = ET.parse(weapon_file)
xmlroot = xmltree.getroot()
# get the default weapon variant(not the single player version!)
default_variant = xmlroot.findall("variant[@name='default']")[0];
weapon = parse_group_element(default_variant)
weapon_json = json.dumps(weapon)


