import os
from scriptUtils import get_nth_level_parent, find_key_in_nested_dict, build_files_dictionary
from weapons import parse_weapon_xml_data


# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# 2 levels up to the repository
weapons_src_dir = os.path.abspath(os.path.join(get_nth_level_parent(
    script_root_dir, 2), 'xml/attrib/instances/weapon'))
print(f"weapons source dir: {weapons_src_dir}")
result = build_files_dictionary(weapons_src_dir, parse_weapon_xml_data)
weapons = find_key_in_nested_dict(result, "weapon")
print("retrieved weapon objects.")