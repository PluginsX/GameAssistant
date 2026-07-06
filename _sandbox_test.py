import os
import sys
import shutil
import subprocess

PROJECT = r"f:\Project\Python\GameAssistant"
VENV_PYTHON = os.path.join(PROJECT, "venv", "Scripts", "python.exe")
BUILD_DIR = os.path.join(PROJECT, "build")
TEST_DIST = os.path.join(PROJECT, "_test_dist")
TEST_WORK = os.path.join(PROJECT, "_test_work")

def clean():
    for d in [TEST_DIST, TEST_WORK]:
        if os.path.isdir(d):
            shutil.rmtree(d)
    # also clean existing build output
    for d in [os.path.join(BUILD_DIR, "GameAssistant"), os.path.join(BUILD_DIR, "GameAssistant_single"), os.path.join(BUILD_DIR, "_build")]:
        if os.path.isdir(d):
            shutil.rmtree(d)
    for f in [os.path.join(BUILD_DIR, "GameAssistant.exe"), os.path.join(BUILD_DIR, "GameAssistant_single.exe")]:
        if os.path.isfile(f):
            os.remove(f)

def run_spec(spec_name, mode_name):
    spec_path = os.path.join(PROJECT, spec_name)
    cmd = [
        VENV_PYTHON, "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--distpath", TEST_DIST,
        "--workpath", TEST_WORK,
        spec_path
    ]
    print(f"\n{'='*60}")
    print(f"Testing: {mode_name} ({spec_name})")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-2000:])
        return False

    # Check output
    print(f"\n--- Checking output in {TEST_DIST} ---")
    if os.path.isdir(TEST_DIST):
        for root, dirs, files in os.walk(TEST_DIST):
            for f in files:
                full = os.path.join(root, f)
                size = os.path.getsize(full)
                rel = os.path.relpath(full, TEST_DIST)
                print(f"  {rel} ({size} bytes)")
    else:
        print("  DIST DIR DOES NOT EXIST!")
        return False
    return True

if __name__ == "__main__":
    clean()
    os.makedirs(TEST_DIST, exist_ok=True)
    os.makedirs(TEST_WORK, exist_ok=True)

    print("=== SANDBOX PACK TEST ===")
    print(f"Python: {VENV_PYTHON}")
    print(f"Dist: {TEST_DIST}")
    print(f"Work: {TEST_WORK}")

    ok1 = run_spec("GameAssistant_onefile.spec", "ONEFILE")
    # clean work dir between runs
    if os.path.isdir(TEST_WORK):
        shutil.rmtree(TEST_WORK)
    os.makedirs(TEST_WORK, exist_ok=True)
    ok2 = run_spec("GameAssistant.spec", "DIR")

    print(f"\n=== RESULTS ===")
    print(f"Onefile: {'PASS' if ok1 else 'FAIL'}")
    print(f"Dir:     {'PASS' if ok2 else 'FAIL'}")

    # Cleanup
    clean()
