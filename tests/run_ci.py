#!/usr/bin/env python3
"""Run selected emulator suites, preserving logs and exact build hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "storage64": ["ci_storage.py"],
    "storage128": ["ci_storage.py", "--machine", "x128"],
    "fm": ["ci_fm.py"],
    "vdc": ["ci_vdc.py"],
    "copy": ["ci_copy.py"],
    "edit": ["ci_edit.py"],
    "calc": ["ci_calc.py"],
    "native": ["ci_native.py"],
}


def build_hashes():
    files = sorted((ROOT / "target").glob("*.prg")) + [ROOT / "target/ultos.d64"]
    files += sorted((ROOT / "target/native").glob("*.prg"))
    files += sorted((ROOT / "target/native").glob("*.d64"))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suites", choices=list(SUITES), nargs="+")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="uos-regressions-"))
    report = {"build": build_hashes(), "suites": {}}
    print(f"Regression evidence: {work}", flush=True)
    for suite in args.suites:
        entry, *extra = SUITES[suite]
        print(f"Running {suite}", flush=True)
        with (work / f"{suite}.log").open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "tests" / entry), *extra],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end="", flush=True)
                code = process.wait()
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        report["suites"][suite] = {"exit_code": code}
        assert report["build"] == build_hashes(), "Build changed during regression"
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        if code:
            return code
    print(f"PASS: {len(args.suites)} suites; evidence at {work}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
