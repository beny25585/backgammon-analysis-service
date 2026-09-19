"""Install the pinned upstream engine, selecting a CPU-compatible Linux build.

Run with the service virtualenv's Python after installing requirements.txt
(or requirements-server.txt). The upstream models and engine version stay fixed.
"""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

REVISION = "d8325a491168062df1047ffd998f3a5dfb426a0c"
UPSTREAM = "https://github.com/markbgsage/bgsage.git"
ROOT = Path(__file__).resolve().parents[1]


def needs_compatible_build(system, machine, cpuinfo):
    if system != "Linux" or machine.lower() not in {"x86_64", "amd64"}:
        return False
    processors = [set(line.split(":", 1)[1].split())
                  for line in cpuinfo.splitlines()
                  if line.split(":", 1)[0].strip() == "flags" and ":" in line]
    # Unknown capabilities must not silently select the AVX2 build.
    return not processors or any(not {"avx2", "fma"} <= flags for flags in processors)


def patch_compatible_source(source):
    replacements = {
        "cpp/CMakeLists_cpu.txt": (
            "-mavx2 -mfma", "-march=x86-64 -mtune=generic"),
        "cpp/src/neural_net.cpp": (
            "#define BGBOT_USE_AVX2 1", "#undef BGBOT_USE_AVX2"),
    }
    # Validate all expected upstream content before changing either file.
    files = []
    for relative, (before, after) in replacements.items():
        path = source / relative
        content = path.read_text(encoding="utf-8")
        if content.count(before) != 1:
            raise RuntimeError(f"Unexpected upstream content: {relative}; refusing to patch")
        files.append((path, content.replace(before, after)))
    for path, content in files:
        path.write_text(content, encoding="utf-8")


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compatible", action="store_true",
                        help="Force the baseline x86-64 Linux build")
    args = parser.parse_args()
    if sys.prefix == sys.base_prefix:
        parser.error("Run this script with the service virtualenv's Python")
    system, machine = platform.system(), platform.machine()
    cpuinfo_path = Path("/proc/cpuinfo")
    cpuinfo = cpuinfo_path.read_text() if cpuinfo_path.exists() else ""
    compatible = args.compatible or needs_compatible_build(system, machine, cpuinfo)
    if compatible and (system != "Linux" or machine.lower() not in {"x86_64", "amd64"}):
        parser.error("The compatible build is supported on Linux x86-64")
    print(f"Open Sage {REVISION}: {'compatible scalar' if compatible else 'upstream'} build", flush=True)
    build_env = os.environ.copy()
    build_env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "2")
    # Build in an ignored directory and retain the resulting wheel for inspection.
    build_root = ROOT / ".engine-build"
    build_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-", dir=build_root) as temporary:
        source = Path(temporary)
        run("git", "init", "-q", str(source))
        run("git", "-C", str(source), "remote", "add", "origin", UPSTREAM)
        run("git", "-C", str(source), "fetch", "--depth=1", "--filter=blob:none", "origin", REVISION)
        run("git", "-C", str(source), "sparse-checkout", "set", "--no-cone",
            "/CMakeLists.txt", "/pyproject.toml", "/README.md", "/LICENSE",
            "/cpp/", "/python/", "/models/sl_s9_*.weights.best",
            "/models/sl_s11_*.weights.best", "/data/bearoff_1sided.db")
        run("git", "-C", str(source), "checkout", "--detach", REVISION)
        if compatible:
            patch_compatible_source(source)
        wheel_dir = build_root / ("compatible" if compatible else "upstream")
        wheel_dir.mkdir(exist_ok=True)
        run(sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-cache-dir",
            "--wheel-dir", str(wheel_dir), str(source), env=build_env)
        wheels = list(wheel_dir.glob("bgsage-2.0.20260907-*.whl"))
        wheels = [p for p in wheels if f"cp{sys.version_info.major}{sys.version_info.minor}-" in p.name]
        if len(wheels) != 1:
            raise RuntimeError("Expected one matching engine wheel")
        run(sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheels[0]))
    run(sys.executable, "-m", "pip", "check")
    run(sys.executable, "-u", "-c",
        'from bgsage import BgBotAnalyzer, STARTING_BOARD; '
        'a = BgBotAnalyzer(eval_level="1ply", cubeful=True); '
        'r = a.checker_play(STARTING_BOARD, 3, 1); '
        'assert r.moves; print("Open Sage OK; best equity:", r.moves[0].equity)')


if __name__ == "__main__":
    main()
