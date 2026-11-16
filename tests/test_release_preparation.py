"""Release configuration/updater checks: no build, archive, network or user state."""
import ast
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

import update_checker as finder
from edmc_plugin.EDHF_Community_Navigator import update_checker as edmc

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.5"
BETA_VERSION = "1.0.5-beta.1"


class UpdaterReleaseTests(unittest.TestCase):
    def check(self, module, current, latest, **extra):
        payload = dict(tag_name="v" + latest, name="Fixture release",
                       html_url="https://example.invalid/release", prerelease=False, draft=False,
                       assets=[dict(name=f"Hotspots-Finder-EDMC-Plugin-v{latest}.zip")])
        payload.update(extra)
        with patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result = module.check_for_update(current)
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.args[0].full_url.endswith("/releases/latest"))
        return result

    def test_numeric_and_beta_order_is_identical_in_both_clients(self):
        versions = ["1.0.4", BETA_VERSION, "1.0.5-beta.2", "1.0.5-beta.10", "1.0.5", "1.0.6", "1.0.10"]
        for module in (finder, edmc):
            parsed = [module._version_tuple(v) for v in versions]
            self.assertEqual(parsed, sorted(parsed))
            self.assertEqual(module._version_tuple("v" + BETA_VERSION), parsed[1])
        self.assertEqual([finder._version_tuple(v) for v in versions], [edmc._version_tuple(v) for v in versions])

    def test_beta_does_not_downgrade_to_current_stable(self):
        for module in (finder, edmc):
            result = self.check(module, BETA_VERSION, "1.0.4")
            self.assertTrue(result["ok"])
            self.assertFalse(result["update_available"])

    def test_same_base_stable_is_newer_than_beta(self):
        for module in (finder, edmc):
            result = self.check(module, "v" + BETA_VERSION, "1.0.5")
            self.assertTrue(result["ok"])
            self.assertTrue(result["update_available"])

    def test_stable_clients_keep_normal_update_behavior(self):
        for module in (finder, edmc):
            for current, latest, expected in [("1.0.4", "1.0.5", True), ("1.0.5", "1.0.5", False), ("1.0.5", "1.0.10", True)]:
                result = self.check(module, current, latest)
                self.assertTrue(result["ok"])
                self.assertEqual(result["update_available"], expected)

    def test_beta_candidate_is_never_offered_even_with_incorrect_release_flags(self):
        for module in (finder, edmc):
            for extra in ({}, {"prerelease": True}, {"assets": [dict(name="Hotspots-Finder-EDMC-Plugin-v1.0.5.zip")]}):
                result = self.check(module, "1.0.4", BETA_VERSION, **extra)
                self.assertFalse(result["update_available"])

    def test_draft_or_prerelease_stable_tag_is_not_offered(self):
        for module in (finder, edmc):
            for flags in ({"draft": True}, {"prerelease": True}):
                self.assertFalse(self.check(module, VERSION, "1.0.5", **flags)["update_available"])

    def test_invalid_current_versions_and_network_failure_are_quiet(self):
        for module in (finder, edmc):
            for value in (None, "", "1.0.5-beta.0", "1.0.5-beta.x", "1.0.5-rc.1", "garbage"):
                self.assertIsNone(module._version_tuple(value))
                self.assertFalse(self.check(module, value, "1.0.5")["update_available"])
            with patch.object(module.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
                result = module.check_for_update(VERSION)
                self.assertFalse(result["ok"])
                self.assertFalse(result["update_available"])

    def test_plugin_still_reads_its_version_from_stable_asset(self):
        result = self.check(edmc, BETA_VERSION, "1.0.6", assets=[dict(name="Hotspots-Finder-EDMC-Plugin-v1.0.5.zip")])
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "1.0.5")


class PackagingSourceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "release_manifest.json").read_text(encoding="utf-8"))
        self.plugin = ROOT / "edmc_plugin/EDHF_Community_Navigator"

    def test_exact_source_inventory_and_compile_without_emitting_files(self):
        self.assertEqual(self.manifest["version"], VERSION)
        self.assertEqual(len(self.manifest["finder_sources"]), 24)
        self.assertEqual(len(self.manifest["plugin_sources"]), 20)
        self.assertEqual(set(self.manifest["finder_sources"]), {p.name for p in ROOT.glob("*.py")})
        self.assertEqual(set(self.manifest["plugin_sources"]), {p.name for p in self.plugin.glob("*.py")})
        for base, field in ((ROOT, "finder_sources"), (self.plugin, "plugin_sources")):
            self.assertEqual(len(self.manifest[field]), len(set(self.manifest[field])))
            for name in self.manifest[field]:
                self.assertEqual(Path(name).name, name)
                compile((base / name).read_text(encoding="utf-8-sig"), str(base / name), "exec")
        self.assertTrue(set(self.manifest["finder_shared_sources"]) <= set(self.manifest["plugin_sources"]))

    def test_version_constants_and_windows_stable_metadata(self):
        for p, variable, expected in [(ROOT / "hotspots_finder_gui_v8_final.py", "PUBLIC_APP_VERSION", "v" + VERSION),
                                      (self.plugin / "load.py", "VERSION", VERSION)]:
            tree = ast.parse(p.read_text(encoding="utf-8"))
            value = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets))
            self.assertEqual(value, expected)
        def keyword_record(**kwargs): return kwargs
        scope = dict(VSVersionInfo=keyword_record, FixedFileInfo=keyword_record,
                     StringFileInfo=lambda x: x, StringTable=lambda *args: args,
                     StringStruct=lambda *args: args, VarFileInfo=lambda x: x, VarStruct=lambda *args: args)
        info = eval(compile((ROOT / "version_info_v8.txt").read_text(), "metadata", "eval"), scope)
        self.assertEqual(info["ffi"]["filevers"], (1, 0, 5, 0))
        self.assertEqual(info["ffi"]["prodvers"], (1, 0, 5, 0))
        self.assertEqual(info["ffi"]["flags"] & 2, 0)
        strings = dict(info["kids"][0][0][1])
        self.assertEqual(strings["FileVersion"], VERSION)
        self.assertEqual(strings["ProductVersion"], VERSION)

    def test_pyinstaller_configuration_with_stubbed_build_functions(self):
        captured = {}
        def analysis(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])
        scope = dict(SPECPATH=str(ROOT), Analysis=analysis, PYZ=lambda *args: None, EXE=lambda *args, **kwargs: None)
        exec(compile((ROOT / "HotspotsFinder-v8.spec").read_text(), "spec", "exec"), scope)
        self.assertEqual(set(captured["datas"]), {(p, ".") for p in self.manifest["resources"]})
        self.assertIn("finder_distance", captured["hiddenimports"])
        for name in self.manifest["finder_shared_sources"]:
            self.assertIn("edmc_plugin.EDHF_Community_Navigator." + Path(name).stem, captured["hiddenimports"])
        for resource in self.manifest["resources"]:
            self.assertTrue((ROOT / resource).is_file())

    def test_sources_and_resources_are_not_gitignored(self):
        paths = self.manifest["finder_sources"] + ["edmc_plugin/EDHF_Community_Navigator/" + n for n in self.manifest["plugin_sources"]]
        paths += self.manifest["resources"] + ["release_manifest.json", "HotspotsFinder-v8.spec", "version_info_v8.txt"]
        result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=ROOT,
                                input="\n".join(paths) + "\n", text=True, capture_output=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_packaging_is_stable_only_and_plugin_uses_allowlist(self):
        bat = (ROOT / "build_windows_v8.bat").read_text()
        ps = (ROOT / "build_companion_release.ps1").read_text()
        self.assertIn('set "VERSION=v' + VERSION + '"', bat)
        self.assertIn("build-v" + VERSION, bat)
        self.assertIn("dist-v" + VERSION, bat)
        self.assertNotIn("v1.0.4", bat + ps)
        self.assertNotIn('Copy-Item (Join-Path $PluginSource "*")', ps)
        self.assertIn('$Manifest.plugin_sources', ps)
        self.assertIn('"EDHF_Community_Navigator"', ps)
        self.assertIn('"release\\v$Version"', ps)
        self.assertIn('"' + VERSION + '"', ps)
        self.assertNotIn(BETA_VERSION, bat + ps)

    def test_operational_guides_identify_the_stable_release(self):
        for name in ("README.md", "RELEASE_NOTES.md", "docs/COMMUNITY_DEPOSITS.md",
                     "docs/EDMC_COMPANION.md", "docs/RHINOSPOTTER.md", "edmc_plugin/EDHF_Community_Navigator/README.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(VERSION, text)
            self.assertNotIn(BETA_VERSION, text)


    def test_community_user_agents_identify_stable_version(self):
        for name in ("community_deposits.py", "rhinospotter_sync.py",
                     "edmc_plugin/EDHF_Community_Navigator/community_api.py"):
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
            user_agent = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                              and any(isinstance(t, ast.Name) and t.id == "USER_AGENT" for t in n.targets))
            self.assertTrue(user_agent.endswith("/" + VERSION), user_agent)

    def test_build_checksums_and_isolated_intermediates(self):
        bat = (ROOT / "build_windows_v8.bat").read_text()
        ps = (ROOT / "build_companion_release.ps1").read_text()
        for script in (bat, ps):
            self.assertIn("SHA256.txt", script)
            self.assertIn("[Security.Cryptography.SHA256]::Create()", script)
            self.assertIn("ComputeHash", script)
            self.assertIn("SHA256", script)
        for name in ("build-v" + VERSION + "/", "dist-v" + VERSION + "/"):
            self.assertIn(name, (ROOT / ".gitignore").read_text().splitlines())

    def test_production_canaries_are_documented_as_residual(self):
        notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        operations = (ROOT / "docs/PUBLISH_v1.0.5.md").read_text(encoding="utf-8")
        self.assertIn("NOT TESTED in production", operations)
        self.assertIn("Read-only", operations)
        self.assertIn("same-UUID retry", operations)
        self.assertIn("# v1.0.4", notes)
