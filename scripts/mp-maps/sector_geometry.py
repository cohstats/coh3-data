"""
Turns the territory cell grid into polygon outlines that a client can draw directly.

The grid is a per cell sector id, so the exact outline of a sector is a staircase
along cell edges. Tracing it verbatim costs about 205 vertices per sector (1.9 MB of
JSON over all maps), and almost all of that is quantisation noise rather than authored
detail: the painted resolution is one world unit, so a step never says anything the
grid did not already round.

Simplifying is therefore worthwhile, but it cannot be done one sector at a time.
**77% of all sector boundary is shared with another sector**, and simplifying the same
border twice, once from each side, yields two slightly different lines - hairline
cracks and overlaps along three quarters of the overlay. So the boundary is first cut
into *arcs*:

* a maximal run of boundary edges separating the same pair of regions, cut again at
  junctions where more than two regions meet.

Each arc is simplified once and cached under a direction independent key, so the two
sectors either side of a border reuse the identical vertex list and stay welded
together. Rings are then reassembled from the simplified arcs.

Vertices come out in the same world coordinate space as `points[].x/y`, so a client
needs no conversion between the two: cell (gx, gy) has its corner at world
`(gx - width/2, gy - height/2)`. Grid dimensions equal `mapsize`, which is even on
every shipped map, so the coordinates stay whole numbers.
"""

import math

# Douglas-Peucker tolerance in world units. One unit is exactly one grid cell, i.e.
# the resolution the sector was painted at, so no simplified edge can stray further
# from the authored border than the border's own quantisation. It cuts the vertex
# count to ~18% (205 -> 36 per sector). Raising it to 2 saves little more (6%) and
# starts visibly rounding corners.
SIMPLIFY_TOLERANCE = 1.0

# Sectors that touch fewer cells than this are dropped. Painting leaves the odd
# stray cell behind; a handful of cells is not a region anyone can capture and would
# render as a speck.
MIN_SECTOR_CELLS = 4


def _boundary_edges(cells, width, height, target):
    """
    Directed edges around every cell belonging to `target`, wound consistently.

    Each entry maps a start corner to (end corner, neighbouring sector id), where the
    neighbour is 0 for empty space and off grid.
    """
    edges = {}
    for y in range(height):
        row = y * width
        for x in range(width):
            if cells[row + x] != target:
                continue

            up = cells[row - width + x] if y > 0 else 0
            right = cells[row + x + 1] if x + 1 < width else 0
            down = cells[row + width + x] if y + 1 < height else 0
            left = cells[row + x - 1] if x > 0 else 0

            if up != target:
                edges.setdefault((x, y), []).append(((x + 1, y), up))
            if right != target:
                edges.setdefault((x + 1, y), []).append(((x + 1, y + 1), right))
            if down != target:
                edges.setdefault((x + 1, y + 1), []).append(((x, y + 1), down))
            if left != target:
                edges.setdefault((x, y + 1), []).append(((x, y), left))

    return edges


def _trace_rings(edges):
    """
    Walks the directed edges into closed rings.

    Returns a list of `(vertices, labels)`; `labels[i]` is the sector on the far side
    of the edge leaving `vertices[i]`. A vertex where two diagonal cells of the same
    sector touch has two outgoing edges; taking them in turn splits the shape into
    separate rings there, which is what we want - a pinch point is not an interior.
    """
    remaining = {node: list(out) for node, out in edges.items()}
    rings = []

    while remaining:
        start = next(iter(remaining))
        vertices = []
        labels = []
        node = start

        while True:
            outgoing = remaining.get(node)
            if not outgoing:
                break

            following, label = outgoing.pop()
            if not outgoing:
                del remaining[node]

            vertices.append(node)
            labels.append(label)
            node = following
            if node == start:
                break

        # A closed ring needs at least four unit edges to enclose anything.
        if len(vertices) >= 4 and node == start:
            rings.append((vertices, labels))

    return rings


def _junctions(edges):
    """Corners where the boundary is not a simple pass through."""
    return {node for node, out in edges.items() if len(out) != 1}


def _split_into_arcs(vertices, labels, junctions):
    """
    Cuts one ring into arcs at every label change and at every junction corner.

    Returns a list of vertex lists; consecutive arcs share their end vertices. When a
    ring has no cut at all (a sector fully enclosed by one neighbour) the whole ring
    comes back as a single closed arc.
    """
    count = len(vertices)
    cuts = [
        index for index in range(count)
        if labels[index - 1] != labels[index] or vertices[index] in junctions
    ]

    if not cuts:
        return [list(vertices) + [vertices[0]]], True

    arcs = []
    for position, start in enumerate(cuts):
        end = cuts[(position + 1) % len(cuts)]
        length = (end - start) % count or count
        arcs.append([vertices[(start + step) % count] for step in range(length + 1)])

    return arcs, False


def _drop_collinear(points, closed):
    """Removes vertices that lie on the straight line between their neighbours."""
    if len(points) < 3:
        return list(points)

    if closed:
        body = points[:-1]
        kept = []
        for index in range(len(body)):
            ax, ay = body[index - 1]
            bx, by = body[index]
            cx, cy = body[(index + 1) % len(body)]
            if (bx - ax) * (cy - by) != (by - ay) * (cx - bx):
                kept.append((bx, by))
        return kept + [kept[0]] if kept else []

    kept = [points[0]]
    for index in range(1, len(points) - 1):
        ax, ay = points[index - 1]
        bx, by = points[index]
        cx, cy = points[index + 1]
        if (bx - ax) * (cy - by) != (by - ay) * (cx - bx):
            kept.append((bx, by))
    kept.append(points[-1])
    return kept


def _perpendicular_distance(point, start, end):
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _douglas_peucker(points, tolerance):
    """Iterative Douglas-Peucker; iterative so a long arc cannot blow the stack."""
    if len(points) < 3:
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        worst = tolerance
        split = None
        for index in range(first + 1, last):
            distance = _perpendicular_distance(points[index], points[first], points[last])
            if distance > worst:
                worst, split = distance, index

        if split is not None:
            keep[split] = True
            stack.append((first, split))
            stack.append((split, last))

    return [point for point, keeper in zip(points, keep) if keeper]


def _rotate_to_pivot(cycle):
    """Rotates a closed vertex cycle to start at its lowest, leftmost vertex."""
    pivot = min(range(len(cycle)), key=lambda index: (cycle[index][1], cycle[index][0]))
    return cycle[pivot:] + cycle[:pivot]


def _arc_key(arc, closed):
    """
    A key that identifies an arc regardless of which side it is traced from.

    An open arc is pinned by its endpoints, so reversing is the only ambiguity. A
    closed one - a sector fully enclosed by a single neighbour - can also start
    anywhere in the cycle, so it is rotated to a fixed vertex first. Without that the
    two sides would miss each other in the cache and be simplified independently,
    which is exactly the crack this is here to prevent.
    """
    if not closed:
        forward = tuple(arc)
        return min(forward, forward[::-1])

    body = arc[:-1] if len(arc) > 1 and arc[0] == arc[-1] else list(arc)
    forward = tuple(_rotate_to_pivot(body))
    backward = tuple(_rotate_to_pivot(body[::-1]))
    return min(forward, backward)


def _simplify_arc(arc, closed, tolerance, cache):
    """
    Simplifies one arc, reusing the result when the same arc is met from the other side.

    The two sectors either side of a border therefore get the exact same vertices and
    their outlines stay welded together. The returned arc always runs in the direction
    of `arc` itself, whichever direction the cached copy was built in.
    """
    key = _arc_key(arc, closed)
    cached = cache.get(key)

    if cached is None:
        if closed:
            body = arc[:-1] if len(arc) > 1 and arc[0] == arc[-1] else list(arc)
            # Endpoints of a closed arc are not pinned by a neighbour, so start from a
            # stable vertex and keep the cycle closed while simplifying.
            body = _rotate_to_pivot(body)
            collapsed = _drop_collinear(body + [body[0]], True)
        else:
            collapsed = _drop_collinear(arc, False)

        cached = _douglas_peucker(collapsed, tolerance) if tolerance else collapsed
        cache[key] = cached

    if closed or not cached:
        return list(cached)

    # Open arcs are pinned by their endpoints, so matching the start vertex is enough.
    return list(reversed(cached)) if cached[0] != arc[0] else list(cached)


def _ring_area(ring):
    total = 0.0
    for index in range(len(ring)):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def build_sector_polygons(territory, tolerance=SIMPLIFY_TOLERANCE):
    """
    Returns `{sector_id: {'rings': [...], 'cellCount': int}}` in world coordinates.

    Rings are closed implicitly (the repeated last vertex is dropped) and ordered
    largest first, so the first ring of a sector is its outline and any further ring
    is a hole or a detached piece.
    """
    cells = territory['cells']
    width, height = territory['width'], territory['height']
    half_width, half_height = width / 2.0, height / 2.0

    counts = {}
    for value in cells:
        if value:
            counts[value] = counts.get(value, 0) + 1

    arc_cache = {}
    out = {}
    for sector_id in sorted(counts):
        if counts[sector_id] < MIN_SECTOR_CELLS:
            continue

        edges = _boundary_edges(cells, width, height, sector_id)
        junctions = _junctions(edges)
        rings = []

        for vertices, labels in _trace_rings(edges):
            arcs, closed = _split_into_arcs(vertices, labels, junctions)
            ring = []
            for arc in arcs:
                simplified = _simplify_arc(arc, closed, tolerance, arc_cache)
                # Every arc ends where the next one starts, and the last one closes
                # back onto the first, so each arc contributes all but its last vertex.
                ring.extend(simplified[:-1])

            if len(ring) >= 3:
                rings.append(ring)

        if not rings:
            continue

        rings.sort(key=lambda ring: -abs(_ring_area(ring)))
        out[sector_id] = {
            'cellCount': counts[sector_id],
            'rings': [
                [[_round(x - half_width), _round(y - half_height)] for x, y in ring]
                for ring in rings
            ],
        }

    return out


def _round(value):
    """Grid corners are whole world units on every shipped map; keep them integers."""
    return int(value) if float(value).is_integer() else round(value, 3)


def sector_at(territory, x, y):
    """The 1 based sector id covering a world position, or None."""
    grid_x = int(math.floor(x + territory['width'] / 2.0))
    grid_y = int(math.floor(y + territory['height'] / 2.0))
    if not (0 <= grid_x < territory['width'] and 0 <= grid_y < territory['height']):
        return None

    value = territory['cells'][grid_y * territory['width'] + grid_x]
    return value or None
