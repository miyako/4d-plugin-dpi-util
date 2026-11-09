import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from xml.parsers.expat import ExpatError


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import publish
import version


FIXTURES = Path(__file__).parent / "fixtures"
SHA = "a" * 40
OTHER = "b" * 40
REPO = "example/dpi-util"
V = "7.8.9"
TAG = f"v{V}"


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)

    def change(self, path, old, new, count=-1):
        file = self.root / path
        file.write_text(file.read_text().replace(old, new, count))

    def test_explicit_fixture_bumps(self):
        for mode, expected in (("patch", "7.8.10"), ("minor", "7.9.0"), ("major", "8.0.0")):
            with self.subTest(mode=mode):
                shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)
                self.assertEqual(version.bump(mode, self.root), expected)
                self.assertEqual(version.read_version(self.root), expected)
                text = (self.root / version.PBX).read_text()
                self.assertEqual(text.count(f"MARKETING_VERSION = {expected};"), 6)
                self.assertEqual(text.count(f"CURRENT_PROJECT_VERSION = {expected};"), 6)
                self.assertIn("objectVersion = 46;", text)
                self.assertIn("<string>6.0</string>", (self.root / version.PLIST).read_text())

    def test_invalid_versions_and_drift_do_not_modify_files(self):
        mutations = [
            (version.PBX, "MARKETING_VERSION = 7.8.9", "MARKETING_VERSION = 07.8.9"),
            (version.PBX, "MARKETING_VERSION = 7.8.9", "MARKETING_VERSION = nope"),
            (version.PBX, "MARKETING_VERSION = 7.8.9", "MARKETING_VERSION = 7.8"),
            (version.PBX, "MARKETING_VERSION = 7.8.9", "MARKETING_VERSION = 7.8.10"),
            (version.PBX, "CURRENT_PROJECT_VERSION = 7.8.9", "CURRENT_PROJECT_VERSION = 7.8.8"),
            (version.PBX, "CURRENT_PROJECT_VERSION = 7.8.9;", ""),
            (version.PBX, "MARKETING_VERSION = 7.8.9;", ""),
            (version.PLIST, "<string>7.8.9</string>", "<string>7.8.10</string>"),
            (version.PLIST, "<string>7.8.9</string>", "<string>$(UNKNOWN)</string>"),
            (version.PLIST, "CFBundleShortVersionString", "MissingVersion"),
            (version.PLIST, "</plist>", ""),
            (version.LOCALIZED, "7.8.9", "7.8.8"),
            (version.LOCALIZED, "CFBundleShortVersionString", "MissingVersion"),
            (version.LOCALIZED, "DPIUtil version 7.8.9", "DPIUtil version 7.8"),
        ]
        for path, old, new in mutations:
            with self.subTest(path=path, new=new):
                shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)
                self.change(path, old, new, 1)
                before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
                with self.assertRaises((ValueError, plistlib.InvalidFileException, ExpatError)):
                    version.bump("patch", self.root)
                self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_supported_build_variables_and_optional_bundle_version(self):
        for variable in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}",
                         "$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
            with self.subTest(variable=variable):
                shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)
                self.change(version.PLIST, "<string>7.8.9</string>", f"<string>{variable}</string>")
                self.change(version.PLIST, "</dict>", f"<key>CFBundleVersion</key><string>{variable}</string></dict>")
                self.assertEqual(version.bump("patch", self.root), "7.8.10")
                self.assertEqual((self.root / version.PLIST).read_text().count(variable), 2)
        shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)
        self.change(version.PLIST, "</dict>", "<key>CFBundleVersion</key><string>7.8.9</string></dict>")
        version.bump("patch", self.root)
        with (self.root / version.PLIST).open("rb") as stream:
            self.assertEqual(plistlib.load(stream)["CFBundleVersion"], "7.8.10")
        self.change(version.PLIST, "<string>7.8.10</string>", "<string>7.8.11</string>", 1)
        with self.assertRaises(ValueError):
            version.read_version(self.root)

    def test_live_version_and_copy_bump(self):
        # Live expectations derive from the authority, never the fixture version.
        current = version.read_version(ROOT)
        project = (ROOT / version.PBX).read_text()
        self.assertIn(f"MARKETING_VERSION = {current};", project)
        for path in (version.PBX, version.PLIST, version.LOCALIZED):
            shutil.copyfile(ROOT / path, self.root / path)
        major, minor, patch_number = map(int, current.split("."))
        expected = f"{major}.{minor}.{patch_number + 1}"
        self.assertEqual(version.bump("patch", self.root), expected)
        self.assertEqual(version.read_version(self.root), expected)
        self.assertEqual(version.read_version(ROOT), current)


def entry(number, tag=None, draft=False):
    return {"id": number, "tag_name": tag or f"v0.0.{number}", "draft": draft}


class AvailabilityTests(unittest.TestCase):
    def test_empty_and_multiple_pages(self):
        pages = [[entry(i) for i in range(1, 101)], []]
        with patch.object(publish, "remote_tag", return_value=None), patch.object(publish, "api", side_effect=pages) as api:
            publish.available(REPO, TAG)
        self.assertEqual([c.args[1] for c in api.call_args_list],
                         ["releases?per_page=100&page=1", "releases?per_page=100&page=2"])

    def test_page_two_draft_and_published_collisions(self):
        for draft in (True, False):
            pages = [[entry(i) for i in range(1, 101)], [entry(101, TAG, draft)]]
            with patch.object(publish, "remote_tag", return_value=None), patch.object(publish, "api", side_effect=pages):
                with self.assertRaisesRegex(ValueError, "Release already exists"):
                    publish.available(REPO, TAG)

    def test_remote_tag_blocks_listing(self):
        with patch.object(publish, "remote_tag", return_value=OTHER), patch.object(publish, "api") as api:
            with self.assertRaisesRegex(ValueError, "Remote tag"):
                publish.available(REPO, TAG)
            api.assert_not_called()

    def test_listing_errors_and_malformed_pages_fail_closed(self):
        malformed = [None, {}, "Not Found", [None], [{}], [entry(True)],
                     [entry(1, draft="false")], [dict(entry(1), tag_name=3)],
                     [entry(1), entry(1)], [entry(i) for i in range(1, 102)]]
        errors = [subprocess.CalledProcessError(code, ["gh", "api"], stderr=reason)
                  for code, reason in ((1, "404"), (1, "401"), (1, "403"), (1, "network"))]
        errors += [json.JSONDecodeError("bad", "", 0)]
        for result in malformed + errors:
            with self.subTest(result=result), patch.object(publish, "remote_tag", return_value=None):
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with patch.object(publish, "api", **kwargs):
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        publish.available(REPO, TAG)
        for later_page in (errors[0], None, {}, [entry(1)]):
            with self.subTest(later_page=later_page), patch.object(publish, "remote_tag", return_value=None), patch.object(
                publish, "api", side_effect=[[entry(i) for i in range(1, 101)], later_page],
            ) as api:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    publish.available(REPO, TAG)
                self.assertEqual(api.call_count, 2)

    def test_authenticated_api_command_and_malformed_json(self):
        with patch.object(publish, "run", return_value="[]") as run:
            self.assertEqual(publish.api(REPO, "releases?per_page=100&page=1"), [])
            self.assertEqual(run.call_args.args,
                             ("gh", "api", f"repos/{REPO}/releases?per_page=100&page=1",
                              "--method", "GET", "--header", "Accept: application/vnd.github+json"))
        with patch.object(publish, "run", return_value="<html>error</html>"):
            with self.assertRaises(json.JSONDecodeError):
                publish.api(REPO, "releases?per_page=100&page=1")

    def test_remote_tag_response_validation(self):
        for output in ("broken\n", f"{SHA}\trefs/tags/wrong\n", f"{SHA}\trefs/tags/{TAG}\nextra\n"):
            with patch.object(publish, "run", return_value=output):
                with self.assertRaises(ValueError):
                    publish.remote_tag(TAG)
        with patch.object(publish, "run", side_effect=subprocess.CalledProcessError(1, ["git"])):
            with self.assertRaises(subprocess.CalledProcessError):
                publish.remote_tag(TAG)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.assets = [str(Path(self.temp.name) / f"DPIUtil-{V}.{ext}") for ext in ("zip", "dmg")]
        for asset in self.assets:
            Path(asset).write_bytes(b"fixture")
        self.calls = []
        self.state = {"tag": None, "release": False, "assets": []}
        self.fail = None

    def runner(self, *args, payload=None):
        self.calls.append((args, payload))
        if args[:2] == ("git", "rev-parse"):
            return SHA + "\n"
        if args[:2] == ("git", "ls-remote"):
            if self.state["tag"] is None:
                return ""
            return f'{self.state["tag"]}\trefs/tags/{TAG}\n'
        if args[:2] == ("git", "tag"):
            self.assertEqual(args, ("git", "tag", "--no-sign", TAG, SHA))
            return ""
        if args[:3] == ("git", "-c", "push.followTags=false"):
            self.assertEqual(args[3:], ("push", "--no-follow-tags", "--porcelain", "origin", f"refs/tags/{TAG}:refs/tags/{TAG}"))
            if self.fail == "tag-race":
                self.state["tag"] = OTHER
                raise subprocess.CalledProcessError(1, args)
            self.state["tag"] = OTHER if self.fail == "wrong-remote" else SHA
            if self.fail == "same-sha-race":
                return f"=\trefs/tags/{TAG}:refs/tags/{TAG}\t[up to date]\n"
            return f"*\trefs/tags/{TAG}:refs/tags/{TAG}\t[new tag]\n"
        if args[:2] == ("gh", "api"):
            method = args[args.index("--method") + 1]
            if method == "GET":
                if self.fail == "collision":
                    return json.dumps([entry(1, TAG, True)])
                return "[]"
            self.assertEqual(method, "POST")
            data = json.loads(payload)
            self.assertEqual(data, {"tag_name": TAG, "target_commitish": SHA, "name": TAG,
                                    "draft": False, "prerelease": False})
            if self.fail == "post":
                raise subprocess.CalledProcessError(1, args)
            self.state["release"] = True
            if self.fail == "post-response":
                return "{}"
            return json.dumps(dict(data, id=123))
        if args[:3] == ("gh", "release", "upload"):
            self.assertEqual(args, ("gh", "release", "upload", TAG, *self.assets, "--repo", REPO))
            self.state["assets"].append(self.assets[0])
            if self.fail == "upload":
                raise subprocess.CalledProcessError(1, args)
            self.state["assets"].append(self.assets[1])
            return ""
        self.failUnexpected(args)

    def failUnexpected(self, args):
        raise AssertionError(f"Unexpected command: {args}")

    def test_success_exact_sha_and_order(self):
        with patch.object(publish, "run", side_effect=self.runner):
            publish.publish(REPO, V, SHA, self.assets)
        self.assertEqual(self.state, {"tag": SHA, "release": True, "assets": self.assets})
        commands = [args for args, _ in self.calls]
        listing = next(i for i, args in enumerate(commands) if args[:2] == ("gh", "api"))
        tag = next(i for i, args in enumerate(commands) if args[:2] == ("git", "tag"))
        self.assertLess(listing, tag)
        self.assertEqual(commands[-2][0:2], ("gh", "api"))
        self.assertIn("--method", commands[-2])
        self.assertEqual(commands[-3][:2], ("git", "ls-remote"))

    def test_failures_preserve_partial_state_without_retries(self):
        expected = {
            "collision": (None, False, 0),
            "tag-race": (OTHER, False, 0),
            "same-sha-race": (SHA, False, 0),
            "wrong-remote": (OTHER, False, 0),
            "post": (SHA, False, 0),
            "post-response": (SHA, True, 0),
            "upload": (SHA, True, 1),
        }
        for failure, state in expected.items():
            with self.subTest(failure=failure):
                self.calls.clear()
                self.state = {"tag": None, "release": False, "assets": []}
                self.fail = failure
                with patch.object(publish, "run", side_effect=self.runner):
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        publish.publish(REPO, V, SHA, self.assets)
                self.assertEqual((self.state["tag"], self.state["release"], len(self.state["assets"])), state)
                commands = [args for args, _ in self.calls]
                self.assertLessEqual(sum(args[:3] == ("gh", "release", "upload") for args in commands), 1)
                self.assertLessEqual(sum("POST" in args for args in commands), 1)
                for args in commands:
                    self.assertFalse(set(args) & {"DELETE", "PATCH", "--clobber", "--force", "-f", "--delete"})
                    self.assertNotEqual(args[:3], ("gh", "release", "create"))

    def test_bad_sha_or_checkout_and_missing_assets_never_mutate(self):
        for sha in ("master", "a" * 7, OTHER):
            with patch.object(publish, "run", return_value=SHA + "\n") as run:
                with self.assertRaises(ValueError):
                    publish.publish(REPO, V, sha, self.assets)
                self.assertLessEqual(run.call_count, 1)
        Path(self.assets[1]).unlink()
        with patch.object(publish, "run", return_value=SHA + "\n") as run:
            with self.assertRaises(ValueError):
                publish.publish(REPO, V, SHA, self.assets)
            self.assertEqual(run.call_count, 1)

    def test_subprocess_failures_propagate(self):
        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["gh"])) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                publish.run("gh", "api", "example")
            self.assertTrue(run.call_args.kwargs["check"])


class WorkflowTests(unittest.TestCase):
    def test_manual_no_input_immutable_build_and_repository_lock(self):
        build = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("name: Build\n", build)
        trigger = build.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(trigger.strip(), "workflow_dispatch:")
        self.assertIn("group: release-publication\n", build)
        self.assertIn("cancel-in-progress: false", build)
        self.assertEqual(build.count("uses: actions/checkout@v4"), 3)
        self.assertEqual(build.count("ref: ${{ github.sha }}"), 3)
        self.assertNotIn("inputs.tag", build)
        self.assertNotIn("refs/heads/master", build)
        self.assertNotIn("softprops", build)
        self.assertNotIn("continue-on-error", build)
        self.assertIn("needs: [version, build-windows]", build)
        order = ["publish.py check", "msbuild ", "xcodebuild ", "lipo -info",
                 "codesign --verify", 'notarytool submit "$ZIP_PATH"',
                 'notarytool submit "$DMG_PATH"', '["Accepted", "Accepted"]',
                 'stapler staple "$DMG_PATH"', 'stapler validate "$DMG_PATH"',
                 "publish.py publish"]
        positions = [build.index(text) for text in order]
        self.assertEqual(positions, sorted(positions))
        secrets = set(re.findall(r"secrets\.([A-Z_]+)", build))
        self.assertEqual(secrets, {"APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
                                  "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID", "NOTARYTOOL_PASSWORD"})

    def test_bump_metadata_only_selected_branch_push(self):
        bump = (ROOT / ".github/workflows/bump-version.yml").read_text()
        self.assertEqual(re.findall(r"^\s+- (patch|minor|major)$", bump, re.M), ["patch", "minor", "major"])
        self.assertIn("ref: ${{ github.sha }}", bump)
        self.assertIn("group: bump-version-${{ github.ref }}", bump)
        self.assertIn('[[ "$SELECTED_REF" == refs/heads/* ]]', bump)
        self.assertIn('git -c push.followTags=false push --no-follow-tags origin "HEAD:${SELECTED_REF}"', bump)
        self.assertNotIn("git tag", bump)
        self.assertNotIn("workflow run", bump)
        self.assertNotIn("--force", bump)
        self.assertIn("English.lproj/InfoPlist.strings", bump)


class GitRaceTests(unittest.TestCase):
    def git(self, directory, *args, check=True):
        location = ["--git-dir", str(directory)] if directory.suffix == ".git" else ["-C", str(directory)]
        result = subprocess.run(
            ["git", *location, *args], check=check, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return result.stdout.strip() if check else result

    def commit(self, directory, name):
        (directory / "file").write_text(name)
        self.git(directory, "add", "file")
        self.git(directory, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-m", f"{name}\n\nCo-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>")
        return self.git(directory, "rev-parse", "HEAD")

    def test_actual_bump_script_only_pushes_selected_branch_and_rejects_races(self):
        workflow = (ROOT / ".github/workflows/bump-version.yml").read_text()
        script = textwrap.dedent(workflow.split("        run: |\n", 1)[1])
        for scenario in ("success", "branch-race", "tag-ref", "wrong-sha"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                remote, work, racer = [root / name for name in ("remote.git", "work", "racer")]
                self.git(root, "init", "--bare", str(remote))
                self.git(root, "clone", str(remote), str(work))
                self.git(work, "checkout", "-b", "selected")
                shutil.copytree(FIXTURES, work, dirs_exist_ok=True)
                shutil.copytree(ROOT / ".github/scripts", work / ".github/scripts")
                self.git(work, "add", ".")
                selected = self.commit(work, "initial")
                self.git(work, "push", "origin", "HEAD:refs/heads/selected")
                self.git(work, "checkout", "--detach", selected)
                self.git(work, "config", "push.followTags", "true")
                self.git(work, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                         "tag", "-a", "unrelated", "-m", "Unrelated annotated tag")
                remote_sha = selected
                if scenario == "branch-race":
                    self.git(root, "clone", "--branch", "selected", str(remote), str(racer))
                    remote_sha = self.commit(racer, "concurrent")
                    self.git(racer, "push", "origin", "HEAD:refs/heads/selected")
                result = subprocess.run(
                    ["bash", "-c", script], cwd=work, text=True,
                    env={**os.environ, "MODE": "patch", "SELECTED_SHA": OTHER if scenario == "wrong-sha" else selected,
                         "SELECTED_REF": "refs/tags/not-a-branch" if scenario == "tag-ref" else "refs/heads/selected",
                         "GITHUB_STEP_SUMMARY": str(root / "summary")},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.assertEqual(self.git(remote, "tag", "--list"), "")
                if scenario == "success":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    new_head = self.git(work, "rev-parse", "HEAD")
                    self.assertEqual(self.git(remote, "rev-parse", "refs/heads/selected"), new_head)
                    self.assertEqual(version.read_version(work), "7.8.10")
                    changed = set(self.git(work, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
                    self.assertEqual(changed, {str(version.PBX), str(version.PLIST), str(version.LOCALIZED)})
                    self.assertIn("Run Build manually", (root / "summary").read_text())
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.git(remote, "rev-parse", "refs/heads/selected"), remote_sha)
                    self.assertFalse((root / "summary").exists())

    def test_nonforced_branch_and_tag_races_and_followtags_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote, first, second = [root / name for name in ("remote.git", "first", "second")]
            self.git(root, "init", "--bare", str(remote))
            self.git(root, "clone", str(remote), str(first))
            self.git(first, "checkout", "-b", "selected")
            initial = self.commit(first, "initial")
            self.git(first, "push", "origin", "HEAD:refs/heads/selected")
            self.git(root, "clone", "--branch", "selected", str(remote), str(second))
            second_sha = self.commit(second, "other")
            self.git(second, "push", "origin", "HEAD:refs/heads/selected")
            self.commit(first, "bump")
            self.git(first, "config", "push.followTags", "true")
            self.git(first, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "tag", "-a", "unrelated", "-m", "Unrelated annotated tag")
            rejected = self.git(first, "-c", "push.followTags=false", "push", "--no-follow-tags",
                                "origin", "HEAD:refs/heads/selected", check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(self.git(remote, "rev-parse", "refs/heads/selected"), second_sha)
            self.assertEqual(self.git(remote, "tag", "--list"), "")
            self.git(first, "checkout", "-b", "fresh")
            self.git(first, "-c", "push.followTags=false", "push", "--no-follow-tags", "origin", "HEAD:refs/heads/fresh")
            self.assertEqual(self.git(remote, "tag", "--list"), "")
            self.git(second, "tag", "--no-sign", TAG, second_sha)
            self.git(second, "push", "origin", f"refs/tags/{TAG}:refs/tags/{TAG}")
            self.git(first, "tag", "--no-sign", TAG, initial)
            rejected = self.git(first, "-c", "push.followTags=false", "push", "--no-follow-tags",
                                "origin", f"refs/tags/{TAG}:refs/tags/{TAG}", check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(self.git(remote, "rev-parse", f"refs/tags/{TAG}"), second_sha)
            self.git(first, "tag", "--no-sign", "exact", initial)
            output = self.git(first, "-c", "push.followTags=false", "push", "--no-follow-tags",
                              "--porcelain", "origin", "refs/tags/exact:refs/tags/exact")
            self.assertIn("*\trefs/tags/exact:refs/tags/exact\t[new tag]", output)
            self.assertEqual(self.git(remote, "rev-parse", "refs/tags/exact"), initial)
            output = self.git(first, "-c", "push.followTags=false", "push", "--no-follow-tags",
                              "--porcelain", "origin", "refs/tags/exact:refs/tags/exact")
            self.assertIn("=\trefs/tags/exact:refs/tags/exact\t[up to date]", output)


if __name__ == "__main__":
    unittest.main()
