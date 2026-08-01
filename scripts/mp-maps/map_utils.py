"""
Helpers for turning parsed scenario `.info` data into the shape written to
`data/mp-maps.json`.

Two external inputs are cross-referenced:

* the English locstring table (from `data/locales/en-locstring.json` or a raw
  `anvil.en.ucs`), to resolve `"$11266017"` into `"(4) El Alamein"`.
* `data/ebps.json` (or the smaller `data/chunked/ebps/*.json`), to look up what each
  `ebp_name` in `point_positions` actually is: which resource it provides, at what
  rate, and how long it takes to capture. Rates are never hardcoded here.
"""

import json
import os

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


def classify_point(point, ebps_index, unresolved):
    """
    Turns one `point_positions` entry into the record written to the JSON.
    `unresolved` collects ebp names missing from ebps.json so the caller can report
    them instead of silently dropping information.
    """
    ebp_name = point.get('ebp_name')
    record = {
        'ebp': ebp_name,
        'ownerId': point.get('owner_id'),
    }

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
