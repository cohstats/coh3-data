import json
import os
import argparse
import re

def create_locstring_dictionary(ucs_file_path):
    """
    Reads a UCS file and creates a dictionary with locstring IDs as keys and text as values.
    The UCS file is tab-separated and UTF-16 encoded, with format:
    ID<tab>Text
    """
    locstring_dict = {}
    
    with open(ucs_file_path, 'r', encoding='UTF-16') as f:
        for line in f:
            # Skip empty lines
            if not line.strip():
                continue
                
            # Split on first tab only
            parts = line.strip().split('\t', 1)
            if len(parts) == 2:
                id_str, text = parts
                try:
                    # Convert ID to int for proper sorting
                    id_num = int(id_str)
                    locstring_dict[id_str] = text
                except ValueError:
                    continue  # Skip if ID is not a valid number
    
    # Sort dictionary by key (converting string keys to int for proper numerical sorting)
    sorted_dict = dict(sorted(locstring_dict.items(), key=lambda x: int(x[0])))
    
    return sorted_dict

def main():
    parser = argparse.ArgumentParser(description='Convert UCS file to locstring JSON')
    parser.add_argument('input', help='Path to input UCS file (e.g., anvil.en.ucs)')
    parser.add_argument('--output', '-o', 
                        help='Output JSON file path (default: data/<localecode>/locstring.json)',
                        default=None)

    args = parser.parse_args()

    # Extract locale code from input filename (e.g., "anvil.en.ucs" or "anvil.zh-hans.ucs")
    input_filename = os.path.basename(args.input)
    locale_pattern = re.search(r'\.([a-z]{2}(?:-[a-z]+)?)\.',  input_filename, re.IGNORECASE)
    locale_code = locale_pattern.group(1) if locale_pattern else 'en'

    # Set default output path if not specified
    if args.output is None:
        args.output = f'data/locales/{locale_code}-locstring.json'

    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    try:
        # Convert UCS to dictionary
        locstring_dict = create_locstring_dictionary(args.input)
        
        # Save to JSON
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(locstring_dict, f, ensure_ascii=False, indent=2)
            
        print(f'Successfully converted {args.input} to {args.output}')
        print(f'Total entries: {len(locstring_dict)}')
        
    except Exception as e:
        print(f'Error processing file: {str(e)}')
        exit(1)

if __name__ == '__main__':
    main()