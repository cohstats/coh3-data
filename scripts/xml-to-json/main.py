import os
import shutil
from scriptUtils import get_nth_level_parent
from weapons import parse_weapon_xml_data


# specify the source and destination directories
src_dir = 'in'
dest_dir = 'out'


# this script cwd
script_root_dir = os.path.abspath(os.getcwd())
# 2 levels up to the repository
source_xml_dir = os.path.abspath(os.path.join(get_nth_level_parent(script_root_dir, 2), 'xml'))

# browse the source directory recursively
for dirpath, dirnames, filenames in os.walk(src_dir):
    # create a corresponding destination directory
    dest_subdir = dirpath.replace(src_dir, dest_dir, 1)
    os.makedirs(dest_subdir, exist_ok=True)
    
    # copy all files in the current directory
    for filename in filenames:
        src_file = os.path.join(dirpath, filename)
        dest_file = os.path.join(dest_subdir, filename + '_copy')
        shutil.copy(src_file, dest_file)