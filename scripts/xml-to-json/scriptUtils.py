import os
import json
import xml.etree.ElementTree as ET

def string_num(input_string: str):
    """
    Convert a string to a float if possible, otherwise return the original string.

    Args:
        input_string (str): A string to be converted to a float.

    Returns:
        Union[float, str]: If inputString can be converted to a float, returns the float value.
        Otherwise, returns the original inputString.
    """
    try:
        return float(input_string)
    except ValueError:
        return input_string

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


def get_attribute(element: ET.Element, preferred_attribute: str = "value") -> str:
    """
    Returns the value or name of an XML element attribute, according to a preferred attribute.

    Args:
        element: An instance of the `ET.Element` class representing an XML element.
        preferred_attribute: A string specifying the preferred attribute to return. Possible values are:
            - "value": return the attribute value if it exists, otherwise return the attribute name.
            - "name": return the attribute name if it exists, otherwise return the attribute value.

    Returns:
        A string with the attribute value or name, or an empty string if the preferred attribute is not found
        and there is no fallback attribute to return.

    Raises:
        ValueError: if the `preferred_attribute` argument is not one of the allowed values.
    """
    if preferred_attribute not in ["value", "name"]:
        raise ValueError(f"Invalid value for preferred_attribute: {preferred_attribute}")

    if preferred_attribute == "value":
        if "value" in element.attrib:
            return element.attrib["value"]
        elif "name" in element.attrib:
            return element.attrib["name"]
    elif preferred_attribute == "name":
        if "name" in element.attrib:
            return element.attrib["name"]
        elif "value" in element.attrib:
            return element.attrib["value"]
        
    return ""


def has_children(element: ET.Element) -> bool:
    """
    Check if an XML element has any child elements.

    Args:
        element: An `Element` object from the `xml.etree.ElementTree` module.

    Returns:
        A boolean value indicating whether the element has any child elements.

    Raises:
        TypeError: If the input element is not an `Element` object.

    Example:
        >>> root = ET.fromstring('<root><child/></root>')
        >>> has_children(root)
        True
        >>> has_children(root.find('child'))
        False
    """
    if not isinstance(element, ET.Element):
        raise TypeError("Input element must be an Element object.")
    for children in element:
        return True
    return False

def find_key_in_nested_dict(dictionary, key, default=None):
    """
    Recursively searches a dictionary (including nested dictionaries) for the first occurrence
    of a key and returns its associated value.

    Args:
        dictionary: A dictionary (possibly with nested dictionaries) to search for the key.
        key: The key (possibly a nested key) to search for in the dictionary.
        default: The default value to return if the key is not found (defaults to None).

    Returns:
        The value associated with the first occurrence of the key in the dictionary (including
        nested dictionaries), or the default value if the key does not exist in the dictionary.
    """
    if key in dictionary:
        return dictionary[key]
    else:
        for value in dictionary.values():
            if isinstance(value, dict):
                result = find_key_in_nested_dict(value, key, default=default)
                if result is not None:
                    return result
    return default

def get_default_variant(file_path):
    """
    Parses an XML file at the given `file_path` and returns the `variant` element with a `name`
    attribute of "default".

    Args:
        file_path (str): A string representing the path to the XML file to be parsed.

    Returns:
        xml.etree.ElementTree.Element: The `variant` element with a `name` attribute of "default".

    Raises:
        IndexError: If no `variant` element with a `name` attribute of "default" is found.
    """
    xml_tree = ET.parse(file_path)
    xml_root = xml_tree.getroot()
    default_variant = xml_root.findall("variant[@name='default']")[0]
    return default_variant


def build_files_dictionary(directory, parse_func):
    """
    Builds a nested dictionary from a directory containing files by recursively walking through the directory 
    and parsing each file using the provided parse function.
    
    Args:
        directory (str): The path to the directory to build the dictionary from.
    
        parse_func (function): A function to parse the current file with. Input is xml element tree. Outputs dictionary.
    
    Returns:
        dict: A nested dictionary representing the files and folders in the directory. 
        The keys of the dictionary are the names of files and folders, and the values are either sub-dictionaries 
        for folders or the parsed representation of the file for files.
    """

    files_dict = {}
    for root, dirs, files in os.walk(directory):
        current_dict = files_dict
        path = root.split(os.sep)
        for i in range(len(path)):
            folder = path[i]
            if folder not in current_dict:
                current_dict[folder] = {}
            current_dict = current_dict[folder]
        for file in files:
            file_path = os.path.join(root, file)
            filename = os.path.splitext(os.path.basename(file_path))[0]
            # get the default variant(not the single player version!)
            default_variant = get_default_variant(file_path)
            current_dict[filename] = parse_func(default_variant)
    return files_dict


def save_dict_to_json(dictionary, path, file_name, indent=4):
    """
    Saves a dictionary as JSON to a specified path with a specified file name.
    
    Args:
        dictionary (dict): The dictionary to save as JSON.
        path (str): The path where the JSON file will be saved.
        file_name (str): The name of the JSON file.
        indent (int): The number of spaces to use for indentation (default is 4).
    
    Returns:
        None
    """
    # create directory if it does not exist
    if not os.path.exists(path):
        os.makedirs(path)
        
    # construct the full file path
    file_path = os.path.join(path, file_name)
    
    # write the dictionary as formatted JSON to file
    with open(file_path, 'w') as json_file:
        json.dump(dictionary, json_file, indent=indent)




