"""
Reads the authored territory sectors out of a scenario's `*_territory.override`.

Sectors are the regions *between* the resource points - the areas the game shades in
the tactical map and that decide which points are cut off. They are painted by hand in
the editor and stored per scenario, so unlike the point list they do not have to be
inferred from anything.

The file is a Relic Chunky:

    FOLDOLYR
      FOLDODAT
        FOLDDATA
          FOLDTRTY
            FOLDTCEL
              DATADATA   the cell grid
            FOLDSECT
              DATADATA   sector count
              FOLDSECT   one per sector
                DATADATA   bounding box, neighbours, base flag

`FOLDTCEL`'s `DATADATA` body is:

    uint32   width
    uint32   height
    uint32   width * height cell values, row major: 0 = no sector,
             otherwise the 1 based sector index
    uint8    width * height, a second grid whose meaning is not identified
             (see README) - parsed past, not exported

Each per sector `DATADATA` body is:

    uint16   minX, maxX, minY, maxY   bounding box in grid cells
    uint32   neighbour count
    uint32   neighbour sector ids, 1 based, same numbering as the cell values
    uint16   1 on a base (HQ) sector, 0 otherwise

The grid is always exactly `mapsize` from the `.info`, so one cell is one world unit,
and a cell at grid (gx, gy) covers world x in `[gx - width/2, gx + 1 - width/2]` - the
same coordinate space the `.info` uses for the resource points. That mapping was
verified rather than assumed: every one of the 198 starting positions across the
shipped maps falls inside a sector flagged as a base, and the per sector bounding box
recomputed from the cell grid matches the declared one exactly on all 46 maps.
"""

import struct

CHUNK_HEADER_LENGTH = 20
# "Relic Chunky\r\n\x1a\0" plus version and platform.
CHUNKY_HEADER_LENGTH = 0x18

# Chunk versions identify the two payloads we want; the surrounding folders are
# walked generically so an added sibling chunk cannot shift our parsing.
CELL_GRID_VERSION = 3001
SECTOR_VERSION = 3004

SECTOR_BBOX_LENGTH = 8
MAX_REASONABLE_NEIGHBOURS = 256


class TerritoryParseError(ValueError):
    """Raised when a `*_territory.override` is not shaped the way we expect."""


def _walk(data, start, end):
    """Yields (name, version, size, body_offset) for every chunk in a range."""
    position = start
    while position + CHUNK_HEADER_LENGTH <= end:
        kind = data[position:position + 4]
        name = data[position + 4:position + 8]
        if kind not in (b'FOLD', b'DATA'):
            return

        version, size, name_length = struct.unpack(
            '<III', data[position + 8:position + CHUNK_HEADER_LENGTH]
        )
        body = position + CHUNK_HEADER_LENGTH + name_length
        if body + size > end:
            return

        yield name, version, size, body
        if kind == b'FOLD':
            yield from _walk(data, body, body + size)
        position = body + size


def _parse_sector_record(data, body, size):
    """One per sector `DATADATA`: bounding box, neighbours, base flag."""
    if size < SECTOR_BBOX_LENGTH + 4:
        raise TerritoryParseError('sector record too short')

    min_x, max_x, min_y, max_y = struct.unpack('<4H', data[body:body + SECTOR_BBOX_LENGTH])
    cursor = body + SECTOR_BBOX_LENGTH
    count = struct.unpack('<I', data[cursor:cursor + 4])[0]
    cursor += 4

    if count > MAX_REASONABLE_NEIGHBOURS or cursor + 4 * count > body + size:
        raise TerritoryParseError(f'implausible neighbour count {count}')

    neighbours = struct.unpack(f'<{count}I', data[cursor:cursor + 4 * count]) if count else ()
    cursor += 4 * count

    tail = data[cursor:body + size]
    is_base = bool(struct.unpack('<H', tail[:2])[0]) if len(tail) >= 2 else False

    return {
        'bbox': (min_x, max_x, min_y, max_y),
        'neighbors': sorted(neighbours),
        'isBase': is_base,
    }


def parse_territory_file(path):
    """
    Returns `{'width', 'height', 'cells', 'sectors'}` or None when the file holds no
    cell grid. `cells` is a flat row major tuple of 1 based sector ids (0 = none) and
    `sectors` is indexed by `id - 1`.
    """
    with open(path, 'rb') as territory_file:
        data = territory_file.read()

    if not data.startswith(b'Relic Chunky'):
        raise TerritoryParseError(f'{path} is not a Relic Chunky file')

    grid = None
    sectors = []
    for name, version, size, body in _walk(data, CHUNKY_HEADER_LENGTH, len(data)):
        if name != b'DATA':
            continue
        if version == CELL_GRID_VERSION and grid is None:
            grid = (body, size)
        elif version == SECTOR_VERSION:
            sectors.append(_parse_sector_record(data, body, size))

    if grid is None:
        return None

    body, size = grid
    if size < 8:
        raise TerritoryParseError('cell grid chunk too short')

    width, height = struct.unpack('<2I', data[body:body + 8])
    cell_count = width * height
    # The uint8 grid that follows the ids is not exported, but it has to be there:
    # if it is missing the chunk is not what we think it is.
    expected = 8 + cell_count * 5
    if not 0 < cell_count <= 4096 * 4096 or size < expected:
        raise TerritoryParseError(
            f'cell grid {width}x{height} does not fit in {size} bytes'
        )

    cells = struct.unpack(
        f'<{cell_count}I', data[body + 8:body + 8 + cell_count * 4]
    )

    return {'width': width, 'height': height, 'cells': cells, 'sectors': sectors}
