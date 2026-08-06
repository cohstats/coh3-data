"""
Reads the real entity placements out of a scenario's Relic Chunky files.

The `.info` file next to every scenario also lists the resource points, but it is a
summary the editor writes on save and it goes stale: on `twin_beach_2p_mkii` it calls
all five fuel points `territory_fuel_point_medium` while the map actually holds two
medium ones and three `territory_fuel_point_extra_low` (+10 vs +8 fuel in game). The
entities parsed here are what the game loads, so they win over the `.info`.

Entities live in `DATAENTI` chunks, which turn up in two places depending on how the
map was authored - both are read and the results merged:

* `<map>/<map>/*.layer` - one Chunky file per editor layer. Most maps keep their
  resource points in a `territory.layer` / `territorylayout.layer`, but the layer
  names are per map and a few maps split them across several layers.
* `<map>/<map>.scenario` - the main scenario Chunky. Some maps (`black_gold_8p`)
  have no territory layer at all and keep every point here; others (`torrente_4p_mkiii`)
  keep most points in a layer and a few here.

A `DATAENTI` chunk body is:

    uint32  guid length (always 16)
    bytes   guid
    uint32  ebp name length
    bytes   ebp name, e.g. "territory_fuel_point_extra_low"
    float32 3x3 rotation matrix
    float32 x, height, z
    float32 scale

Note the axis order: the `.info` calls the *third* float `y`, so `entity["y"]` here is
the Chunky's `z` and matches the `.info` directly. The height goes into `height`.
"""

import os
import re
import struct

ENTITY_CHUNK = b'DATAENTI'

# `DATAENTI` is eight arbitrary bytes as far as a 40 MB binary is concerned, so every
# field is range checked before a hit is accepted as an entity.
GUID_LENGTH = 16
MAX_NAME_LENGTH = 128
# 3x3 rotation + x/height/z + scale, as float32.
TRANSFORM_LENGTH = 13 * 4
NAME_RE = re.compile(rb'^[A-Za-z0-9_\-\.]+$')

# Entities that can be a resource point. Everything else in a layer (buildings, cover,
# props) is ignored: this parser only exists to correct the `.info` point list.
TERRITORY_PREFIXES = ('territory_', 'hoff_territory')


def is_territory_entity(ebp_name):
    return ebp_name.startswith(TERRITORY_PREFIXES)


def parse_entities(path):
    """
    Returns `[{'ebp': str, 'x': float, 'y': float, 'height': float}, ...]` for every
    territory entity in one Chunky file. Malformed hits are skipped rather than raised
    on - a false `DATAENTI` match inside compressed data is expected, not exceptional.
    """
    with open(path, 'rb') as chunky_file:
        data = chunky_file.read()

    entities = []
    for match in re.finditer(re.escape(ENTITY_CHUNK), data):
        entity = _parse_entity_chunk(data, match.end())
        if entity is not None and is_territory_entity(entity['ebp']):
            entities.append(entity)

    return entities


def _parse_entity_chunk(data, offset):
    """Parses one `DATAENTI` chunk; `offset` points just past the chunk type."""
    # Chunk header after the type: version, body size, name length, then the name.
    header = data[offset:offset + 12]
    if len(header) < 12:
        return None

    _version, size, name_length = struct.unpack('<III', header)
    if size <= 0 or name_length > MAX_NAME_LENGTH:
        return None

    body = data[offset + 12 + name_length:offset + 12 + name_length + size]
    if len(body) < size:
        return None

    guid_length = struct.unpack('<I', body[0:4])[0]
    if guid_length != GUID_LENGTH:
        return None

    cursor = 4 + guid_length
    if cursor + 4 > size:
        return None

    ebp_length = struct.unpack('<I', body[cursor:cursor + 4])[0]
    cursor += 4
    if not 0 < ebp_length <= MAX_NAME_LENGTH or cursor + ebp_length + TRANSFORM_LENGTH > size:
        return None

    raw_name = body[cursor:cursor + ebp_length]
    if not NAME_RE.match(raw_name):
        return None
    cursor += ebp_length

    transform = struct.unpack('<13f', body[cursor:cursor + TRANSFORM_LENGTH])
    x, height, z = transform[9], transform[10], transform[11]

    return {
        'ebp': raw_name.decode('ascii'),
        'x': round(x, 5),
        'y': round(z, 5),
        'height': round(height, 5),
    }


def collect_scenario_entities(scenario_dir, map_id):
    """
    Every territory entity of one scenario, from its layers and its `.scenario`.

    Both sources are always read: a map can keep some points in a layer and the rest
    in the scenario. Duplicates (same ebp at the same spot) are collapsed, so a point
    present in both is counted once.
    """
    sources = []

    layer_dir = os.path.join(scenario_dir, map_id)
    if os.path.isdir(layer_dir):
        sources.extend(
            os.path.join(layer_dir, name)
            for name in sorted(os.listdir(layer_dir))
            if name.lower().endswith('.layer')
        )

    scenario_path = os.path.join(scenario_dir, map_id + '.scenario')
    if os.path.isfile(scenario_path):
        sources.append(scenario_path)

    entities = []
    seen = set()
    for path in sources:
        try:
            parsed = parse_entities(path)
        except OSError:
            continue

        for entity in parsed:
            key = (entity['ebp'], round(entity['x'], 2), round(entity['y'], 2))
            if key in seen:
                continue
            seen.add(key)
            entities.append(entity)

    return entities
