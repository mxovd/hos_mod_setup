#!/usr/bin/env python3
"""Build and package the ${mod_name} mod for distribution."""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

MOD_NAME = "${mod_name}"
PACKAGE_PREFIX = "${package_prefix}"
PROJECT_FILENAME = "${project_filename}"
OUTPUT_DLL_NAME = "${output_dll_name}"
MOD_FOLDER_NAME = "${mod_folder_name}"

GAME_MANAGED_DIR = Path.home() / (
    ".var/app/com.valvesoftware.Steam/.steam/steam/steamapps/common/Hex of Steel/"
    "Hex of Steel_Data/Managed"
)

REQUIRED_DLLS = [
    "Assembly-CSharp.dll",
    "Newtonsoft.Json.dll",
    "PhotonUnityNetworking.dll",
    "LeTai.TranslucentImage.dll",
    "Unity.TextMeshPro.dll",
    "UnityEngine.dll",
    "UnityEngine.AudioModule.dll",
    "UnityEngine.CoreModule.dll",
    "UnityEngine.ImageConversionModule.dll",
    "UnityEngine.TextRenderingModule.dll",
    "UnityEngine.UI.dll",
    "UnityEngine.UIModule.dll",
]


HARMONY_PACKAGE_ID = "lib.harmony.thin"
NUGET_FLAT_BASE_URL = "https://api.nuget.org/v3-flatcontainer"


def download_latest_harmony() -> tuple[str, bytes]:
    metadata_url = f"{NUGET_FLAT_BASE_URL}/{HARMONY_PACKAGE_ID}/index.json"
    try:
        with urlrequest.urlopen(metadata_url, timeout=30) as response:
            metadata = json.load(response)
    except urlerror.URLError as error:
        raise SystemExit(
            f"Failed to query Harmony versions from {metadata_url}: {error}"
        ) from error

    versions = metadata.get("versions")
    if not versions:
        raise SystemExit("No versions returned for lib.harmony.thin from NuGet")

    version = versions[-1]
    package_url = (
        f"{NUGET_FLAT_BASE_URL}/{HARMONY_PACKAGE_ID}/{version}/"
        f"{HARMONY_PACKAGE_ID}.{version}.nupkg"
    )

    try:
        with urlrequest.urlopen(package_url, timeout=60) as response:
            package_bytes = response.read()
    except urlerror.URLError as error:
        raise SystemExit(
            f"Failed to download Harmony package {package_url}: {error}"
        ) from error

    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.lower().endswith("0harmony.dll") and name.startswith("lib/")
        ]
        if not candidates:
            raise SystemExit("Harmony package did not contain 0Harmony.dll")

        preferred_targets = [
            "lib/net48/",
            "lib/net472/",
            "lib/net452/"
        ]

        def select_key(path: str) -> tuple[int, int]:
            lower = path.lower()
            for index, marker in enumerate(preferred_targets):
                if marker in lower:
                    return (index, len(path))
            return (len(preferred_targets), len(path))

        selected = min(candidates, key=select_key)
        dll_bytes = archive.read(selected)

    return version, dll_bytes


def ensure_harmony_library(libraries_dir: Path) -> None:
    harmony_path = libraries_dir / "0Harmony.dll"
    if harmony_path.exists():
        return

    libraries_dir.mkdir(parents=True, exist_ok=True)
    version, dll_bytes = download_latest_harmony()
    harmony_path.write_bytes(dll_bytes)
    print(f"Downloaded Harmony {version} to {harmony_path}")


def run(command: list[str], *, cwd: Path) -> None:
    """Execute an external command and raise on failure."""
    subprocess.run(command, cwd=cwd, check=True)


def refresh_libraries(root: Path) -> None:
    if not GAME_MANAGED_DIR.exists() or not GAME_MANAGED_DIR.is_dir():
        raise SystemExit(f"Managed directory not found at {GAME_MANAGED_DIR}")

    libraries_dir = root / "Libraries"
    libraries_dir.mkdir(parents=True, exist_ok=True)

    ensure_harmony_library(libraries_dir)

    for dll_path in libraries_dir.glob("*.dll"):
        if dll_path.name.lower() != "0harmony.dll":
            dll_path.unlink(missing_ok=True)

    for dll_name in REQUIRED_DLLS:
        source = GAME_MANAGED_DIR / dll_name
        if not source.exists():
            raise SystemExit(f"Required library {dll_name} missing at {source}")
        shutil.copy2(source, libraries_dir / dll_name)


def compute_package_dir(package_root: Path, mod_version: str) -> Path:
    prefix = f"{PACKAGE_PREFIX}-v{mod_version}-"
    highest_index = 0

    if package_root.exists():
        for entry in package_root.iterdir():
            name = entry.name
            if not name.startswith(prefix):
                continue

            suffix = name[len(prefix):]
            if entry.is_file():
                suffix = suffix.split(".", 1)[0]

            if suffix.isdigit():
                highest_index = max(highest_index, int(suffix))

    next_index = highest_index + 1
    return package_root / f"{prefix}{next_index}"


def parse_args() -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(description=f"Build and package the {MOD_NAME} mod.")
    parser.add_argument(
        "--deploy",
        "-d",
        action="store_true",
        help="Build the project and stage the packaged mod in the package directory.",
    )
    parser.add_argument(
        "--install",
        "-i",
        action="store_true",
        help="After a successful deploy, copy the build into the local Hex of Steel mods directory.",
    )
    parser.add_argument(
        "--get-dlls",
        "-g",
        action="store_true",
        help="Decompile Assembly-CSharp.dll and refresh Libraries from the Hex of Steel installation.",
    )
    return parser.parse_args(), parser


def install_package(package_root: Path) -> Path:
    install_root = (
        Path.home()
        / ".var"
        / "app"
        / "com.valvesoftware.Steam"
        / "config"
        / "unity3d"
        / "War Frogs Studio"
        / "Hex of Steel"
        / "MODS"
    )
    target_path = install_root / package_root.name

    install_root.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        shutil.rmtree(target_path)
    shutil.copytree(package_root, target_path)
    return target_path


def build_and_package(root: Path, install: bool) -> None:
    manifest_path = root / "Manifest.json"
    project_path = root / PROJECT_FILENAME
    output_dll = root / "output" / "net48" / OUTPUT_DLL_NAME
    package_root = root / "package"
    assets_dir = root / "assets"

    refresh_libraries(root)

    if not manifest_path.exists():
        raise SystemExit(f"manifest.json not found at {manifest_path}")

    if not project_path.exists():
        raise SystemExit(f"Project file not found at {project_path}")

    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)

    mod_version = manifest.get("modVersion", "0.0.0")

    package_root.mkdir(parents=True, exist_ok=True)

    package_dir = compute_package_dir(package_root, mod_version)
    target_root = package_dir / MOD_FOLDER_NAME
    libraries_dir = target_root / "Libraries"

    package_dir.mkdir(parents=True, exist_ok=True)
    target_root.mkdir(parents=True, exist_ok=True)
    libraries_dir.mkdir(parents=True, exist_ok=True)
    # Additional directories get created as needed when copying assets.

    run(["dotnet", "build", str(project_path), "--configuration", "Release"], cwd=root)

    if not output_dll.exists():
        raise SystemExit(f"Build completed but DLL missing at {output_dll}")

    shutil.copy2(manifest_path, target_root / "Manifest.json")
    shutil.copy2(output_dll, libraries_dir / output_dll.name)

    if assets_dir.exists():
        shutil.copytree(assets_dir, target_root, dirs_exist_ok=True)

    print(f"Package created at {package_dir}")

    if install:
        installed_path = install_package(target_root)
        print(f"Mod installed to {installed_path}")


def run_decompilation(root: Path) -> Path:
    refresh_libraries(root)

    assembly_path = GAME_MANAGED_DIR / "Assembly-CSharp.dll"

    if not assembly_path.exists():
        raise SystemExit(f"Assembly-CSharp.dll not found at {assembly_path}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="hos_decompile_", dir="/tmp"))

    try:
        command = [
            "ilspycmd",
            str(assembly_path),
            "-p",
            "-o",
            str(tmp_dir),
        ]
        run(command, cwd=root)

        manager_path = tmp_dir / "MultiplayerManager.cs"
        if not manager_path.exists():
            candidates = list(tmp_dir.rglob("MultiplayerManager.cs"))
            if not candidates:
                raise SystemExit("MultiplayerManager.cs not found in decompilation output")
            manager_path = candidates[0]

        content = manager_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"VERSION\s*=\s*\"([^\"]+)\"", content)
        if not match:
            raise SystemExit("VERSION attribute not found in MultiplayerManager.cs")

        version = match.group(1)
        dest_dir = root / "decompiled" / version

        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(tmp_dir, dest_dir)

        return dest_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        args, parser = parse_args()
        root = Path(__file__).resolve().parent

        if args.install and not args.deploy:
            print("--install is ignored unless --deploy is also specified.")

        performed_action = False

        if args.get_dlls:
            decompiled_path = run_decompilation(root)
            print(f"Assembly decompiled to {decompiled_path}")
            performed_action = True

        if args.deploy:
            build_and_package(root, args.install)
            performed_action = True

        if not performed_action:
            parser.print_help()
            sys.exit(0)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
