import os
from scriptUtils import get_nth_level_parent, build_files_dictionary, save_dict_to_json, get_path_as_string, resolve_dict_value_by_path, create_locstring_dictionary
from weapons import parse_weapon_xml_data

CONST_EXPORT_DIR = 'tempexported'   # this is gitignored
CONST_EXPORT_DIR = 'exported'       # this is not gitignored

print('Parsing xml to json...')
# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# xml data source folder
xml_data_dir = os.path.abspath(os.path.join(get_nth_level_parent(script_root_dir, 2), 'xml'))



# create locstring dictionary
locstring_path = os.path.abspath(os.path.join(xml_data_dir, 'loc_english\locale.txt'))
locstring = create_locstring_dictionary(locstring_path)
# export to json
locstring_export_path = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
save_dict_to_json(locstring, locstring_export_path, "locstring.json")


# navigate to weapon XMLs and build a dictionary
weapons_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\weapon'))
result = build_files_dictionary(weapons_src_dir, parse_weapon_xml_data)
weapons = resolve_dict_value_by_path(result, get_path_as_string(weapons_src_dir))
# export to json
exported_weapons_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
save_dict_to_json(weapons, exported_weapons_dir, "weapon.json")



# navigate to ebps XMLs and build a dictionary
ebps_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\ebps'))
result = build_files_dictionary(ebps_src_dir, parse_weapon_xml_data)
ebps = resolve_dict_value_by_path(result, get_path_as_string(ebps_src_dir))
# export to json
exported_ebps_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
save_dict_to_json(ebps, exported_ebps_dir, "ebps.json")



# navigate to sbps XMLs and build a dictionary
sbps_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\sbps'))
result = build_files_dictionary(sbps_src_dir, parse_weapon_xml_data)
sbps = resolve_dict_value_by_path(result, get_path_as_string(sbps_src_dir))
# export to json
exported_sbps_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
save_dict_to_json(sbps, exported_sbps_dir, "sbps.json")

# navigate to upgrade XMLs and build a dictionary
upgrade_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\\upgrade'))
result = build_files_dictionary(upgrade_src_dir, parse_weapon_xml_data)
upgrade = resolve_dict_value_by_path(result, get_path_as_string(upgrade_src_dir))
# export to json
exported_upgrade_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
save_dict_to_json(upgrade, exported_upgrade_dir, "upgrade.json")

# Use a function to easily spot each xml-to-json execution.
def exportBattlegroups():
    print('## Started processing battlegroups....')
    # Navigate to tech_tree/battlegroup XMLs and build a dictionary. We do not need the campaign ones.
    battlegroup_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\\tech_tree\\battlegroup'))
    result = build_files_dictionary(battlegroup_src_dir, parse_weapon_xml_data)
    battlegroup = resolve_dict_value_by_path(result, get_path_as_string(battlegroup_src_dir))
    # export to json
    exported_battlegroup_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
    save_dict_to_json(battlegroup, exported_battlegroup_dir, "battlegroup.json")
    print('## Finished processing battlegroups....')

def exportAbilities():
    print('## Started processing abilities....')
    # Navigate to tech_tree/battlegroup XMLs and build a dictionary. We do not need the campaign ones.
    abilities_src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib\instances\\abilities'))
    result = build_files_dictionary(abilities_src_dir, parse_weapon_xml_data)
    abilities = resolve_dict_value_by_path(result, get_path_as_string(abilities_src_dir))
    # export to json
    exported_abilities_dir = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
    save_dict_to_json(abilities, exported_abilities_dir, "abilities.json")
    print('## Finished processing abilities....')


exportBattlegroups()
exportAbilities()

print('Parsing done. View this folder for results: \n"'+ get_path_as_string(script_root_dir)+f'\{CONST_EXPORT_DIR}"')