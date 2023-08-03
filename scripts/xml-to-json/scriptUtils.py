import os
import json
import xml.etree.ElementTree as ET
import copy
import re
import sys

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

    Blacklist mechanic has been added to filter out folders and extension that are not required. Blacklists are saved
    under /blacklists/[ROOT_FOLDER]_bl.txt for folder blacklists (eg. /blacklists/ebps_bl.txt ) and 
    /blacklists/[ROOT_FOLDER]_ext_bl.txt for extension blacklists. 
    
    Args:
        directory (str): The path to the directory to build the dictionary from.
    
        parse_func (function): A function to parse the current file with. Input is xml element tree. Outputs dictionary.
    
    Returns:
        dict: A nested dictionary representing the files and folders in the directory. 
        The keys of the dictionary are the names of files and folders, and the values are either sub-dictionaries 
        for folders or the parsed representation of the file for files.
    """
    skip_blackllist = False

    # receive blacklists
    if len(sys.argv) > 1 and '-no_bl' in sys.argv:
        skip_blackllist = True

    blacklist = []
    blacklist_ext = []
    if not skip_blackllist:
        ## xml folder must be 2 level upwards in the folder hierarchy = project root
        blacklist_dir = os.path.dirname(os.path.abspath(__file__+"/../../"))
        blacklist_dir = os.path.join(blacklist_dir, 'blacklists')
        print("- Using blacklist from "+blacklist_dir)
        blacklist = getBlacklist(os.path.join(blacklist_dir,os.path.splitext(os.path.basename(directory))[0])+'_bl.txt')
        blacklist_ext = getBlacklist(os.path.join(blacklist_dir,os.path.splitext(os.path.basename(directory))[0])+'_ext_bl.txt')
    
    files_dict = {}
    for root, dirs, files in os.walk(directory):

        ## check if root is blacklisted
        if len(blacklist) > 0 and isBlacklisted(root,directory,blacklist):
            continue

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
            current_dict[filename] = parse_func(default_variant,blacklist_ext)

    return files_dict


def getBlacklist(path) :
    """
    Reads the corresponding blacklist file and returns an array with expressions
    
    Args:
        path (str): The path to the blacklilst file
    
    
    Returns:
        a string array containing all expressions of the blackllist
    """
    if not os.path.isfile(path):
        return []

    with open(path) as file:
        lines = file.read().splitlines()
    file.close()

    return lines


def isBlacklisted(path:str,directory:str,  blacklist):
    """
    Checks if folder path is blacklisted. 
    
    Args:
        path (str): The path to be checked
        dictonary (str): Path to root folder for concrete blueprint (eg. ebps)
        blacklist List: the blacklist array of strings (expressions) to be checked against
    
    Returns:
        true if path is in checklist
    """
    # convert to relative path of directory
    relative_path = path.replace(directory,'')

    for expr in blacklist:
        if expr != '' and re.search(expr, relative_path) :
            return True
    return False

def mod_overwrite(dic_root , mod_path:str, parser ):
    """
    Overwrites original data by data extracted from 
    mod. 
    
    Args:
        dic_root target dictionary
        mod_dic overwriting dictionary
        parser custom xml parser
    
    Returns:
        dic_root - Resolved dictionary including overwritten values
    """  
    mod_dic = build_files_dictionary(mod_path,parser)
    mod_overwrite_traverse(dic_root,mod_dic)
    return dic_root

def mod_overwrite_traverse(dic_root,mod_dic, path = ""):
    """
    Navigates through mod dictionary and overwrites to 
    identify all elements that need to overwrite
    
    Args:
        dic_root target dictionary
        mod_dic overwriting instance
        path of overwriting instance
    
    Returns:
        dic_root - Resolved dictionary including overwritten values
    """  
    if('pbgid' in mod_dic):
        return mod_overwrite_by_path(dic_root,mod_dic,path)
    
    # No overwrite, keep going searching
    for prop in mod_dic:
        path_new = path + prop + '/'
        dic_root = mod_overwrite_traverse(dic_root,mod_dic[prop],path_new)


    return dic_root


def mod_overwrite_by_path(dic_root,mod_dic, path:str, common_root = False):
    """
    Navigates to a given path of the dictory and overwrites the last
    path element as property by the given mod_dic dictionary/file. 
    
    Args:
        dic_root    to be navigated and overwritten
        mod_dic     overwriting instance
        common_root indicates if traversal begins from a common
                    root folder
    
    Returns:
        dic_root - Resolved dictionary including overwritten values
    """ 
       
    pathArray = path.split('/')
    pathFirst = pathArray[0]
    pathLast = pathArray[len(pathArray)-2]
    pathNext = path.replace(pathFirst+'/','')

    # # traverse the first parent folder until we find the attrib folder
    # # to have the same starting point as the original dictionary
    if not common_root:
        if 'attrib' not in dic_root and pathFirst != 'attrib':
            for prop in dic_root:
                dic_root[prop] = mod_overwrite_by_path(dic_root[prop],mod_dic,pathNext )
            return dic_root
        elif 'attrib' not in dic_root and pathFirst == 'attrib':
            for prop in dic_root:
                dic_root[prop] = mod_overwrite_by_path(dic_root[prop],mod_dic,path )
            return dic_root
        elif 'attrib' in dic_root and pathFirst != 'attrib':
            dic_root = mod_overwrite_by_path(dic_root,mod_dic,pathNext )
            return dic_root
        else: common_root = True

    if(pathFirst == pathLast): 
        if( pathFirst in dic_root ):
            dic_root[pathFirst] = resolve_inheritance_node(dic_root[pathFirst],mod_dic)
        else: 
            dic_root[pathFirst] = mod_dic
        return dic_root
    
    if pathFirst in dic_root: 
        dic_root[pathFirst] = mod_overwrite_by_path(dic_root[pathFirst],mod_dic, pathNext,True )
        return dic_root

    
    # for prop in dic_root:
    #     dic_root[prop] = mod_overwrite(dic_root[prop],mod_dic,pathNext)

    return dic_root


def resolve_inheritance_dic(dic_current_node, dic_root): 
    """
    Resolves inheritance for given blueprint dictionary recursively
    
    Args:
        dic_current_node Dict: the current node to be checked 
        dic_root Dict: the complete dictionary to find parents
    
    Returns:
        Dict - Resolved dictionary including inherited values
    """ 


    # recursively find and process all nodes that use inheritance
    if dic_current_node is None:
        return None

    ## check if node can inherit
    if  'parent_pbg' in dic_current_node :

        ## get reference 
        reference = dic_current_node['parent_pbg']['instance_reference']

        ## check if reference exists
        if(reference is None or reference == ""):
            return dic_current_node
        
        ## get name of reference parent
        key = os.path.splitext(os.path.basename(reference))[0]

        # find inheritance parent
        parent = find_key_in_nested_dict(dic_root,key)

        if parent is None :
            print("Info: Inheritance reference "+reference+" not resolved. Probably blacklisted.")
            return dic_current_node

        # resolve inheritance for parent itself
        parent = resolve_inheritance_dic(parent,dic_root)

        parent_clone = copy.deepcopy(parent)

        return resolve_inheritance_node(parent_clone,dic_current_node)
 
    else: 
        for child in dic_current_node:
           if type(dic_current_node[child]) is dict:
                dic_current_node[child] = resolve_inheritance_dic(dic_current_node[child],dic_root)

    return dic_current_node


def resolve_inheritance_node(base,overwrite):

    """
    Resolves inheritance for given node
    
    Args:
        base Dict:       the base node containing all values from parent
        overwrite Dict:  the overwriting node 
    
    Returns:
        Dict - Resolved dictionary including inherited values
    """ 


    
    if overwrite is None:
        return base
    
    if type(base) is not dict:
        return overwrite 
    
    # Convention: If parent node is a dict and overwrite is a string
    # parent node is overwriting
    if type (overwrite) is str: 
        return base
    
    for prop in overwrite:

        if prop not in base:
            base[prop] = overwrite[prop]
            continue

        if prop == 'extensions':
            base[prop] = resolve_extensions(base[prop],overwrite[prop])
            continue

        if type(overwrite[prop]) is list:
            base[prop] = resolve_list(base[prop],overwrite[prop])
            continue

        base[prop] = resolve_inheritance_node(base[prop],overwrite[prop])


        # node can inherit
    return base


def resolve_extensions(base,overwrite):
    """
    Resolves inheritance for extensions (Special case)
    
    Args:
        base Dict:       the base node containing all values from parent
        overwrite Dict:  the overwriting node 
    
    Returns:
        Dict - Resolved dictionary including inherited values
    """ 

    for i in range(len(overwrite)):
        found =False
        keyOwr =list(overwrite[i].keys())[0] 
        for j in range(len(base)):
            keyBase =list(base[j].keys())[0] 
            if overwrite[i][keyOwr]['template_reference']['value'] == base[j][keyBase]['template_reference']['value']:
                base[j] = resolve_inheritance_node(base[j],overwrite[i]) 
                found = True
                break
        if found == False:  
            base.append(overwrite[i])
    
    return base

def resolve_list(base,overwrite):
    """
    Resolves inheritance for lists 
    
    Args:
        base Dict:       the base node containing all values from parent
        overwrite Dict:  the overwriting node 
    
    Returns:
        Dict - Resolved dictionary including inherited values
    """ 
    for i in range(len(overwrite)):
        if i >= len(base) :
            base.append(overwrite[i])
            continue
        base[i] = resolve_inheritance_node(base[i],overwrite[i]) 

    return base
    

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
    json_file.close()

    # json_str = json.dumps(dictionary)
    # json_str = str(zlib.compress(json_str.encode()))
    # # write the dictionary as formatted JSON to file
    # with open(file_path+"_c", 'w') as compressed_file:
    #     compressed_file.write(json_str)
    # compressed_file.close()






def resolve_dict_value_by_path(obj, path, separator="\\"):
    """
    Traverse a nested dictionary to get the value of a specific path.

    Args:
        obj (dict): The dictionary to traverse.
        path (str): The path of the value to retrieve. The path should be
            a string of property names separated by the separator.
        separator (str, optional): The separator used to split the path.
            Defaults to '\'.

    Returns:
        The value of the property at the specified path.
    """
    # Split the path into an array of property names
    props = path.split(separator)

    # Traverse the object to get the nested value
    value = obj
    for prop in props:
        value = value[prop]

    return value

def get_path_as_string(path, separator='\\'):
    """
    Takes an os.path input and returns the path as a string with a specified separator.
    Args:
        path (str): The path to be formatted.
        separator (str, optional): The separator to use in the returned path. Default is '\'.
    Returns:
        str: The formatted path with the specified separator.
    """
    return path.replace(os.path.sep, separator)



def create_locstring_dictionary(file_path, encode="utf-8"):
    """
    Reads a tab-separated file and returns a dictionary with the last field
    as the value and the second-to-last field after the '$' symbol as the key.
    If there are only four fields in a line, the value is None.
    If there are more than five fields, the line is ignored.

    Args:
        file_path (str): The path to the file to be read.
        encode (str): File encoding

    Returns:
        dict: A dictionary with the extracted values.

    Raises:
        FileNotFoundError: If the specified file does not exist.

    """
    dictionary = {}
    with open(file_path, "r", encoding=encode) as file:
        for line in file:
                
                fields = line.strip().split("\t")
                if len(fields) == 5:
                    number = fields[-2].split("$")[-1]
                    value = fields[-1]
                    dictionary[number] = value

                elif len(fields) == 4:
                    number = fields[-1].split("$")[-1]
                    value = None
                    dictionary[number] = value

                else:
                    print(f'Unable to parse:\n{line}')

    # Sort the dictionary by key (the locstring id).
    sorted_dictionary = dict(sorted(dictionary.items(), key=lambda x: int(x[0])))

    return sorted_dictionary