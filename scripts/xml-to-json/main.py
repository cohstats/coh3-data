import os
from scriptUtils import mod_overwrite, resolve_inheritance_dic, get_nth_level_parent, build_files_dictionary, \
    save_dict_to_json, get_path_as_string, resolve_dict_value_by_path, create_locstring_dictionary
from weapons import parse_weapon_xml_data
import sys
import concurrent.futures
import time

# Program parameter : -no_bl = no blacklist
#CONST_EXPORT_DIR = 'tempexported'  # this is gitignored
CONST_EXPORT_DIR = 'data'  # this is not gitignored

# xml folder must be 2 level upwards in the folder hierarchy
PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/../.."))


def export_by_type(type: str, prefix="", script_root_dir="", xml_data_dir="", const_export_dir=""):
    output = []  # List to collect the print outputs

    output.append('## Started processing ' + type + '....')
    src_dir = os.path.abspath(os.path.join(xml_data_dir, 'attrib', 'instances', prefix + type))
    result = build_files_dictionary(src_dir, parse_weapon_xml_data)

    if len(sys.argv) < 1 or '-no_mod' not in sys.argv:
        output.append('- Mod fix overwrite...')
        mod_dir = os.path.abspath(
            os.path.join(xml_data_dir, 'coh3-state-tree-fix', 'assets', 'attrib', 'instances', prefix + type))
        result = mod_overwrite(result, mod_dir, parse_weapon_xml_data)

    output.append('- Resolving inheritance....')
    result = resolve_inheritance_dic(result, result)
    resolved_dic = resolve_dict_value_by_path(result, get_path_as_string(src_dir))

    output.append('- Writing to file....')
    exported_dir = os.path.join(script_root_dir, f'{const_export_dir}')
    save_dict_to_json(resolved_dic, exported_dir, type + ".json")

    output.append(' ')
    output.append(f'Successfully processed {type}')

    # Print all the outputs at once
    print('\n'.join(output))
    return f'Successfully processed {type}'


def main():
    # Get the start time
    start_time = time.time()
    print('Parsing xml to json...')
    # this script cwd
    # script_root_dir = os.path.abspath(os.getcwd())

    script_root_dir = PROJECT_ROOT_DIR
    print('## Root dir ' + script_root_dir)
    # xml data source folder

    xml_data_dir = os.path.abspath(os.path.join(script_root_dir, 'xml'))

    print('## Started processing locale....')
    # create locstring dictionary
    loc_string_path = os.path.abspath(os.path.join(xml_data_dir, 'loc_english', 'locale.txt'))
    loc_string = create_locstring_dictionary(loc_string_path)
    # export to json
    loc_string_export_path = os.path.join(script_root_dir, f'{CONST_EXPORT_DIR}')
    save_dict_to_json(loc_string, loc_string_export_path, "locstring.json")
    print(' ')

    # exportByType('ebps')
    # exportByType('sbps')
    # exportByType('weapon')
    # exportByType('upgrade')
    # exportByType('battlegroup','tech_tree\\')
    # exportByType('abilities')
    # exportByType('daily_challenges_store_release','challenges\\challenge\\')
    # exportByType('weekly_challenges_store_release','challenges\\challenge\\')

    # Define the types and prefixes to be processed
    types_and_prefixes = [
        ('ebps', ''),
        ('sbps', ''),
        ('weapon', ''),
        ('upgrade', ''),
        ('battlegroup', 'tech_tree\\'),
        ('abilities', ''),
        ('daily_challenges_store_release', 'challenges\\challenge\\'),
        ('weekly_challenges_store_release', 'challenges\\challenge\\')
    ]

    futures = []

    # Create a ThreadPoolExecutor
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Use list comprehension to start the tasks and collect the Future objects
        futures = [executor.submit(export_by_type, type, prefix, script_root_dir, xml_data_dir, CONST_EXPORT_DIR) for
                   type, prefix in types_and_prefixes]


    # Wait for all tasks to complete
    for future in concurrent.futures.as_completed(futures):
        print(f"Task completed: {future.result()}")
   
    print('Parsing done. View this folder for results: \n"' + get_path_as_string(
        script_root_dir) + f'\{CONST_EXPORT_DIR}"')
    print(f"Execution time: {round(time.time() - start_time, 1)} seconds")


if __name__ == '__main__':
    main()
