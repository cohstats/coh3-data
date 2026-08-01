"""
Parser for Company of Heroes 3 scenario `.info` files.

A `.info` file sits next to every scenario inside `ScenariosMP.sga` and is a plain
text Lua table literal:

    HeaderInfo =
    {
        ScenarioDescription = "$11266018",
        mapsize = { 416, 416, },
        point_positions =
        {
            { ebp_name = "territory_fuel_point_medium", owner_id = 0, x = -112.9, y = -26.5, },
        },
        scenario_type = 1,
        visible_in_lobby = true,
    }

Only the subset of Lua used by the game is supported: table constructors, strings,
numbers, `true` / `false` / `nil` and trailing commas. No expressions, no function
calls, no `eval`. Unknown keys are preserved verbatim so that a field added by a
future game patch is never silently dropped.
"""

import re

TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<number>[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)
    | (?P<string>"(?:[^"\\]|\\.)*")
    | (?P<punct>[{}=,;])
    """,
    re.VERBOSE,
)

# Lua tables can be both keyed and array-like at the same time. When a single table
# mixes the two, the keyed entries win and the positional ones are parked here.
ARRAY_KEY = "__array"

STRING_ESCAPES = {
    'n': '\n',
    'r': '\r',
    't': '\t',
    'a': '\a',
    'b': '\b',
    'f': '\f',
    'v': '\v',
    '\\': '\\',
    '"': '"',
    "'": "'",
}


class LuaInfoParseError(ValueError):
    """Raised when a `.info` file cannot be parsed."""


def tokenize(text):
    """Turns `text` into a list of (kind, value) tuples, dropping whitespace."""
    tokens = []
    pos = 0
    end = len(text)

    while pos < end:
        match = TOKEN_RE.match(text, pos)
        if match is None:
            snippet = text[pos:pos + 40].replace('\n', '\\n')
            raise LuaInfoParseError(f'Unexpected character at offset {pos}: "{snippet}"')

        pos = match.end()
        kind = match.lastgroup
        if kind == 'ws':
            continue
        tokens.append((kind, match.group()))

    return tokens


def unescape_string(literal):
    """Turns a quoted Lua string literal into its value."""
    body = literal[1:-1]
    if '\\' not in body:
        return body

    out = []
    index = 0
    length = len(body)
    while index < length:
        char = body[index]
        if char != '\\' or index + 1 >= length:
            out.append(char)
            index += 1
            continue

        following = body[index + 1]
        # Unknown escapes are kept as-is: the game writes literal "\n" sequences
        # inside description strings and we must not corrupt them.
        out.append(STRING_ESCAPES.get(following, '\\' + following))
        index += 2

    return ''.join(out)


def parse_number(literal):
    """Ints stay ints so that ids and counts do not gain a `.0` in the JSON output."""
    if any(char in literal for char in '.eE'):
        return float(literal)
    return int(literal)


def _parse_value(tokens, index):
    if index >= len(tokens):
        raise LuaInfoParseError('Unexpected end of input, expected a value')

    kind, value = tokens[index]

    if kind == 'punct' and value == '{':
        return _parse_table(tokens, index + 1)
    if kind == 'string':
        return unescape_string(value), index + 1
    if kind == 'number':
        return parse_number(value), index + 1
    if kind == 'name':
        if value == 'true':
            return True, index + 1
        if value == 'false':
            return False, index + 1
        if value == 'nil':
            return None, index + 1
        # A bare identifier used as a value is not something the game emits, but
        # returning it as a string is friendlier than failing the whole file.
        return value, index + 1

    raise LuaInfoParseError(f'Expected a value, got {kind} "{value}"')


def _parse_table(tokens, index):
    """Parses a table body. `index` points just past the opening brace."""
    mapping = {}
    array = []

    while True:
        if index >= len(tokens):
            raise LuaInfoParseError('Unexpected end of input inside a table')

        kind, value = tokens[index]

        if kind == 'punct' and value == '}':
            index += 1
            break

        if kind == 'punct' and value in ',;':
            index += 1
            continue

        # `key = value` when a name is followed by '='
        is_keyed = (
            kind == 'name'
            and index + 1 < len(tokens)
            and tokens[index + 1] == ('punct', '=')
        )

        if is_keyed:
            key = value
            parsed, index = _parse_value(tokens, index + 2)
            mapping[key] = parsed
        else:
            parsed, index = _parse_value(tokens, index)
            array.append(parsed)

    if mapping and array:
        mapping[ARRAY_KEY] = array
        return mapping, index
    if mapping:
        return mapping, index
    return array, index


def parse_info(text):
    """
    Parses the contents of a `.info` file and returns the `HeaderInfo` table
    as a dict. Raises LuaInfoParseError on malformed input.
    """
    tokens = tokenize(text)
    if not tokens:
        raise LuaInfoParseError('Empty .info file')

    index = 0
    result = None

    # The file is a sequence of `Name = value` assignments. In practice there is
    # only ever `HeaderInfo`, but loop so an extra assignment does not break us.
    while index < len(tokens):
        kind, value = tokens[index]
        if kind != 'name':
            raise LuaInfoParseError(f'Expected an assignment target, got {kind} "{value}"')
        if tokens[index + 1:index + 2] != [('punct', '=')]:
            raise LuaInfoParseError(f'Expected "=" after "{value}"')

        parsed, index = _parse_value(tokens, index + 2)
        if value == 'HeaderInfo':
            result = parsed

        # Skip any separator between top level assignments.
        while index < len(tokens) and tokens[index] in (('punct', ','), ('punct', ';')):
            index += 1

    if result is None:
        raise LuaInfoParseError('No HeaderInfo table found')
    if not isinstance(result, dict):
        raise LuaInfoParseError('HeaderInfo is not a keyed table')

    return result


def parse_info_file(path):
    """Reads and parses a `.info` file. Community maps contain the odd stray byte,
    hence errors='replace' rather than a hard failure."""
    with open(path, 'r', encoding='utf-8', errors='replace') as info_file:
        return parse_info(info_file.read())
