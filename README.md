# Hex of Steel Mod Setup

This repository helps you bootstrap and maintain Hex of Steel mods with a repeatable workflow. It contains:

- `mod_folder_setup.py`: command-line scaffolder that clones the template folder into a fresh mod workspace with your metadata.
- `template/`: source files copied into each new mod project (C# project, template script, manifest, utilities).
- `template/hos_mod_utils.py`: utility script included in every scaffolded mod for fetching game DLLs, decompiling the vanilla assembly, building, and packaging your mod.

## Prerequisites

- Python 3.10 or newer available on your PATH.
- .NET SDK 6.0+ (needed for `dotnet build`).
- `ilspycmd` installed (available via [`dotnet tool install ilspycmd`](https://github.com/icsharpcode/ILSpy)).
- Hex of Steel installed.
- Internet access (for the first run) so Harmony can be downloaded from NuGet.

## Scaffolding a New Mod

The script duplicates the `template` folder and applies a handful of substitutions (manifest values, project name, etc.). Run it from the repository root:

```bash
python mod_folder_setup.py /path/to/MyMod \
  --mod-name "My Mod" \
  --mod-author "YourName" \
  --mod-description "Short description shown in the mod browser"
```

Flags:

- `destination` (positional): directory where the new mod should live. The script creates it if needed. Use `--force` to allow non-empty destinations.
- `--mod-name`: Display name used in the manifest and package folder.
- `--mod-author`: Author string for the manifest.
- `--mod-description`: Optional manifest description.

What the scaffolder does:

1. Copies files from `template/`, substituting placeholders with your metadata.
2. Creates an empty `assets/` directory inside the new mod.
3. Runs `hos_mod_utils.py --get-dlls` in the new mod root, which downloads Harmony, copies the game DLLs from your Hex of Steel installation, and decompiles `Assembly-CSharp.dll` into `decompiled/<version>/`.
4. Drops a `.env` file in the mod root so you can override detection paths later (only necessary if the tool can't detect the paths automatically).

After scaffolding, your mod folder contains everything needed to build or distribute the project.

> **Path detection safety.** Before any files are copied, the scaffolder now verifies it can find both the Hex of Steel `MODS` directory and the `Hex of Steel_Data/Managed` folder. If either location is missing, the script exits early with instructions to update the `.env` file.

## Using `hos_mod_utils.py`

Each generated mod includes `hos_mod_utils.py` at its root. It orchestrates common maintenance tasks:

```bash
python hos_mod_utils.py [options]
```

### Available Options

- `-g`, `--get-dlls`: Refresh the `Libraries/` directory by copying the required assemblies from the Hex of Steel install and download the latest Harmony Thin package. As part of this process, ILSpy decompiles the stock `Assembly-CSharp.dll` into `decompiled/<version>/`. Run this whenever the game updates.
- `-d`, `--deploy`: Build the C# project (via `dotnet build --configuration Release`) and stage the packaged mod under `package/`. Each package has the form `package/${mod_slug}-vX.Y.Z-N/<mod folder name>/` so it’s ready to drop into Hex of Steel.
- `-i`, `--install`: Copy the most recently deployed package into Hex of Steel’s `MODS` directory. This option only has an effect when combined with `--deploy`.

Examples:

Refresh libraries and decompile only:

```bash
python hos_mod_utils.py --get-dlls
```

Build and stage the package without installing:

```bash
python hos_mod_utils.py --deploy
```

Deploy and install in one step:

```bash
python hos_mod_utils.py --deploy --install
```

If no flags are provided, the script shows the help message.

### What `--deploy` Produces

When you run `--deploy`, the script:

1. Reads `Manifest.json` to capture the mod version.
2. Builds the C# project, producing `output/net48/<ModAssembly>.dll`.
3. Creates `package/${mod_slug}-v<version>-<n>/${mod_folder_name}/`, copying:
   - `Manifest.json`
   - Built DLL under `Libraries/`
   - All files from `assets/`.
4. Optionally installs the package (if `--install` is supplied).

You can zip the generated package folder and distribute it directly to players.

## Configuring Hex of Steel Paths via `.env`

Both `mod_folder_setup.py` and every generated `hos_mod_utils.py` read a local `.env` file before attempting to locate the Hex of Steel installation. The file ships with commented placeholders:

```
# HOS_MANAGED_DIR="/absolute/path/to/Hex of Steel/Hex of Steel_Data/Managed"
# HOS_MODS_PATH="/absolute/path/to/War Frogs Studio/Hex of Steel/MODS"
```

You can try to run the tool first to see if the tool is able to determine these path by itself. If it fails, adjust the paths in the .env folder.

Steps:

1. Edit the root `.env` file (or the copy inside an individual mod) and uncomment the variables that apply to your setup.
2. Provide absolute paths to the managed DLL folder and the MODS folder.
3. Re-run `mod_folder_setup.py` or `hos_mod_utils.py`; the scripts pick up the overrides automatically.

Environment variables exported in your shell take precedence over `.env`, so you can still override them per-session if needed.

## Project Template Notes

- The C# project targets `net48` and references the game’s assemblies. Harmony is downloaded lazily (first run of `--get-dlls`) and kept alongside the template for convenience.
- Add your custom scripts under `Scripts/` in the mod. The scaffolder renames `TemplateScript.cs` to `${mod_class_name}.cs` and updates the namespaces/identifiers to match your mod.
- Use the `assets/` folder for every content tweak Hex of Steel expects alongside your DLL—units, scenarios, countries, sounds, videos, wallpapers, etc. Mirror the directory layout that the Hex of Steel in-game mod creator generates (e.g., `assets/Maps`, `assets/Musics`, and so on); the deploy step copies this tree verbatim into the packaged mod so the game picks it up without extra work.

## Troubleshooting

- **Managed directory not found**: Set `HOS_MANAGED_DIR` in `.env` (or export it) to point at `Hex of Steel_Data/Managed`, then rerun the command so the DLL copy step can succeed.
- **MODS directory not found**: Set `HOS_MODS_PATH` in `.env` (or export it) to the directory Hex of Steel reads mods from.
- **`ilspycmd` missing**: Add it via `dotnet tool install --global ilspycmd` or update `PATH` so `hos_mod_utils.py` can call it.
- **No Harmony DLL**: The utility downloads the latest `lib.harmony.thin` package from NuGet. If you need the full Harmony build, replace the downloaded `0Harmony.dll` in `Libraries/` manually and the script will reuse it.
- **Build errors**: Confirm that .NET SDK 6.0 (or newer) is installed and `dotnet` is available. Unity assemblies require the mono fallback, so Windows-specific builds may fail without the right references.

## Contributing

Issues and PRs are welcome.

---

This tooling is not affiliated with War Frogs Studio; it’s community-maintained. Use at your own risk and always back up your game files before experimenting with mods.
