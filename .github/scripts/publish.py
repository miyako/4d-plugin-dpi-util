#!/usr/bin/env python3
"""Create-only publication. Failures deliberately preserve remote partial state."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from version import strict


def run(*args, payload=None):
    return subprocess.run(
        args, input=payload, text=True, check=True, stdout=subprocess.PIPE,
    ).stdout


def api(repo, endpoint, payload=None):
    args = ["gh", "api", f"repos/{repo}/{endpoint}", "--method",
            "GET" if payload is None else "POST",
            "--header", "Accept: application/vnd.github+json"]
    if payload is not None:
        args += ["--input", "-"]
    return json.loads(run(*args, payload=None if payload is None else json.dumps(payload)))


def validate(repo, version, sha):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository")
    strict(version)
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected immutable full commit SHA")
    if run("git", "rev-parse", "HEAD").strip() != sha:
        raise ValueError("Checkout does not match selected SHA")


def remote_tag(tag):
    output = run("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}")
    if not output:
        return None
    lines = output.splitlines()
    if len(lines) != 1:
        raise ValueError("Malformed remote tag response")
    fields = lines[0].split()
    if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{40}", fields[0]) or fields[1] != f"refs/tags/{tag}":
        raise ValueError("Malformed remote tag response")
    return fields[0]


def available(repo, tag):
    # Authenticated listing includes drafts; a tag lookup alone does not.
    if remote_tag(tag) is not None:
        raise ValueError(f"Remote tag already exists: {tag}")
    page = 1
    seen = set()
    while True:
        entries = api(repo, f"releases?per_page=100&page={page}")
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError("Malformed releases page")
        for entry in entries:
            if (not isinstance(entry, dict)
                    or type(entry.get("id")) is not int or entry["id"] <= 0
                    or not isinstance(entry.get("tag_name"), str) or not entry["tag_name"]
                    or type(entry.get("draft")) is not bool
                    or entry["id"] in seen):
                raise ValueError("Malformed or repeated release entry")
            seen.add(entry["id"])
            if entry["tag_name"] == tag:
                raise ValueError(f"Release already exists (including drafts): {tag}")
        if len(entries) < 100:
            return
        page += 1


def publish(repo, version, sha, assets):
    validate(repo, version, sha)
    tag = f"v{version}"
    if len(assets) != 2 or any(not Path(asset).is_file() or Path(asset).stat().st_size == 0 for asset in assets):
        raise ValueError("Expected nonempty ZIP and DMG assets")
    # This recheck runs only after every build/signing/notarization gate.
    available(repo, tag)
    run("git", "tag", "--no-sign", tag, sha)
    refspec = f"refs/tags/{tag}:refs/tags/{tag}"
    pushed = run("git", "-c", "push.followTags=false", "push", "--no-follow-tags",
                 "--porcelain", "origin", refspec)
    statuses = [line.split("\t") for line in pushed.splitlines() if "\t" in line]
    if statuses != [["*", refspec, "[new tag]"]]:
        raise ValueError("Tag was not newly created; inspect remote state manually")
    if remote_tag(tag) != sha:
        raise ValueError("Remote tag does not point exactly at the selected SHA")
    release = api(repo, "releases", {
        "tag_name": tag, "target_commitish": sha, "name": tag,
        "draft": False, "prerelease": False,
    })
    if (not isinstance(release, dict) or type(release.get("id")) is not int
            or release["id"] <= 0 or release.get("tag_name") != tag
            or release.get("target_commitish") != sha
            or release.get("draft") is not False or release.get("prerelease") is not False):
        raise ValueError("Malformed create-release response; inspect remote state manually")
    # Never use `gh release create` with assets: its cleanup can delete a release.
    run("gh", "release", "upload", tag, *assets, "--repo", repo)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "publish"))
    parser.add_argument("version")
    parser.add_argument("sha")
    parser.add_argument("assets", nargs="*")
    args = parser.parse_args()
    repository = os.environ["GITHUB_REPOSITORY"]
    if args.command == "check":
        validate(repository, args.version, args.sha)
        available(repository, f"v{args.version}")
    else:
        publish(repository, args.version, args.sha, args.assets)
