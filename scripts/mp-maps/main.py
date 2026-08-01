"""
Generates `data/mp-maps.json` from the multiplayer scenarios shipped in
`<game>/anvil/archives/ScenariosMP.sga`.

The archive is unpacked with AOEMods.Essence.CLI (`sga-unpack`) - the same tool the
workflow already uses for `ReferenceAttributes.sga` - and every scenario's `.info`
file is parsed for its name, size, player slots and resource point layout. Resource
income rates are looked up in `data/ebps.json` rather than hardcoded.

Typical use, with the game installed locally:

    python scripts/mp-maps/main.py --game-path "D:\\SteamLibrary\\steamapps\\common\\Company of Heroes 3"

If the scenarios are already unpacked somewhere, skip the unpack step:

    python scripts/mp-maps/main.py --scenarios-dir <unpacked>/scenarios/multiplayer
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from lua_info_parser import LuaInfoParseError, parse_info_file
from map_utils import (
    KIND_STARTING_POSITION,
    classify_point,
    load_ebps_index,
    load_locstrings,
    playable_bounds,
    resolve_locstring,
    summarize_points,
    summarize_slots,
    team_layout,
)

PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/../.."))

SCENARIOS_ARCHIVE = os.path.join('anvil', 'archives', 'ScenariosMP.sga')
DEFAULT_ESSENCE_CLI = os.path.join(
    PROJECT_ROOT_DIR, 'tools', 'AOEMods.Essence', 'AOEMods.Essence.CLI.exe'
)
DEFAULT_LOCSTRING = os.path.join(PROJECT_ROOT_DIR, 'data', 'locales', 'en-locstring.json')
DEFAULT_EBPS = os.path.join(PROJECT_ROOT_DIR, 'data', 'ebps.json')
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT_DIR, 'data', 'mp-maps.json')

# Unpack inside the project (gitignored), NOT into the system temp directory.
# On GitHub Windows runners the workspace lives on the fast local SSD (D:) while the
# system temp directory is on the slow OS disk (C:): unpacking this 1 GB archive to
# C: took over 105 minutes and never finished, versus ~5 minutes on D:.
DEFAULT_UNPACK_DIR = os.path.join(PROJECT_ROOT_DIR, 'scenarios')

SCHEMA_VERSION = 1

# Scenarios that are not playable multiplayer maps. `hoff` is the co-op "Hold Off"
# mode; scenario_type 0 covers the cinematic `*_video` and `*_defend_01` scenarios.
CATEGORY_MP = 'mp'
CATEGORY_HOFF = 'hoff'
CATEGORY_TEST = 'test'

MAP_ORIGIN_COMMUNITY = 2


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate data/mp-maps.json from ScenariosMP.sga'
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        '--game-path',
        help='Company of Heroes 3 install directory; the ScenariosMP.sga path is derived from it',
    )
    source.add_argument('--sga', help='Path to ScenariosMP.sga')
    source.add_argument(
        '--scenarios-dir',
        help='Path to an already unpacked scenarios directory (skips sga-unpack)',
    )

    parser.add_argument(
        '--essence-cli',
        default=DEFAULT_ESSENCE_CLI,
        help=f'Path to AOEMods.Essence.CLI.exe (default: {DEFAULT_ESSENCE_CLI})',
    )
    parser.add_argument(
        '--unpack-dir',
        default=DEFAULT_UNPACK_DIR,
        help='Where to unpack the archive; removed afterwards if the script created it '
             f'(default: {DEFAULT_UNPACK_DIR}). Keep this on a fast local disk - see the '
             'note in the source about GitHub runners.',
    )
    parser.add_argument(
        '--keep-unpacked',
        action='store_true',
        help='Do not delete the unpacked archive when finished',
    )
    parser.add_argument(
        '--locstring',
        default=DEFAULT_LOCSTRING,
        help='English locstring source: a *-locstring.json or a raw anvil.en.ucs',
    )
    parser.add_argument('--ebps', default=DEFAULT_EBPS, help='Path to data/ebps.json')
    parser.add_argument('--output', default=DEFAULT_OUTPUT, help='Output JSON path')
    parser.add_argument(
        '--min-maps',
        type=int,
        default=60,
        help='Fail if fewer than this many scenarios were found (guards against a silent extraction failure)',
    )
    parser.add_argument(
        '--include-test',
        action='store_true',
        help='Also export cinematic/test scenarios, which are excluded by default',
    )
    parser.add_argument(
        '--dump-info-dir',
        help='Also copy the raw .info files here, for debugging',
    )

    return parser.parse_args()


def unpack_archive(sga_path, essence_cli, output_dir):
    """Runs `AOEMods.Essence.CLI.exe sga-unpack` and returns the output directory."""
    if not os.path.isfile(sga_path):
        raise FileNotFoundError(f'Archive not found: {sga_path}')
    if not os.path.isfile(essence_cli):
        raise FileNotFoundError(
            f'AOEMods.Essence.CLI.exe not found: {essence_cli}\n'
            'Unzip tools/AOEMods.Essence-0.7.0.zip or pass --essence-cli.'
        )

    os.makedirs(output_dir, exist_ok=True)

    archive_size = os.path.getsize(sga_path) / (1024 ** 3)
    free = shutil.disk_usage(output_dir).free / (1024 ** 3)
    print(f'## Unpacking {sga_path} ({archive_size:.1f} GB)')
    print(f'   into {os.path.abspath(output_dir)} ({free:.1f} GB free)')
    print('   expect roughly 4 GB of output and a few minutes; if this takes much longer, '
          'the target is probably not on a fast local disk')

    if free < 6:
        print(f'   warning: only {free:.1f} GB free, the unpack needs about 4 GB')

    started = time.time()
    result = subprocess.run(
        [essence_cli, 'sga-unpack', sga_path, output_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        errors='replace',
    )

    if result.returncode != 0:
        print(result.stdout)
        raise RuntimeError(f'sga-unpack failed with exit code {result.returncode}')

    print(f'   unpacked in {round(time.time() - started, 1)} seconds')
    return output_dir


def find_scenarios_dir(root):
    """
    Locates the `scenarios/multiplayer` directory. Accepts the unpack root, the
    `scenarios` directory or the `multiplayer` directory itself, so a caller does
    not have to care which level they point at.
    """
    # Most specific first: the unpack root also "contains" .info files further down,
    # and picking it would put "scenarios/multiplayer" twice into every folder path.
    candidates = (
        os.path.join(root, 'scenarios', 'multiplayer'),
        os.path.join(root, 'multiplayer'),
    )

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    if os.path.isdir(root) and _has_info_files(root):
        return root

    raise FileNotFoundError(f'No scenario .info files found under {root}')


def _has_info_files(root):
    for _, _, files in os.walk(root):
        if any(name.lower().endswith('.info') for name in files):
            return True
    return False


def collect_info_files(scenarios_dir):
    """
    Returns a sorted list of (map_id, relative_folder, absolute_path).

    The map id is the `.info` filename stem, which does not always match its folder
    (`community/faymonville_2p/faymonville.info`, `community/eindhoven_4p/eindhoven.info`).
    """
    found = []
    for current_dir, _, files in os.walk(scenarios_dir):
        for name in files:
            if not name.lower().endswith('.info'):
                continue

            path = os.path.join(current_dir, name)
            relative = os.path.relpath(current_dir, scenarios_dir).replace(os.sep, '/')
            if relative == '.':
                relative = ''
            found.append((os.path.splitext(name)[0], relative, path))

    return sorted(found, key=lambda entry: entry[0])


def classify_scenario(relative_folder, header, name):
    """Returns the `category` tag for a scenario."""
    folder_parts = relative_folder.split('/') if relative_folder else []

    if CATEGORY_HOFF in folder_parts:
        return CATEGORY_HOFF
    if header.get('scenario_type') == 0:
        return CATEGORY_TEST
    if name and name.strip().upper().startswith('[TEST]'):
        return CATEGORY_TEST

    return CATEGORY_MP


def build_map_entry(map_id, relative_folder, header, locstrings, ebps_index, unresolved,
                    sibling_files):
    name_id, name = resolve_locstring(header.get('scenarioname'), locstrings)
    # `ScenarioDescriptionlong` is not exported: the game writes the same locstring id
    # into it as into `ScenarioDescription` on every single scenario, so it is pure
    # duplication (verified on all 78 scenarios of build 48837).
    description_id, description = resolve_locstring(
        header.get('ScenarioDescription'), locstrings
    )

    raw_points = header.get('point_positions')
    raw_points = raw_points if isinstance(raw_points, list) else []
    points = [
        classify_point(point, ebps_index, unresolved)
        for point in raw_points
        if isinstance(point, dict)
    ]

    starting_positions = [
        point for point in points if point.get('kind') == KIND_STARTING_POSITION
    ]
    slot_counts, teams = summarize_slots(header)
    summary = summarize_points(points)

    map_size = header.get('mapsize')
    if isinstance(map_size, list) and len(map_size) >= 2:
        map_size = {'width': map_size[0], 'height': map_size[1]}
    else:
        map_size = None

    category = classify_scenario(relative_folder, header, name)
    folder = 'scenarios/multiplayer'
    if relative_folder:
        folder = folder + '/' + relative_folder

    entry = {
        'id': map_id,
        'folder': folder,
        'category': category,
        'isLobbyVisible': header.get('visible_in_lobby') is True,
        'isCommunity': header.get('map_origin') == MAP_ORIGIN_COMMUNITY,
        'scenarioType': header.get('scenario_type'),
        'mapOrigin': header.get('map_origin'),
        'version': header.get('version'),
        'author': header.get('map_author'),
        'audioEnvironment': header.get('audio_environment'),
        'worldbp': header.get('worldbp'),
        'name': {'locstring': name_id, 'en': name},
        'description': {'locstring': description_id, 'en': description},
        'mapSize': map_size,
        'playableAreaEstimate': playable_bounds(points),
        'maxPlayers': len(starting_positions),
        'teamLayout': team_layout(teams),
        'teams': dict(sorted(teams.items())),
        'enabledSlots': slot_counts['enabled'],
        'aiSlots': slot_counts['ai'],
        'totalSlots': slot_counts['total'],
        'resources': summary,
        'points': points,
        'minimapFiles': sorted(
            name for name in sibling_files if name.lower().endswith('.rrtex')
        ),
    }

    # Keys only a minority of scenarios carry. Passed through so nothing is lost.
    for source, target in (
        ('win_condition', 'winCondition'),
        ('win_conditions', 'winConditions'),
        ('tuning_variant', 'tuningVariant'),
        ('sort_index', 'sortIndex'),
        ('start_location', 'startLocation'),
        ('stylized_minimap_enabled', 'stylizedMinimapEnabled'),
        ('stylized_minimap_pipeline_path', 'stylizedMinimapPipelinePath'),
        ('default_layer_set_tags', 'defaultLayerSetTags'),
    ):
        if source in header:
            entry[target] = header[source]

    return entry


def build_mp_maps(scenarios_dir, locstrings, ebps_index, dump_info_dir=None,
                  include_test=False):
    info_files = collect_info_files(scenarios_dir)
    print(f'## Found {len(info_files)} scenario .info files')

    maps = {}
    unresolved = set()
    failures = []
    warnings = []
    skipped_test = []

    for map_id, relative_folder, path in info_files:
        try:
            header = parse_info_file(path)
        except LuaInfoParseError as error:
            failures.append((path, str(error)))
            continue

        sibling_files = os.listdir(os.path.dirname(path))
        entry = build_map_entry(
            map_id, relative_folder, header, locstrings, ebps_index, unresolved,
            sibling_files,
        )

        # Cinematic and defend/test scenarios are not playable maps.
        if entry['category'] == CATEGORY_TEST and not include_test:
            skipped_test.append(map_id)
            continue

        if map_id in maps:
            warnings.append(f'duplicate map id "{map_id}" ({entry["folder"]})')

        maps[map_id] = entry

        # Only meaningful for real multiplayer maps. Co-op and test scenarios routinely
        # have more spawn points than lobby slots, which is not a problem.
        if (
            entry['category'] == CATEGORY_MP
            and entry['maxPlayers']
            and entry['maxPlayers'] != entry['enabledSlots']
        ):
            warnings.append(
                f'{map_id}: {entry["maxPlayers"]} starting positions but '
                f'{entry["enabledSlots"]} enabled slots'
            )

        if dump_info_dir:
            target_dir = os.path.join(dump_info_dir, relative_folder)
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(target_dir, os.path.basename(path)))

    if skipped_test:
        print(f'## Skipped {len(skipped_test)} test/cinematic scenarios: '
              + ', '.join(skipped_test))

    return maps, unresolved, failures, warnings


def build_meta(maps):
    categories = {}
    for entry in maps.values():
        categories[entry['category']] = categories.get(entry['category'], 0) + 1

    return {
        'schemaVersion': SCHEMA_VERSION,
        'generatedFrom': 'ScenariosMP.sga',
        'mapCount': len(maps),
        'categories': dict(sorted(categories.items())),
        'lobbyVisibleCount': sum(1 for entry in maps.values() if entry['isLobbyVisible']),
        'communityCount': sum(1 for entry in maps.values() if entry['isCommunity']),
    }


def save_json(data, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    # newline='\n' keeps the file LF only on Windows, matching .gitattributes.
    with open(path, 'w', encoding='utf-8', newline='\n') as json_file:
        json.dump(data, json_file, indent=2, ensure_ascii=False, sort_keys=False)
        json_file.write('\n')


def main():
    args = parse_args()
    started = time.time()

    # CI pipes stdout, which makes Python block-buffer it: without this every line
    # only shows up once the script exits, so a slow unpack looks like a silent hang.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    sga_path = args.sga
    if args.game_path:
        sga_path = os.path.join(args.game_path, SCENARIOS_ARCHIVE)

    if not args.scenarios_dir and not sga_path:
        print('Error: one of --game-path, --sga or --scenarios-dir is required')
        return 2

    print('## Loading locstrings from ' + args.locstring)
    locstrings = load_locstrings(args.locstring)
    print(f'   {len(locstrings)} entries')

    print('## Loading entity blueprints via ' + args.ebps)
    ebps_index = load_ebps_index(args.ebps)
    print(f'   {len(ebps_index)} gameplay/hoff blueprints indexed')

    # Only clean up a directory this run created, so pointing --unpack-dir at an
    # existing folder never deletes someone's data.
    created_unpack_dir = None
    try:
        if args.scenarios_dir:
            scenarios_root = args.scenarios_dir
        else:
            if not os.path.exists(args.unpack_dir):
                created_unpack_dir = args.unpack_dir
            scenarios_root = unpack_archive(sga_path, args.essence_cli, args.unpack_dir)

        scenarios_dir = find_scenarios_dir(scenarios_root)
        print('## Reading scenarios from ' + scenarios_dir)

        maps, unresolved, failures, warnings = build_mp_maps(
            scenarios_dir, locstrings, ebps_index, args.dump_info_dir, args.include_test
        )
    finally:
        if created_unpack_dir and not args.keep_unpacked:
            print('## Removing ' + created_unpack_dir)
            shutil.rmtree(created_unpack_dir, ignore_errors=True)

    for warning in warnings:
        print('   warning: ' + warning)

    if unresolved:
        # Not fatal on its own: a new Relic ebp should be visible, not a build break.
        print('   warning: ebp_name not found in ebps.json: ' + ', '.join(sorted(unresolved)))

    if failures:
        print(f'Error: {len(failures)} .info file(s) failed to parse:')
        for path, message in failures:
            print(f'   {path}: {message}')
        return 1

    if len(maps) < args.min_maps:
        print(
            f'Error: only {len(maps)} scenarios found, expected at least {args.min_maps}. '
            'Extraction probably failed; refusing to write a thin data file.'
        )
        return 1

    output = {'__meta': build_meta(maps)}
    for map_id in sorted(maps):
        output[map_id] = maps[map_id]

    save_json(output, args.output)

    meta = output['__meta']
    print('')
    print(f'Wrote {args.output}')
    print(f'   {meta["mapCount"]} scenarios: ' + ', '.join(
        f'{count} {category}' for category, count in meta['categories'].items()
    ))
    print(f'   {meta["lobbyVisibleCount"]} lobby visible, {meta["communityCount"]} community')
    print(f'Execution time: {round(time.time() - started, 1)} seconds')
    return 0


if __name__ == '__main__':
    sys.exit(main())
