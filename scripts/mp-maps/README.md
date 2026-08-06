# Multiplayer maps (`data/mp-maps.json`)

Map data comes from a different archive than the attributes: `...\Company of Heroes 3\anvil\archives\ScenariosMP.sga`.
Every scenario in it ships a small `.info` file (a plain text Lua table) holding the map name,
description, size, player slots and the position of every resource point.

**The `.info` point list is not trusted.** It is a summary the editor writes on save and it goes
stale, so the resource points are re-read from the scenario's own binary data and the `.info`
values are overwritten. See [Why the points come from the scenario, not the `.info`](#why-the-points-come-from-the-scenario-not-the-info).

## Generating the data

This is a two step process. The script **does not unpack the archive** - unpacking is by far the
slowest part, so it is done separately (in the workflow it is its own step) and the script only
reads the already unpacked `.info` files.

1. Unpack `ScenariosMP.sga` with the AOEMods.Essence CLI (unzip `tools/AOEMods.Essence-0.7.0.zip`
   first, or use your own copy):

   ```
   tools\AOEMods.Essence\AOEMods.Essence.CLI.exe sga-unpack ^
     "D:\SteamLibrary\steamapps\common\Company of Heroes 3\anvil\archives\ScenariosMP.sga" ^
     .\scenarios
   ```

2. Build the JSON:

   ```
   python scripts/mp-maps/main.py --scenarios-dir ./scenarios
   ```

`scenarios/` is gitignored; delete it when you are done.

Unpacking needs a few GB of free disk space (the archive is about 1 GB, the output about 4 GB)
and takes a few minutes. AOEMods.Essence cannot extract single files, so the whole archive has
to come out.

**Unpack to a fast local disk.** On GitHub Windows runners the workspace is the fast local SSD
(`D:`) while the system temp directory is on the OS disk (`C:`); unpacking this archive to `C:`
ran for over 105 minutes without finishing, versus about 5 minutes on `D:`.

### Options

- `--scenarios-dir <path>` - the unpacked archive. The unpack root, its `scenarios/` folder or
  the `multiplayer/` folder are all accepted. Defaults to `scenarios/` in the repo root.
- `--locstring <path>` - defaults to `data/locales/en-locstring.json`. **Generate the locale data
  and `data/ebps.json` first**, otherwise map names will come out empty: a map added by the
  latest patch has no locstring id in an older `en-locstring.json`. A raw `anvil.en.ucs` is
  accepted here too.
- `--ebps <path>` - defaults to `data/ebps.json`. The smaller `data/chunked/ebps/*.json` files
  are used automatically when they exist.
- `--output <path>` - defaults to `data/mp-maps.json`.
- `--min-maps <n>` - the script fails if fewer than this many scenarios were found (default 60),
  so a broken extraction cannot silently produce a near-empty data file.
- `--include-test` - also export the cinematic/test scenarios that are normally skipped.
- `--dump-info-dir <path>` - also copy the raw `.info` files there, for debugging.

## In the workflow

[`.github/workflows/extract-data.yaml`](../../.github/workflows/extract-data.yaml) does the same
two steps: **Unpack ScenariosMP.sga** runs `sga-unpack` into `.\scenarios`, then **Extract
Multiplayer Maps** runs this script against it and a later step deletes the directory. Keeping
the unpack in the workflow means a hang shows up as a slow step with its own timeout rather than
as a silent stall inside Python. Same approach as
[`cohstats/coh3-cdn`](https://github.com/cohstats/coh3-cdn/blob/master/.github/workflows/extract-map-images.yaml).

The map step must run after the UCS step (for `anvil.en.ucs`) and after the ReferenceAttributes
step (for `data/ebps.json`) - the map data is cross-referenced against both.

### Do not download the whole game in that job

The unpack step is very sensitive to how much was written to the runner's `D:` drive before it.
When the workflow downloaded the full ~34 GB game with SteamCMD, the unpack of this 1.07 GB
archive never finished inside a 20-25 minute timeout - and the 5 second cleanup afterwards showed
it had barely written anything. `cohstats/coh3-cdn` hit the same wall and measured it on identical
runners with the identical tool and archive:

| coh3-cdn run | Download method | `sga-unpack` duration |
| --- | --- | --- |
| 2026-05-12 | SteamCMD, full ~34 GB game | 30m16s |
| 2026-05-24 | DepotDownloader + filelist, ~1 GB | 6m29s |
| 2026-07-29 | DepotDownloader + filelist, ~1 GB | 5m23s |

The only change between the first two runs was the commit *"Try to migrate to depot downloader"*.
This repo now does the same: [`.github/workflows/coh3-filelist.txt`](../../.github/workflows/coh3-filelist.txt)
limits the download to `RelicCoH3.exe` and the four archives the workflow reads. Keep it that way -
switching back to a full game download will make the unpack time out again.

## What is in the file

Keyed by map id (the `.info` filename), plus a `__meta` block with counts. Cinematic and test
scenarios (`*_video`, `*_defend_01`, `[TEST] ...`) are dropped; everything else is **tagged**
rather than filtered, so nothing playable is lost:

- `category` - `mp` for normal multiplayer maps, `hoff` for the co-op "Hold Off" maps.
- `isLobbyVisible` - whether the game shows the map in the lobby.
- `isCommunity` - community made map (`map_origin = 2`), also reflected in the `folder` path.

Most consumers want `category == "mp" && isLobbyVisible`.

Other fields worth knowing about:
- `name` and `description` each hold `{ "locstring": "11266017", "en": "(4) El Alamein" }`.
  Use `locstring` to look the text up in `data/locales/<code>-locstring.json` for other
  languages - but note **`locstring` can be `null`**, because a few maps store a literal
  English name in the `.info` instead of a locstring id. Always fall back to `en`.
  (The `.info` files also carry a `ScenarioDescriptionlong` field, but the game writes the
  same locstring id into it as into the short description on every scenario, so it is not
  exported.)
- `resources.counts` / `resources.countsByTier` - number of fuel, munitions, strategic
  (manpower) and victory points, broken down by tier (`low`, `medium`, `high`, ...).
- `resources.incomePerMinute` - total manpower/fuel/munitions per minute if one player held
  every point on the map. Rates are read from `data/ebps.json`, not hardcoded, so they carry
  the game's own rounding: a medium fuel point is stored as `0.1667`/second and therefore
  reports `10.002`/minute rather than a clean `10`.
- `points[].kind` - the point category, or `other` for a non territory entity (map markers,
  co-op capture areas), or `unknown` if the `ebp` is missing from `data/ebps.json` - which
  means a patch added something new and the script logs a warning about it.
- `maxPlayers` / `teamLayout` / `teams` / `enabledSlots` describe the lobby. The `.info` files
  hold a 16 entry per slot table, but it is not exported: on every regular multiplayer map it
  is entirely derivable from `enabledSlots` (status is 0 for the first N slots and 1 after,
  team alternates 0/1, flags are constant) and would be ~19% of this file for no information.
  `aiSlots` keeps the one part that is not derivable - the co-op maps mark their enemy slots
  with a third status, which is also why they have more spawn points than lobby seats.
- `points` - every point with its `ebp` name, category, tier, `x`/`y` position, income and
  capture time. Enough to draw a map overlay. The `ebp` and position of a resource point
  come from the scenario itself, not from the `.info` - see
  [below](#why-the-points-come-from-the-scenario-not-the-info).
  `shape` is only present on the ~1/3 of points that use a non default footprint
  (`_smaller`, `_larger`, `_square7x7`, `_square10x10`, `_rect15x20`); absent means the
  default footprint. The `.info`'s `owner_id` is not exported at all: it is 0 on every
  territory point, and on a starting position it only encodes the lobby slot, which is
  already reported as `playerSlot`.
- `mapSize` is the full world size from the `.info`. `playableAreaEstimate` is derived from the
  bounding box of all points, so it is an estimate, not authored data.

Minimap images are **not** exported. The `*_mm_generated.rrtex` / `*_mm_handmade.rrtex` files
are listed per map in `minimapFiles`, but AOEMods.Essence 0.7.0 cannot decode them
(`RRTexDataTman.unknown6 not 1`, then an unsupported compression error) - COH3 uses a newer
RRTex variant. Map images are handled by
[`cohstats/coh3-cdn`](https://github.com/cohstats/coh3-cdn) instead.

## Why the points come from the scenario, not the `.info`

`point_positions` in a `.info` is written by the editor when the map is saved, and on a
handful of maps it never caught up with the map itself. On `twin_beach_2p_mkii` it calls all
five fuel points `territory_fuel_point_medium`, while the map really holds two medium ones
(+10 fuel) and three `territory_fuel_point_extra_low` (+8) - which is what you see in game.

The entities the game actually loads live in `DATAENTI` chunks of the scenario's Relic Chunky
files, and `layer_parser.py` reads them from both places they can appear:

- `<map>/<map>/*.layer` - one file per editor layer. Usually `territory.layer` or
  `territorylayout.layer`, but the layer names are per map, so every `.layer` is scanned.
- `<map>/<map>.scenario` - the main scenario chunky. `black_gold_8p` keeps every point here
  and has no territory layer at all; `torrente_4p_mkiii` keeps most in a layer and three here.
  Both sources are always read and merged, duplicates collapsed.

`reconcile_with_layers()` in `map_utils.py` then matches each `.info` point to its entity by
nearest position (greedy, within `MATCH_RADIUS` = 10 units) and takes the entity's `ebp_name`
and coordinates. 66 of 78 scenarios match to the millimetre; the largest genuine drift is 8.2
units on `across_the_rhine_6p`, and the closest two points on any shipped map are 25.9 units
apart, so the radius cannot reach a neighbouring point. Anything that does not match on either
side keeps its `.info` values and is logged as a warning.

Starting positions are not touched - they only exist in the `.info`.

Nine co-op `hoff_*` maps, the cinematic scenarios and the `hill_400_8p` stub ship no territory
entities at all and fall back to the `.info` unchanged; the script lists them on stdout.

Renames found on build 48837 (all logged as warnings when the script runs):

| map | change | effect |
| --- | --- | --- |
| `twin_beach_2p_mkii` | 3 fuel `medium` -> `extra_low` | fuel 50.01 -> 44.0 /min |
| `primosole_4p`, `primosole_6p` | 2 fuel `low` -> `medium`, 2 fuel `low` -> muni `low`, 1 muni `medium` -> fuel `low` | fuel 40.01 -> 45.01 /min |
| `egletons_2p` | 1 fuel `medium` -> `extra_low`, 1 muni `medium` -> `high` | fuel 41.99 -> 39.99, muni 97.05 -> 103.07 /min |
| `across_the_rhine_6p` | a fuel and a victory point swapped | positions only |
| `desert_airfield_6p_mkii`, `bologna_2p` | wrong footprint variant (`_square10x10`, `_rect15x20`) | `shape` and position only |
| `oasis_depot_8p` | 2 points up to 3.4 units off | position only |

## Files here

- `main.py` - CLI entry point: walks the scenarios, builds and writes the JSON.
- `lua_info_parser.py` - parser for the Lua table in a `.info` file.
- `layer_parser.py` - reads the real resource point entities out of the scenario's
  `.layer` / `.scenario` Relic Chunky files.
- `map_utils.py` - locstring/ebps lookups, the `.info`/scenario reconciliation, point
  classification and the per map summaries.
