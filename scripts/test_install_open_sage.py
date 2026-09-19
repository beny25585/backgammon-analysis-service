import tempfile
import unittest
from pathlib import Path

from install_open_sage import needs_compatible_build, patch_compatible_source


class CompatibleBuildTests(unittest.TestCase):
    def test_ivy_bridge_and_unknown_linux_use_fallback(self):
        for flags in ("flags : sse sse2 avx", "", "flags : avx2"):
            self.assertTrue(needs_compatible_build("Linux", "x86_64", flags))

    def test_all_processors_must_support_both_features(self):
        self.assertFalse(needs_compatible_build("Linux", "x86_64", "flags : avx2 fma"))
        self.assertTrue(needs_compatible_build("Linux", "x86_64",
            "flags : avx2 fma\nflags : avx"))
        self.assertFalse(needs_compatible_build("Linux", "aarch64", ""))

    def test_patch_changes_flags_and_disables_unconditional_avx2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cpp/src").mkdir(parents=True)
            cmake = root / "cpp/CMakeLists_cpu.txt"
            cpp = root / "cpp/src/neural_net.cpp"
            cmake.write_text("set(BGBOT_OPT_FLAGS -O3 -mavx2 -mfma)")
            cpp.write_text("  #define BGBOT_USE_AVX2 1\n")
            patch_compatible_source(root)
            self.assertIn("-march=x86-64 -mtune=generic", cmake.read_text())
            self.assertIn("#undef BGBOT_USE_AVX2", cpp.read_text())

    def test_upstream_drift_fails_before_any_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cpp/src").mkdir(parents=True)
            cmake = root / "cpp/CMakeLists_cpu.txt"
            cmake.write_text("-mavx2 -mfma")
            (root / "cpp/src/neural_net.cpp").write_text("unexpected upstream")
            with self.assertRaises(RuntimeError):
                patch_compatible_source(root)
            self.assertEqual(cmake.read_text(), "-mavx2 -mfma")
