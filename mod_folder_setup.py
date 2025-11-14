#!/usr/bin/env python3
"""Setup a Hex of Steel mod project from the template directory."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from string import Template


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"destination",
		type=Path,
		help="Directory to create the new mod project inside.",
	)
	parser.add_argument("--mod-name", required=True, help="Display name of the mod.")
	parser.add_argument("--mod-author", required=True, help="Mod author name.")
	parser.add_argument(
		"--mod-description",
		default="",
		help="Description text to embed in the manifest.",
	)
	parser.add_argument(
		"--force",
		action="store_true",
		help="Allow scaffolding into a non-empty destination directory.",
	)
	return parser.parse_args()


def _slugify(value: str) -> str:
	import re

	tokens = re.findall(r"[A-Za-z0-9]+", value)
	slug = "-".join(token.lower() for token in tokens)
	return slug or "mod"


def _pascal_case(value: str) -> str:
	import re

	tokens = re.findall(r"[A-Za-z0-9]+", value)
	return "".join(token.capitalize() for token in tokens) or "ModProject"


def _ensure_destination(destination: Path, *, force: bool) -> None:
	if destination.exists():
		if not destination.is_dir():
			raise SystemExit(f"Destination {destination} exists and is not a directory")
		if not force:
			contents = list(destination.iterdir())
			if contents:
				raise SystemExit(
					f"Destination {destination} is not empty. Use --force to scaffold anyway."
				)
	else:
		destination.mkdir(parents=True)


def _is_binary_file(path: Path) -> bool:
	with path.open("rb") as handle:
		sample = handle.read(1024)
	return b"\0" in sample


PATH_PATTERNS = {
	"TemplateScript.cs": "${mod_class_name}.cs",
	"template_project.csproj": "${project_filename}",
	"template_project.sln": "${solution_filename}",
}

def _render_relative_path(relative: Path, values: dict[str, str]) -> Path:
	if relative == Path('.'):
		return Path('.')

	parts: list[str] = []
	for part in relative.parts:
		pattern = PATH_PATTERNS.get(part, part)
		rendered = Template(pattern).substitute(values)
		parts.append(rendered)
	return Path(*parts)


def _copy_template(template_dir: Path, destination: Path, values: dict[str, str]) -> None:
	for root, dirnames, filenames in os.walk(template_dir):
		root_path = Path(root)
		relative_root = root_path.relative_to(template_dir)
		rendered_root = _render_relative_path(relative_root, values)
		dest_root = destination / rendered_root
		dest_root.mkdir(parents=True, exist_ok=True)

		for dirname in dirnames:
			relative_dir = relative_root / dirname
			rendered_dir = _render_relative_path(relative_dir, values)
			(destination / rendered_dir).mkdir(parents=True, exist_ok=True)

		for filename in filenames:
			source_path = root_path / filename
			relative_path = relative_root / filename
			rendered_relative = _render_relative_path(relative_path, values)
			dest_path = destination / rendered_relative
			dest_path.parent.mkdir(parents=True, exist_ok=True)

			if _is_binary_file(source_path):
				shutil.copy2(source_path, dest_path)
				continue

			text = source_path.read_text(encoding="utf-8")
			template = Template(text)
			required_keys = {
				match.group("braced")
				for match in template.pattern.finditer(text)
				if match.group("braced")
			}
			missing = sorted(key for key in required_keys if key not in values)
			if missing:
				raise SystemExit(
					f"Missing placeholder(s) {', '.join(missing)} while processing {source_path}"
				)

			rendered_text = template.safe_substitute(values)
			dest_path.write_text(rendered_text, encoding="utf-8")


def _run_initial_decomp(destination: Path) -> None:
	deploy_script = destination / "hos_mod_utils.py"
	if not deploy_script.exists():
		raise SystemExit(f"Expected deploy script at {deploy_script}")

	command = [sys.executable, str(deploy_script), "--get-dlls"]
	subprocess.run(command, cwd=deploy_script.parent, check=True)


def _build_values(args: argparse.Namespace) -> dict[str, str]:
	mod_name = args.mod_name
	project_name = _pascal_case(mod_name)
	mod_class_name = f"{project_name}Mod"
	mod_folder_name = mod_name
	mod_slug = _slugify(mod_name)
	package_prefix = mod_slug
	mod_harmony_id = f"com.hexofsteel.{mod_slug}"
	project_guid = str(uuid.uuid4()).upper()
	solution_guid = str(uuid.uuid4()).upper()

	return {
		"mod_name": mod_name,
		"mod_version": "0.0.1",
		"mod_author": args.mod_author,
		"supported_game_version": "8.1.0+",
		"mod_description": args.mod_description,
		"project_name": project_name,
		"project_filename": f"{project_name}.csproj",
		"solution_filename": f"{project_name}.sln",
		"project_guid": project_guid,
		"solution_guid": solution_guid,
		"mod_class_name": mod_class_name,
		"mod_slug": mod_slug,
		"package_prefix": package_prefix,
		"mod_harmony_id": mod_harmony_id,
		"output_dll_name": f"{project_name}.dll",
		"mod_folder_name": mod_folder_name,
	}


def main() -> int:
	args = _parse_args()
	template_dir = Path(__file__).resolve().parent / "template"
	if not template_dir.exists():
		raise SystemExit(f"Template directory not found at {template_dir}")
	if not template_dir.is_dir():
		raise SystemExit(f"Template path {template_dir} is not a directory")

	destination = args.destination.resolve()
	_ensure_destination(destination, force=args.force)

	values = _build_values(args)
	_copy_template(template_dir, destination, values)
	(destination / "assets").mkdir(parents=True, exist_ok=True)
	_run_initial_decomp(destination)

	print(f"Created mod setup in {destination}")
	print("Applied substitutions:")
	for key in sorted(values):
		print(f"  {key} = {values[key]}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

