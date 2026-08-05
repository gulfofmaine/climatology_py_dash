"""Record the VCR cassettes for the unit tests, one test per pytest process.

erddapy resolves its server list from raw.githubusercontent.com once per process
and caches it. A cassette recorded during a full run therefore misses that
request and fails when its test is later run on its own, so each test needs a
process of its own.

    pixi run unit-rerecord    # delete every cassette and record again
    pixi run unit-record-new  # record only the ones that are missing
"""

import argparse
import subprocess
import sys
from pathlib import Path

UNIT_TESTS = Path(__file__).parent / "unit"
CASSETTES = UNIT_TESTS / "cassettes"


def vcr_test_ids() -> list[str]:
    """Node ids of the unit tests marked with ``@pytest.mark.vcr``."""
    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(UNIT_TESTS),
            "-m",
            "vcr",
            "--collect-only",
            # Twice, to undo the --verbose in addopts: at net-negative
            # verbosity pytest lists one node id per line.
            "-q",
            "-q",
            "--no-header",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in collected.stdout.splitlines() if "::" in line]


def cassette_for(node_id: str) -> Path:
    """Where pytest-recording keeps the cassette for a test."""
    module, test = node_id.rsplit("::", 1)
    return CASSETTES / Path(module).stem / f"{test}.yaml"


def record(node_id: str) -> bool:
    """Record one test, returning whether it succeeded."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", node_id, "--record-mode=once", "-q"],
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="keep existing cassettes and only record tests that have none",
    )
    args = parser.parse_args()

    node_ids = vcr_test_ids()
    if not node_ids:
        print("No tests marked with @pytest.mark.vcr were collected.")
        return 1

    failed = []
    for node_id in node_ids:
        cassette = cassette_for(node_id)

        if args.new_only:
            if cassette.exists():
                print(f"have cassette, skipping  {node_id}")
                continue
        else:
            cassette.unlink(missing_ok=True)

        print(f"recording  {node_id}")
        if not record(node_id):
            failed.append(node_id)

    for node_id in failed:
        print(f"FAILED to record  {node_id}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
