import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get("DPIUTIL_NATIVE_SOURCE_ROOT", ROOT)).resolve()


@unittest.skipUnless(sys.platform == "darwin", "requires macOS frameworks and clang")
class NativeOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="dpiutil-ownership-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / "ownership"
        api = SOURCE / "4D Plugin API"
        # Compile the complete, unchanged SDK, all actual wrappers and dispatcher.
        # No Xcode/MSBuild phases, signing, packaging or tracked binary writes.
        command = [
            "clang++", "-std=c++11", "-g", "-O1",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            "-Wno-deprecated-declarations", "-Wno-deprecated",
            "-x", "objective-c++", "-include", "Carbon/Carbon.h",
            "-include", "Cocoa/Cocoa.h", "-I", str(api),
            "-I", str(api / "Classes"), str(api / "4DPluginAPI.c"),
            *map(str, sorted((api / "Classes").glob("*.cpp"))),
            str(SOURCE / "4DPlugin.cpp"),
            str(ROOT / ".github/tests/native/ownership.cpp"),
            "-framework", "Cocoa", "-framework", "Carbon",
            "-o", str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def test_native_ownership(self):
        for scenario in ("file-path", "file-empty", "set-bytes", "copy-utf16", "copy-formats",
                         "picture-arguments", "arrays", "rejections", "scalar-content", "dispatcher",
                         "procedure-failure"):
            for empty in ("allocated-empty", "null-empty"):
                with self.subTest(scenario=scenario, empty=empty):
                    result = subprocess.run(
                        [str(self.binary), scenario, empty], capture_output=True,
                        text=True, env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                                        "UBSAN_OPTIONS": "halt_on_error=1"},
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
