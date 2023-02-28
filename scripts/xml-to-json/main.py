import os
from scriptUtils import get_nth_level_parent, build_files_dictionary, save_dict_to_json, get_path_as_string, resolve_dict_value_by_path
from weapons import parse_weapon_xml_data

CONST_EXPORT_DIR = 'tempexported'   # this is gitignored
CONST_EXPORT_DIR = 'exported'       # this is not gitignored

print('Parsing xml to json...')
# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# xml data source folder
xml_data_dir = os.path.abspath(os.path.join(get_nth_level_parent(script_root_dir, 2), 'xml'))

# navigate to weapon XMLs and build a dictionary
weapons_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\weapon'))
result = build_files_dictionary(weapons_src_dir, parse_weapon_xml_data)
weapons = resolve_dict_value_by_path(result, get_path_as_string(weapons_src_dir))

# export to json
exported_weapons_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}\weapon')
save_dict_to_json(weapons, exported_weapons_dir, "weapon.json")

print('Parsing done. View this folder for results: \n"'+ get_path_as_string(script_root_dir)+f'\{CONST_EXPORT_DIR}"')