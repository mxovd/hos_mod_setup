#!/usr/bin/env python3
"""Setup a Hex of Steel mod project from the template directory."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from string import Template
from types import ModuleType


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


def _load_env_file(env_path: Path) -> None:
	if not env_path.exists():
		return

	for raw_line in env_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#"):
			continue
		if "=" not in line:
			continue

		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip()

		if not key:
			continue

		if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
			value = value[1:-1]

		os.environ.setdefault(key, value)


def _load_template_utils(template_utils_path: Path) -> ModuleType:
	if not template_utils_path.exists():
		raise SystemExit(f"Template utility script not found at {template_utils_path}")

	spec = importlib.util.spec_from_file_location(
		"hos_mod_utils_template", template_utils_path
	)
	if spec is None or spec.loader is None:
		raise SystemExit("Failed to load hos_mod_utils.py for path detection")

	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _validate_required_paths(utils_module: ModuleType, env_path: Path) -> None:
	install_path = utils_module.determine_mod_install_path()
	managed_path = utils_module.determine_game_managed_dir()

	missing: list[tuple[str, str, Path]] = []
	if not install_path.exists() or not install_path.is_dir():
		missing.append(("Hex of Steel MODS directory", "HOS_MODS_PATH", install_path))
	if not managed_path.exists() or not managed_path.is_dir():
		missing.append(("Hex of Steel Managed directory", "HOS_MANAGED_DIR", managed_path))

	if not missing:
		return

	message_lines = [
		"Unable to locate required Hex of Steel directories before scaffolding.",
	]
	for description, env_var, path in missing:
		message_lines.append(
			f" - {description} was not found (looked at {path}) — set {env_var} in {env_path} or export it."
		)
	message_lines.append("Update the environment variables, then rerun mod_folder_setup.py.")

	raise SystemExit("\n".join(message_lines))

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


def _copy_default_dotenv(destination: Path, env_path: Path) -> None:
	if not env_path.exists():
		return

	dest_env = destination / ".env"
	if dest_env.exists():
		return

	shutil.copy2(env_path, dest_env)


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
	root_dir = Path(__file__).resolve().parent
	env_path = root_dir / ".env"
	_load_env_file(env_path)

	template_dir = root_dir / "template"
	if not template_dir.exists():
		raise SystemExit(f"Template directory not found at {template_dir}")
	if not template_dir.is_dir():
		raise SystemExit(f"Template path {template_dir} is not a directory")

	template_utils = _load_template_utils(template_dir / "hos_mod_utils.py")
	_validate_required_paths(template_utils, env_path)

	destination = args.destination.resolve()
	_ensure_destination(destination, force=args.force)

	values = _build_values(args)
	_copy_template(template_dir, destination, values)
	_copy_default_dotenv(destination, env_path)
	(destination / "assets").mkdir(parents=True, exist_ok=True)
	_run_initial_decomp(destination)

	print(f"Created mod setup in {destination}")
	print("Applied substitutions:")
	for key in sorted(values):
		print(f"  {key} = {values[key]}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

