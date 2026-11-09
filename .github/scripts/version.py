#!/usr/bin/env python3
"""Validate and bump only DPIUtil's coordinated source release metadata."""

import argparse
from pathlib import Path
import plistlib
import re


VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
PBX = Path("DPIUtil.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
LOCALIZED = Path("English.lproj/InfoPlist.strings")
MARKETING = re.compile(r"(\bMARKETING_VERSION\s*=\s*)([^;\n]+)(;)")
CURRENT = re.compile(r"(\bCURRENT_PROJECT_VERSION\s*=\s*)([^;\n]+)(;)")
SHORT = re.compile(r'(CFBundleShortVersionString\s*=\s*")([^"]+)(";)')
INFO = re.compile(r'(CFBundleGetInfoString\s*=\s*"DPIUtil version )([^,"]+)(,)')


def strict(value):
    if not isinstance(value, str) or not re.fullmatch(VERSION, value):
        raise ValueError(f"Invalid release version: {value!r}")
    return value


def read_version(root=Path(".")):
    project = (root / PBX).read_text()
    versions = set()
    for pattern in (MARKETING, CURRENT):
        values = pattern.findall(project)
        if len(values) != 6:
            raise ValueError("Expected release version in all six Xcode configurations")
        for _, value, _ in values:
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            versions.add(strict(value))
    if len(versions) != 1:
        raise ValueError("Xcode release version drift")
    version = versions.pop()
    with (root / PLIST).open("rb") as stream:
        data = plistlib.load(stream)
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if key == "CFBundleVersion" and key not in data:
            continue
        value = data.get(key)
        if value not in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}",
                         "$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
            if strict(value) != version:
                raise ValueError(f"Info.plist {key} release version drift")
    localized = (root / LOCALIZED).read_text()
    for pattern in (SHORT, INFO):
        matches = pattern.findall(localized)
        if len(matches) != 1 or strict(matches[0][1]) != version:
            raise ValueError("Localized release version missing, malformed or drifted")
    return version


def bump(mode, root=Path(".")):
    current = read_version(root)
    parts = list(map(int, current.split(".")))
    index = {"major": 0, "minor": 1, "patch": 2}[mode]
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    new = ".".join(map(str, parts))
    project = (root / PBX).read_text()
    for pattern in (MARKETING, CURRENT):
        project = pattern.sub(lambda m: m[1] + new + m[3], project)
    (root / PBX).write_text(project)
    # Preserve build-variable references and all unrelated plist fields/counters.
    with (root / PLIST).open("rb") as stream:
        data = plistlib.load(stream)
    text = (root / PLIST).read_text()
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if data.get(key) == current:
            text, count = re.subn(
                rf"(<key>{key}</key>\s*<string>)[^<]*(</string>)",
                lambda m: m[1] + new + m[2], text,
            )
            if count != 1:
                raise ValueError(f"Expected one plist {key}")
    (root / PLIST).write_text(text)
    localized = (root / LOCALIZED).read_text()
    for pattern in (SHORT, INFO):
        localized = pattern.sub(lambda m: m[1] + new + m[3], localized)
    (root / LOCALIZED).write_text(localized)
    if read_version(root) != new:
        raise ValueError("Post-bump validation failed")
    return new


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bump", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    print(bump(args.bump) if args.bump else read_version())
