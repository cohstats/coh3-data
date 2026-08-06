"""
Generates `data/mp-maps.json` from the multiplayer scenarios shipped in
`<game>/anvil/archives/ScenariosMP.sga`.

This script does NOT unpack the archive. Unpacking `ScenariosMP.sga` is the caller's
job - the workflow does it in its own step with AOEMods.Essence.CLI (`sga-unpack`),
the same way `cohstats/coh3-cdn` does - so that a slow unpack is visible as its own
step instead of hiding inside this script. Here we only read the already unpacked
`.info` files for name, size, player slots and resource point layout. Resource income
rates are looked up in `data/ebps.json` rather than hardcoded.

Typical use:

    tools/AOEMods.Essence/AOEMods.Essence.CLI.exe sga-unpack ScenariosMP.sga ./scenarios
    python scripts/mp-maps/main.py --scenarios-dir ./scenarios

See scripts/mp-maps/README.md for the full walkthrough.
"""

import argparse
import json
import os
import re
import shutil
import struct
import sys
import time

from layer_parser import collect_scenario_entities
from lua_info_parser import LuaInfoParseError, parse_info_file
from territory_parser import TerritoryParseError, parse_territory_file
from map_utils import (
    KIND_STARTING_POSITION,
    build_sectors,
    classify_point,
    load_ebps_index,
    load_locstrings,
    playable_bounds,
    reconcile_with_layers,
    resolve_locstring,
    summarize_points,
    summarize_slots,
    team_layout,
)

PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/../.."))

DEFAULT_LOCSTRING = os.path.join(PROJECT_ROOT_DIR, 'data', 'locales', 'en-locstring.json')
DEFAULT_EBPS = os.path.join(PROJECT_ROOT_DIR, 'data', 'ebps.json')
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT_DIR, 'data', 'mp-maps.json')

# Where the workflow unpacks ScenariosMP.sga: inside the workspace, which on GitHub
# Windows runners is the fast local SSD (D:). Unpacking this ~1 GB archive to the
# system temp directory on C: ran for over 105 minutes without finishing.
DEFAULT_SCENARIOS_DIR = os.path.join(PROJECT_ROOT_DIR, 'scenarios')

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

    parser.add_argument(
        '--scenarios-dir',
        default=DEFAULT_SCENARIOS_DIR,
        help='Directory holding the unpacked ScenariosMP.sga contents; the unpack root, '
             'its scenarios/ folder or the multiplayer/ folder are all accepted '
             f'(default: {DEFAULT_SCENARIOS_DIR})',
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


def load_territory(scenario_dir, map_id):
    """
    Reads `<map_id>_territory.override`, the painted sector layout.

    Returns (territory, warning). A missing file is not an error - the cinematic
    scenarios and a few stubs ship none - but a malformed one is worth reporting
    rather than silently exporting a map without its sectors.
    """
    path = os.path.join(scenario_dir, map_id + '_territory.override')
    if not os.path.isfile(path):
        return None, None

    try:
        return parse_territory_file(path), None
    except (TerritoryParseError, OSError, struct.error) as error:
        return None, f'{map_id}: could not read territory sectors: {error}'


def build_map_entry(map_id, relative_folder, header, locstrings, ebps_index, unresolved,
                    sibling_files, layer_entities, territory):
    name_id, name = resolve_locstring(header.get('scenarioname'), locstrings)
    # `ScenarioDescriptionlong` is not exported: the game writes the same locstring id
    # into it as into `ScenarioDescription` on every single scenario, so it is pure
    # duplication (verified on all 78 scenarios of build 48837).
    description_id, description = resolve_locstring(
        header.get('ScenarioDescription'), locstrings
    )

    raw_points = header.get('point_positions')
    raw_points = raw_points if isinstance(raw_points, list) else []
    # The `.info` point list is a stale editor summary; the scenario's own entities win.
    raw_points, reconcile_stats = reconcile_with_layers(raw_points, layer_entities)
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
    sectors, sector_stats = build_sectors(territory, points)

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
        'sectors': sectors,
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

    return entry, reconcile_stats, sector_stats


def describe_reconciliation(map_id, layer_entities, stats):
    """
    Turns the reconciliation result for one scenario into log lines.

    A rename is normal and is the whole point of reading the layers, so it is logged
    as information. An unmatched point on either side is not: it means the `.info` and
    the scenario disagree by more than a drifted position, and the exported point list
    then still carries stale data for that point.
    """
    messages = []

    if not layer_entities:
        # Expected for the co-op maps, whose capture areas are not `DATAENTI` entities.
        return messages

    for old, new in stats['renamed']:
        messages.append(f'{map_id}: .info says "{old}", scenario has "{new}"')

    if stats['unmatchedInfo']:
        messages.append(
            f'{map_id}: {len(stats["unmatchedInfo"])} .info point(s) have no entity '
            'in the scenario, keeping the .info values: '
            + ', '.join(sorted(stats['unmatchedInfo']))
        )
    if stats['unmatchedLayer']:
        messages.append(
            f'{map_id}: {len(stats["unmatchedLayer"])} scenario entit(y/ies) are not '
            'in the .info and are not exported: '
            + ', '.join(sorted(stats['unmatchedLayer']))
        )

    return messages


def build_mp_maps(scenarios_dir, locstrings, ebps_index, dump_info_dir=None,
                  include_test=False):
    info_files = collect_info_files(scenarios_dir)
    print(f'## Found {len(info_files)} scenario .info files')

    maps = {}
    unresolved = set()
    failures = []
    warnings = []
    skipped_test = []
    without_entities = []
    without_sectors = []
    points_outside = []

    for map_id, relative_folder, path in info_files:
        try:
            header = parse_info_file(path)
        except LuaInfoParseError as error:
            failures.append((path, str(error)))
            continue

        scenario_dir = os.path.dirname(path)
        sibling_files = os.listdir(scenario_dir)
        layer_entities = collect_scenario_entities(scenario_dir, map_id)
        territory, territory_warning = load_territory(scenario_dir, map_id)
        entry, reconcile_stats, sector_stats = build_map_entry(
            map_id, relative_folder, header, locstrings, ebps_index, unresolved,
            sibling_files, layer_entities, territory,
        )

        # Cinematic and defend/test scenarios are not playable maps.
        if entry['category'] == CATEGORY_TEST and not include_test:
            skipped_test.append(map_id)
            continue

        # Reported after the skip: the `*_defend_01` scenarios ship a copy of another
        # map's `.info` and would drown the real findings in noise.
        warnings.extend(describe_reconciliation(map_id, layer_entities, reconcile_stats))
        if not layer_entities:
            without_entities.append(map_id)

        if territory_warning:
            warnings.append(territory_warning)
        if entry['sectors'] is None:
            without_sectors.append(map_id)
        elif entry['category'] == CATEGORY_MP:
            if sector_stats['pointsOutside']:
                points_outside.append(
                    f'{map_id} ({len(sector_stats["pointsOutside"])})'
                )
            if territory and entry['mapSize'] and (
                territory['width'] != entry['mapSize']['width']
                or territory['height'] != entry['mapSize']['height']
            ):
                warnings.append(
                    f'{map_id}: sector grid {territory["width"]}x{territory["height"]} '
                    f'does not match mapsize {entry["mapSize"]["width"]}x'
                    f'{entry["mapSize"]["height"]}; sector coordinates may be offset'
                )

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

    if without_entities:
        # Expected for the co-op maps - their capture areas are not `DATAENTI`
        # entities - and for `hill_400_8p`, a stub with no points at all.
        print(f'## {len(without_entities)} scenarios ship no territory entities to '
              'reconcile against, keeping their .info point list: '
              + ', '.join(without_entities))

    if without_sectors:
        print(f'## {len(without_sectors)} scenarios ship no painted territory sectors, '
              'their "sectors" is null: ' + ', '.join(without_sectors))

    if points_outside:
        # Authored, not a defect: a victory point is often placed exactly on the seam
        # where several sectors meet, or in a deliberately unpainted neutral area, so
        # it belongs to no sector and appears in no sector's `points`.
        print(f'## {len(points_outside)} scenarios have capturable points that sit on a '
              'sector seam or on unpainted ground and so belong to no sector: '
              + ', '.join(points_outside))

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
        'withSectorsCount': sum(1 for entry in maps.values() if entry.get('sectors')),
    }


# Sector outlines are written one ring per line instead of one number per line.
# Indented, the ~197k polygon vertices would take 3.7 MB and turn every regeneration
# into a 240k line diff; collapsed, the same data is a few hundred KB and a ring that
# did not change stays a single unchanged line.
RING_PLACEHOLDER = '@@ring:{}@@'


def _collapse_rings(node, collected):
    """Swaps every polygon ring for a placeholder, returning the rewritten tree."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == 'rings' and isinstance(value, list):
                rings = []
                for ring in value:
                    collected.append(json.dumps(ring, separators=(',', ':')))
                    rings.append(RING_PLACEHOLDER.format(len(collected) - 1))
                out[key] = rings
            else:
                out[key] = _collapse_rings(value, collected)
        return out

    if isinstance(node, list):
        return [_collapse_rings(item, collected) for item in node]

    return node


def save_json(data, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    collected = []
    text = json.dumps(
        _collapse_rings(data, collected), indent=2, ensure_ascii=False, sort_keys=False
    )

    # One pass: replacing the placeholders one at a time would rescan the whole
    # document per ring.
    text = re.sub(
        r'"@@ring:(\d+)@@"',
        lambda match: collected[int(match.group(1))],
        text,
    )

    # newline='\n' keeps the file LF only on Windows, matching .gitattributes.
    with open(path, 'w', encoding='utf-8', newline='\n') as json_file:
        json_file.write(text)
        json_file.write('\n')


def main():
    args = parse_args()
    started = time.time()

    # CI pipes stdout, which makes Python block-buffer it: without this every line
    # only shows up once the script exits, so a slow step looks like a silent hang.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if not os.path.isdir(args.scenarios_dir):
        print(f'Error: scenarios directory not found: {args.scenarios_dir}')
        print('Unpack ScenariosMP.sga first, for example:')
        print('   tools/AOEMods.Essence/AOEMods.Essence.CLI.exe sga-unpack '
              '<game>/anvil/archives/ScenariosMP.sga ./scenarios')
        return 2

    print('## Loading locstrings from ' + args.locstring)
    locstrings = load_locstrings(args.locstring)
    print(f'   {len(locstrings)} entries')

    print('## Loading entity blueprints via ' + args.ebps)
    ebps_index = load_ebps_index(args.ebps)
    print(f'   {len(ebps_index)} gameplay/hoff blueprints indexed')

    scenarios_dir = find_scenarios_dir(args.scenarios_dir)
    print('## Reading scenarios from ' + scenarios_dir)

    maps, unresolved, failures, warnings = build_mp_maps(
        scenarios_dir, locstrings, ebps_index, args.dump_info_dir, args.include_test
    )

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
