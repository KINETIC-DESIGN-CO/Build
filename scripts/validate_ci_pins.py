#!/usr/bin/env python3
"""Validate immutable third-party GitHub Actions and Supabase CLI pins."""

from __future__ import annotations

import re
import sys
from pathlib import Path

FULL_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
STABLE_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
USES_LINE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?uses:\s*(?P<value>.+?)\s*$")
WITH_LINE = re.compile(r"^(?P<indent>\s*)with:\s*(?:#.*)?$")
VERSION_LINE = re.compile(r"^(?P<indent>\s*)version:\s*(?P<value>[^#]+?)\s*(?:#.*)?$")
STEP_START = re.compile(r"^(?P<indent>\s*)-\s+(?:name|uses|run):")


def _strip_yaml_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith(("'", '"')):
        quote = value[0]
        end = value.find(quote, 1)
        if end == -1:
            return value
        return value[1:end]
    return value.split("#", 1)[0].strip()


def _action_id(reference: str) -> str:
    source = reference.rsplit("@", 1)[0]
    parts = source.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else source


def _step_indent(line: str, uses_indent: int) -> int:
    return uses_indent if line.lstrip().startswith("- uses:") else max(0, uses_indent - 2)


def _step_end(lines: list[str], uses_index: int, step_indent: int) -> int:
    for index in range(uses_index + 1, len(lines)):
        match = STEP_START.match(lines[index])
        if match and len(match.group("indent")) <= step_indent:
            return index
    return len(lines)


def _with_versions(lines: list[str], start: int, end: int) -> list[tuple[int, str]]:
    with_blocks: list[tuple[int, int]] = []
    for index in range(start, end):
        match = WITH_LINE.match(lines[index])
        if match:
            with_blocks.append((index, len(match.group("indent"))))

    versions: list[tuple[int, str]] = []
    for with_index, with_indent in with_blocks:
        for index in range(with_index + 1, end):
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= with_indent:
                break
            version_match = VERSION_LINE.match(line)
            if version_match and len(version_match.group("indent")) > with_indent:
                versions.append((index + 1, _strip_yaml_scalar(version_match.group("value"))))
    return versions


def validate_workflow_text(text: str, source: str = "<workflow>") -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()

    for index, line in enumerate(lines):
        match = USES_LINE.match(line)
        if not match:
            continue

        reference = _strip_yaml_scalar(match.group("value"))
        line_number = index + 1

        if reference.startswith("./") or reference.startswith("docker://"):
            continue

        if "@" not in reference:
            errors.append(f"{source}:{line_number}: external uses reference has no @ref: {reference}")
            continue

        _, ref = reference.rsplit("@", 1)
        if not FULL_COMMIT_SHA.fullmatch(ref):
            errors.append(
                f"{source}:{line_number}: external uses reference must be pinned to a full 40-hex commit SHA: {reference}"
            )

        if _action_id(reference) != "supabase/setup-cli":
            continue

        uses_indent = len(match.group("indent"))
        end = _step_end(lines, index, _step_indent(line, uses_indent))
        versions = _with_versions(lines, index + 1, end)

        if len(versions) != 1:
            errors.append(
                f"{source}:{line_number}: supabase/setup-cli step must declare exactly one with.version fixed CLI version"
            )
        else:
            version_line, version = versions[0]
            if not STABLE_SEMVER.fullmatch(version):
                errors.append(
                    f"{source}:{version_line}: Supabase CLI version must be an exact stable X.Y.Z version, not {version!r}"
                )

    return errors


def workflow_paths(root: Path) -> list[Path]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.exists():
        return []
    return sorted(
        [*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")],
        key=lambda path: path.as_posix(),
    )


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for path in workflow_paths(root):
        errors.extend(validate_workflow_text(path.read_text(encoding="utf-8"), path.as_posix()))
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_repository(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("CI_PINS_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
