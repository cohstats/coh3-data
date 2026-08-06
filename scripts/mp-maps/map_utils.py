"""
Helpers for turning parsed scenario `.info` data into the shape written to
`data/mp-maps.json`.

Two external inputs are cross-referenced:

* the English locstring table (from `data/locales/en-locstring.json` or a raw
  `anvil.en.ucs`), to resolve `"$11266017"` into `"(4) El Alamein"`.
* `data/ebps.json` (or the smaller `data/chunked/ebps/*.json`), to look up what each
  `ebp_name` in `point_positions` actually is: which resource it provides, at what
  rate, and how long it takes to capture. Rates are never hardcoded here.

The `.info` point list itself is not trusted: `reconcile_with_layers` replaces it with
the entities `layer_parser` reads out of the scenario's Chunky files. See that module
for why.
"""

import json
import math
import os

from layer_parser import is_territory_entity
from sector_geometry import build_sector_polygons, sector_at

# Footprint variants. Same income, different physical size on the map, so they are
# recorded separately but do not affect classification.
SHAPE_SUFFIXES = (
    '_square7x7',
    '_square10x10',
    '_rect15x20',
    '_smaller',
    '_larger',
)

# Longest first: 'extra_low' must win over 'low'.
TIERS = ('extra_medium', 'extra_low', 'medium', 'high', 'low')

# Resources we report. Everything else in `resource_provided_per_second` is zero for
# territory points.
TRACKED_RESOURCES = ('manpower', 'fuel', 'munition')

KIND_STARTING_POSITION = 'starting_position'
# The ebp is known but is not a territory point (map markers, hoff capture areas).
KIND_OTHER = 'other'
# The ebp is not in ebps.json at all - most likely added by a patch.
KIND_UNKNOWN = 'unknown'

# Kinds that count towards the capturable point total.
CAPTURABLE_KINDS = ('fuel', 'munitions', 'strategic', 'victory', 'sp')


def load_locstrings(path):
    """
    Loads the English locstring table. Accepts either the JSON produced by
    `scripts/ucs-to-json.py` or a raw UTF-16 `.ucs` file straight out of
    `COH3-SGA-Extraction.exe`.
    """
    if path.lower().endswith('.ucs'):
        locstrings = {}
        # UCS files are UTF-16 and tab separated: ID<tab>Text
        with open(path, 'r', encoding='UTF-16') as ucs_file:
            for line in ucs_file:
                if not line.strip():
                    continue
                parts = line.strip().split('\t', 1)
                if len(parts) == 2 and parts[0].isdigit():
                    locstrings[parts[0]] = parts[1]
        return locstrings

    # Explicit encoding: the default on Windows is cp1252 and blows up on these files.
    with open(path, 'r', encoding='utf-8') as json_file:
        return json.load(json_file)


def resolve_locstring(value, locstrings):
    """
    Returns (locstring_id, english_text) for a `.info` name/description field.

    Most maps store `"$11266017"`, but a handful ship a literal English string
    (e.g. `"(2) Ancona Railyard"`), in which case there is no id to return.
    """
    if value is None:
        return None, None

    value = str(value)
    if not value.startswith('$'):
        return None, value

    locstring_id = value[1:]
    return locstring_id, locstrings.get(locstring_id)


def _iter_ebps_nodes(node, path=()):
    """Yields (path_tuple, node) for every entity blueprint in an ebps tree."""
    if not isinstance(node, dict):
        return

    if 'pbgid' in node:
        yield path, node
        return

    for key, value in node.items():
        yield from _iter_ebps_nodes(value, path + (key,))


def _find_extension(ebp, extension_name):
    """
    Returns the `exts` dict of the named ebp extension, or None.

    Extensions are a list of single key dicts; the extension is identified by the
    tail of its `template_reference` value, e.g. `ebpextensions\\resource_ext`.
    """
    for entry in ebp.get('extensions', []) or []:
        if not isinstance(entry, dict):
            continue
        exts = entry.get('exts')
        if not isinstance(exts, dict):
            continue

        template = exts.get('template_reference')
        if not isinstance(template, dict):
            continue

        reference = str(template.get('value', '')).replace('\\', '/')
        if reference.rsplit('/', 1)[-1] == extension_name:
            return exts

    return None


def _income_per_second(ebp):
    resource_ext = _find_extension(ebp, 'resource_ext')
    if resource_ext is None:
        return {}, None

    rates = resource_ext.get('resource_provided_per_second') or {}
    income = {}
    for resource in TRACKED_RESOURCES:
        try:
            rate = float(rates.get(resource, 0) or 0)
        except (TypeError, ValueError):
            rate = 0.0
        if rate:
            income[resource] = rate

    return income, resource_ext.get('default_provided_resource') or None


def _capture_info(ebp):
    strategic_ext = _find_extension(ebp, 'strategic_point_ext')
    if strategic_ext is None:
        return {}

    info = {}
    for source, target in (
        ('capture_time', 'captureTime'),
        ('revert_time', 'revertTime'),
        ('secure_radius', 'secureRadius'),
    ):
        if source in strategic_ext:
            try:
                info[target] = round(float(strategic_ext[source]), 4)
            except (TypeError, ValueError):
                pass

    return info


def load_ebps_index(ebps_path):
    """
    Builds {ebp_name: descriptor} for every entity blueprint that a scenario can
    reference as a point. Only the `gameplay` and `hoff` subtrees are walked; the
    `races` subtree holds units and is both irrelevant and huge.

    Prefers the chunked per-subtree files when they exist, because
    `data/ebps.json` is ~90 MB while `data/chunked/ebps/gameplay.json` is ~4 MB.
    """
    subtrees = {}
    chunked_dir = os.path.join(os.path.dirname(ebps_path), 'chunked', 'ebps')

    for subtree in ('gameplay', 'hoff'):
        chunk_path = os.path.join(chunked_dir, subtree + '.json')
        if os.path.isfile(chunk_path):
            with open(chunk_path, 'r', encoding='utf-8') as chunk_file:
                subtrees[subtree] = json.load(chunk_file)

    if not subtrees:
        with open(ebps_path, 'r', encoding='utf-8') as ebps_file:
            ebps = json.load(ebps_file)
        for subtree in ('gameplay', 'hoff'):
            if subtree in ebps:
                subtrees[subtree] = ebps[subtree]

    if not subtrees:
        raise ValueError(f'No gameplay/hoff entity blueprints found via {ebps_path}')

    index = {}
    for subtree, tree in subtrees.items():
        for path, ebp in _iter_ebps_nodes(tree):
            if not path:
                continue

            name = path[-1]
            income, provided = _income_per_second(ebp)
            descriptor = {
                'path': '/'.join((subtree,) + path),
                # For gameplay points the folder is authoritative:
                # gameplay/strategic_points/<category>/<ebp_name>
                'folder': path[-2] if len(path) >= 2 else None,
                'resource': provided,
                'incomePerSecond': income,
            }
            descriptor.update(_capture_info(ebp))
            index[name] = descriptor

    return index


def strip_shape_suffix(ebp_name):
    """Returns (base_name, shape_suffix_or_None)."""
    for suffix in SHAPE_SUFFIXES:
        if ebp_name.endswith(suffix):
            return ebp_name[:-len(suffix)], suffix
    return ebp_name, None


def _category_from_descriptor(descriptor, base_name):
    """
    The ebps folder under `gameplay/strategic_points/` is the authoritative
    category (fuel / munitions / strategic / victory / sp). Points that live
    elsewhere (the `hoff_*` ones) fall back to their provided resource, then to
    the name.
    """
    folder = descriptor.get('folder') if descriptor else None
    if folder in ('fuel', 'munitions', 'strategic', 'victory', 'sp'):
        return folder

    resource = (descriptor or {}).get('resource')
    if resource == 'fuel':
        return 'fuel'
    if resource == 'munition':
        return 'munitions'
    if resource == 'manpower':
        return 'strategic'

    if 'victory' in base_name:
        return 'victory'
    if 'fuel' in base_name:
        return 'fuel'
    if 'munition' in base_name:
        return 'munitions'
    if 'strategic' in base_name:
        return 'strategic'

    return None


def _tier_from_name(base_name):
    for tier in TIERS:
        if base_name.endswith('_' + tier) or ('_' + tier + '_') in base_name:
            return tier
    return None


# How far apart, in game units, a `.info` point and the layer entity it is taken to be
# may sit. The `.info` positions are stale, not random: 66 of 78 scenarios match to the
# millimetre and the largest genuine drift on a playable map is 8.2 units
# (across_the_rhine_6p). 10 leaves headroom and still cannot reach a neighbouring point
# - the closest two territory points on any shipped map are 25.9 units apart.
MATCH_RADIUS = 10.0


def reconcile_with_layers(raw_points, entities, radius=MATCH_RADIUS):
    """
    Replaces the `.info` territory points with the entities the game actually loads.

    Returns `(points, stats)`. The `.info` order is kept and non territory entries
    (starting positions, which only exist in the `.info`) pass through untouched.

    Matching is greedy nearest pair: both lists describe the same map, so the shortest
    remaining pair is always the same point, and each side is consumed once. A point
    that finds no partner within `radius` keeps its `.info` values and is counted in
    `stats` so the caller can warn about it.
    """
    points = [dict(point) if isinstance(point, dict) else point for point in raw_points]
    stats = {
        'matched': 0,
        'renamed': [],
        'moved': 0,
        'unmatchedInfo': [],
        'unmatchedLayer': [],
    }

    if not entities:
        return points, stats

    candidates = [
        index for index, point in enumerate(points)
        if isinstance(point, dict) and is_territory_entity(str(point.get('ebp_name', '')))
        and isinstance(point.get('x'), (int, float))
        and isinstance(point.get('y'), (int, float))
    ]

    pairs = []
    for index in candidates:
        point = points[index]
        for entity_index, entity in enumerate(entities):
            distance = math.dist((point['x'], point['y']), (entity['x'], entity['y']))
            if distance <= radius:
                pairs.append((distance, index, entity_index))
    pairs.sort()

    used_points = set()
    used_entities = set()
    for distance, index, entity_index in pairs:
        if index in used_points or entity_index in used_entities:
            continue
        used_points.add(index)
        used_entities.add(entity_index)

        point = points[index]
        entity = entities[entity_index]
        if point['ebp_name'] != entity['ebp']:
            stats['renamed'].append((point['ebp_name'], entity['ebp']))
        if distance:
            stats['moved'] += 1

        point['ebp_name'] = entity['ebp']
        point['x'] = entity['x']
        point['y'] = entity['y']
        stats['matched'] += 1

    stats['unmatchedInfo'] = [points[index]['ebp_name'] for index in candidates
                              if index not in used_points]
    stats['unmatchedLayer'] = [entity['ebp'] for entity_index, entity in enumerate(entities)
                               if entity_index not in used_entities]

    return points, stats


def classify_point(point, ebps_index, unresolved):
    """
    Turns one `point_positions` entry into the record written to the JSON.
    `unresolved` collects ebp names missing from ebps.json so the caller can report
    them instead of silently dropping information.
    """
    # `owner_id` is not exported: it is 0 on every territory point, and on a starting
    # position it only encodes the lobby slot, which is reported as `playerSlot`.
    ebp_name = point.get('ebp_name')
    record = {'ebp': ebp_name}

    for source, target in (('x', 'x'), ('y', 'y'), ('z', 'z')):
        if source in point:
            record[target] = point[source]

    if ebp_name is None:
        record['kind'] = KIND_UNKNOWN
        return record

    if ebp_name.startswith(KIND_STARTING_POSITION):
        record['kind'] = KIND_STARTING_POSITION
        # owner_id 1000..1007 identifies the lobby slot this position belongs to.
        owner_id = point.get('owner_id')
        if isinstance(owner_id, int) and 1000 <= owner_id <= 1007:
            record['playerSlot'] = owner_id - 1000
        if ebp_name != KIND_STARTING_POSITION:
            record['variant'] = ebp_name
        return record

    base_name, shape = strip_shape_suffix(ebp_name)
    descriptor = ebps_index.get(ebp_name) or ebps_index.get(base_name)
    if descriptor is None:
        unresolved.add(ebp_name)

    category = _category_from_descriptor(descriptor, base_name)
    if category:
        record['kind'] = category
    else:
        record['kind'] = KIND_UNKNOWN if descriptor is None else KIND_OTHER
    record['category'] = category
    record['tier'] = _tier_from_name(base_name)
    # Only the ~1/3 of points that actually have a footprint variant carry `shape`;
    # two thirds of them use the default footprint and would just be `"shape": null`.
    if shape:
        record['shape'] = shape

    if descriptor:
        income = descriptor.get('incomePerSecond') or {}
        if income:
            record['incomePerMinute'] = {
                resource: round(rate * 60, 4) for resource, rate in income.items()
            }
        for key in ('captureTime', 'revertTime', 'secureRadius'):
            if key in descriptor:
                record[key] = descriptor[key]

    return record


def summarize_points(points):
    """Counts and total income for the point records of a single map."""
    counts = {}
    by_tier = {}
    income = {resource: 0.0 for resource in TRACKED_RESOURCES}

    for point in points:
        kind = point.get('kind') or KIND_UNKNOWN
        counts[kind] = counts.get(kind, 0) + 1

        category = point.get('category')
        if category:
            tier = point.get('tier') or 'default'
            by_tier.setdefault(category, {})
            by_tier[category][tier] = by_tier[category].get(tier, 0) + 1

        for resource, rate in (point.get('incomePerMinute') or {}).items():
            income[resource] = income.get(resource, 0.0) + rate

    capturable = sum(
        count for kind, count in counts.items() if kind in CAPTURABLE_KINDS
    )

    return {
        'counts': dict(sorted(counts.items())),
        'countsByTier': {
            category: dict(sorted(tiers.items()))
            for category, tiers in sorted(by_tier.items())
        },
        'totalCapturable': capturable,
        'incomePerMinute': {
            resource: round(total, 2)
            for resource, total in sorted(income.items())
            if total
        },
    }


def summarize_slots(header):
    """
    Summarises the 16 entry `slots` table into counts, and returns the team split.

    `status` is 0 for a slot a human can take, 1 for a disabled slot and 2 for an
    AI slot (only the co-op "Hold Off" maps use 2). Slot index i corresponds to
    `owner_id` 1000 + i.

    The per-slot rows themselves are deliberately not exported: on every regular
    multiplayer map they are mechanically derivable (`status` is 0 for the first
    `enabled` slots and 1 afterwards, `team` alternates 0/1, `flags` is a constant),
    so they would be ~19% of the output file carrying no information. The AI slot
    count is the only part that is not derivable from the other fields.
    """
    counts = {'total': 0, 'enabled': 0, 'ai': 0}
    teams = {}

    raw_slots = header.get('slots')
    if not isinstance(raw_slots, list):
        return counts, teams

    for slot in raw_slots:
        if not isinstance(slot, dict):
            continue

        counts['total'] += 1
        status = slot.get('status')

        if status == 0:
            counts['enabled'] += 1
            team = slot.get('team')
            key = str(team) if team is not None else KIND_UNKNOWN
            teams[key] = teams.get(key, 0) + 1
        elif status == 2:
            counts['ai'] += 1

    return counts, teams


def team_layout(teams):
    """`{'0': 2, '1': 2}` -> `'2v2'`. Returns None when teams are not well formed."""
    numeric = sorted(
        (int(key), count) for key, count in teams.items() if key.isdigit()
    )
    if len(numeric) < 2:
        return None
    return 'v'.join(str(count) for _, count in numeric)


def build_sectors(territory, points):
    """
    Builds the exported `sectors` list for one map.

    Each sector carries its outline, the indices of the `points` it contains and the
    ids of the sectors it borders, which is what a client needs to draw the territory
    overlay and to reason about cut off chains.

    `stats` reports points that landed outside every sector so the caller can warn:
    on a well formed map every capturable point sits in a sector.
    """
    stats = {'pointsOutside': [], 'sectorsWithoutPoints': []}
    if not territory:
        return None, stats

    polygons = build_sector_polygons(territory)
    if not polygons:
        return None, stats

    members = {sector_id: [] for sector_id in polygons}
    for index, point in enumerate(points):
        if point.get('kind') == KIND_STARTING_POSITION:
            continue
        if not isinstance(point.get('x'), (int, float)):
            continue

        sector_id = sector_at(territory, point['x'], point['y'])
        if sector_id in members:
            members[sector_id].append(index)
        elif point.get('kind') in CAPTURABLE_KINDS:
            stats['pointsOutside'].append(point.get('ebp'))

    records = territory['sectors']
    half_width = territory['width'] / 2.0
    half_height = territory['height'] / 2.0

    sectors = []
    for sector_id in sorted(polygons):
        polygon = polygons[sector_id]
        record = records[sector_id - 1] if sector_id - 1 < len(records) else {}
        # Neighbours are dropped rather than kept dangling when the sector they name
        # was too small to export.
        neighbors = [
            neighbor for neighbor in record.get('neighbors', []) if neighbor in polygons
        ]

        entry = {
            'id': sector_id,
            'isBase': bool(record.get('isBase')),
            'neighbors': neighbors,
            'points': members[sector_id],
            'area': polygon['cellCount'],
            'rings': polygon['rings'],
        }

        bbox = record.get('bbox')
        if bbox:
            min_x, max_x, min_y, max_y = bbox
            entry['bounds'] = {
                'minX': min_x - half_width,
                # The stored box is inclusive of its last cell, which spans one unit.
                'maxX': max_x + 1 - half_width,
                'minY': min_y - half_height,
                'maxY': max_y + 1 - half_height,
            }

        if not entry['points']:
            stats['sectorsWithoutPoints'].append(sector_id)

        sectors.append(entry)

    return sectors, stats


def playable_bounds(points):
    """
    Bounding box of all points, in game units. This is an estimate of the playable
    area, not authored data: `mapsize` in the `.info` is the full world including
    the out of bounds border.
    """
    xs = [point['x'] for point in points if isinstance(point.get('x'), (int, float))]
    ys = [point['y'] for point in points if isinstance(point.get('y'), (int, float))]
    if not xs or not ys:
        return None

    return {
        'minX': round(min(xs), 3),
        'maxX': round(max(xs), 3),
        'minY': round(min(ys), 3),
        'maxY': round(max(ys), 3),
        'width': round(max(xs) - min(xs), 3),
        'height': round(max(ys) - min(ys), 3),
    }
