import os
from scriptUtils import get_nth_level_parent, find_key_in_nested_dict, build_files_dictionary, save_dict_to_json
from weapons import parse_weapon_xml_data


# this script cwd
script_root_dir = os.path.abspath(os.getcwd())

# navigate to weapon XMLs and build a dictionary
weapons_src_dir = os.path.abspath(os.path.join(get_nth_level_parent(script_root_dir, 2), 'xml/attrib/instances/weapon'))
exported_weapons_dir = os.path.join(script_root_dir, "exported/weapons")
result = build_files_dictionary(weapons_src_dir, parse_weapon_xml_data)
weapons = find_key_in_nested_dict(result, "weapon")
save_dict_to_json(weapons, exported_weapons_dir, "weapons.json")
