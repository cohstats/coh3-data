# Company of Heroes 3 Data
Data and icons on all Company of Heroes 3 units / stuff in a developer friendly format.

### Goal 
Goal of this repository is to gather all the data from the game Company of Heroes 3. For example data for all units. As well as tools and scripts for gathering this data from the game. We beliave that open sourcing all the data and tools can only help the game and community.
Once we have the data it's up to anyone to build any web-site or apps and work with this data. But let's put all our heads together 

### Convention
- All the data should be converted into .json files
- Please provide all the scripts / add manuals how you get the data
   - We can expect a lot of updates from developers. So we will need to run our scripts many times.
- We shall do git tags to mark patch changes 
- The tags are in the format v1.0.7-1, where 1.0.7 should match the game patch version, -x (marks our revision). So v1.0.7-1 means game patch 1.0.7, data revision 1.

### Downloading the data 
If you want to utilize the data in the build / download them periodically. Please use this URL:  
`https://data.coh3stats.com/cohstats/coh3-data/${dataTag}/data/${dataFile}`
- `dataTag` is the [tag](https://github.com/cohstats/coh3-data/tags) in this repo 
- `dataFile` is the file from the [data](https://github.com/cohstats/coh3-data/tree/master/data) folder in this repo 

So for example the url could look like this: https://data.coh3stats.com/cohstats/coh3-data/v1.2.5-1/data/battlegroup.json

### Contribution 
We are looking for more help! If you would like to contribute in any way. Please rech out ot us here in the issues / on the discord https://discord.gg/jRrnwqMfkr

Also if you utilize the data, please give us shoutout! Thank you

## Automated data generation

You can use the GitHub workflow to automatically extract and process game data:

1. Go to the [Extract Data workflow](https://github.com/cohstats/coh3-data/actions/workflows/extract-data.yaml)
2. Click "Run workflow" button
3. Select the branch you want to run it against (usually `master`)
4. Click "Run workflow"

The workflow will:
- Download the latest game files
- Extract USC lang files from .sga using COH3-SGA-Extraction tool for all languages (en, fr, de, it, ja, ko, pl, pt-br, zh-hans, es, zh-hant, tr, cs)
- Process UCS files into JSON using `scripts/ucs-to-json.py` which converts the raw localization data into structured JSON files
- Extract and process ReferenceAttributes using AOEMods.Essence tool, which:
  - Unpacks ReferenceAttributes.sga into XML files
  - Converts XML data to JSON using `scripts/xml-to-json/main.py`
- Extract multiplayer map data from ScenariosMP.sga into `data/mp-maps.json` using `scripts/mp-maps/main.py`
- Create a new branch with changes
- Submit a Pull Request with the updates

Alternatively, you can still generate the data manually following the steps in the "How to generate the data" section above.

## How to generate the data

1. Open Company of Heroes 3 Essence Editor (it's located in your COH3 instalaltion folder). 
2. One file ReferenceAttributes.sga `...\Company of Heroes 3\anvil\archives\ReferenceAttributes.sga`
3. Click on the attrib field, right click, extract   
![image](https://user-images.githubusercontent.com/8086995/226179199-855c6ea5-5336-4df9-941c-3dc4f4dc0ad0.png)

4. Delete content of folder `xml` in this repo,
5. Extract it into folder `xml` of this repository. Should look like this:  
![image](https://user-images.githubusercontent.com/8086995/226179287-a61f956c-ff99-456f-a679-faf1251ae18a.png)

The **locstrings** must be exported as well, but requires the following steps:

1. Within the Essence Editor, click **"Attributes"** in the menu panel then click **"Open Attributes"**. Wait for it to completely load.
2. Open any attribute file (ebps is opened by default) then click **"View"** -> **Show LocString Report...** in the menu panel.
3. With the opened locstring table, select the first column then scroll to the last one and press "Shift" to select all (alternatively Ctrl + A). Then right click, copy or Ctrl + C then paste the content inside the `xml/loc_english/locale.txt` file of this repository.

### Convert the data

1. Go into folder `cd scripts/xml-to-json`. 
2. Run Python script main.py. You need python3. Like this `python main.py`, you should see this result:  
![image](https://user-images.githubusercontent.com/8086995/226179423-711db84e-9cb4-41e7-92de-e2341b9130ba.png)
3. Check the folder, you should see exported files. 

Hint: `python main.py -no_bl` disables blacklist filter and generates complete JSON files. However, when possible,
the filtered JSON files should be used to reduce file size. 

You can verify the changes by running command `git diff`

## Changes after the patch
1. Generate the data into folder `/data`
2. Make an MR with the changes 

The folder /data should always have the stable export of the data. 

## Folder `chunked`
Folder `chunked` has the big json files split to a smaller files for better manipulation.

## Multiplayer maps (`data/mp-maps.json`)

Map data comes from a different archive than the attributes: `...\Company of Heroes 3\anvil\archives\ScenariosMP.sga`.
Every scenario in it ships a small `.info` file (a plain text Lua table) holding the map name,
description, size, player slots and the position of every resource point.

Generate it with one command - the script unpacks the archive with the same AOEMods.Essence
CLI the workflow already uses, reads the `.info` files, then removes the unpacked data again:

```
python scripts/mp-maps/main.py --game-path "D:\SteamLibrary\steamapps\common\Company of Heroes 3"
```

Note that unpacking needs a few GB of free disk space and takes a few minutes; the archive is
about 1 GB and AOEMods.Essence cannot extract single files from it.

Useful options:
- `--essence-cli <path>` - the tool defaults to `tools/AOEMods.Essence/AOEMods.Essence.CLI.exe`,
  so unzip `tools/AOEMods.Essence-0.7.0.zip` first (or point at your own copy).
- `--locstring <path>` - defaults to `data/locales/en-locstring.json`. **Generate the locale data
  and `data/ebps.json` first**, otherwise map names will come out empty: a map added by the
  latest patch has no locstring id in an older `en-locstring.json`. A raw `anvil.en.ucs` is
  accepted here too.
- `--scenarios-dir <path>` - skip unpacking and read an already unpacked scenarios folder.
- `--unpack-dir <path>` / `--keep-unpacked` - keep the unpacked archive around instead of
  using a temporary directory.
- `--min-maps <n>` - the script fails if fewer than this many scenarios were found (default 60),
  so a broken extraction cannot silently produce a near-empty data file.
- `--include-test` - also export the cinematic/test scenarios that are normally skipped.

### What is in the file

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
- `points` - every point with its `ebp` name, category, tier, footprint `shape`, `x`/`y`
  position, income and capture time. Enough to draw a map overlay.
- `mapSize` is the full world size from the `.info`. `playableAreaEstimate` is derived from the
  bounding box of all points, so it is an estimate, not authored data.

Minimap images are **not** exported. The `*_mm_generated.rrtex` / `*_mm_handmade.rrtex` files
are listed per map in `minimapFiles`, but AOEMods.Essence 0.7.0 cannot decode them
(`RRTexDataTman.unknown6 not 1`, then an unsupported compression error) - COH3 uses a newer
RRTex variant.


## How to add/fix missing data not delivered by the Essence Editor

Some times it is nessecary to add some modifications to the XML as not all informations are delivered by relic. 
E.g. Stormtroopers are spawned with an lmg but there is no lmg member referenced within the loadout of the sbps. 
For that we created a CoH3 tuning mod which can be adoptet to overwrite missing information.

1. Open the mod from the projects `xml` directory with the Essence Editor
![image](https://user-images.githubusercontent.com/682343/229565471-1b457592-1276-4df8-8cab-21b31e52d6a3.png)

2. Clone the attribute file that needs to be modified and assign a name. If the mod file has the same name as the original file, the
extensions will overwrite extensions from the orginal otherwise,
a new json object will be created for that element. 
![image](https://user-images.githubusercontent.com/682343/229566966-4ce0b48c-314e-44d3-b4e0-5b7292b0b6b2.png)
![image](https://user-images.githubusercontent.com/682343/229567655-93690d6b-eeb5-4faa-b732-195fc8675bac.png)

3. Modify the cloned file which will appear in the corresponding Mod directory. You can also delete some extensions which are not required at all
to reduce traffic. 
![image](https://user-images.githubusercontent.com/682343/229568348-a7d77d4b-0a19-4e25-967d-7bc66fd3a812.png)

4. Save the mod. When the steps of `How to generate data` are performed, the modifications will be added or overwrite the original data
during the json generation process (see step 6 above). 

Hint: Overwriting can be skipped during script execution via `-no_mod` flag. Be aware after patches, the overwriting mod might need to be
adopted to reflect Relics patch changes. Thus, choose the files to modify wisely. 








### References:
Big thanks to all open source tools focused on Relic games.
https://github.com/RobinKa/RGDReader/tree/master/RRTexConverter
