"""Install and smoke-test the built wheel in an isolated environment."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    root = Path(__file__).parents[1]
    with tempfile.TemporaryDirectory(prefix="dagwright-wheel-") as directory:
        environment = Path(directory) / "venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        dagwright = environment / ("Scripts/dagwright.exe" if os.name == "nt" else "bin/dagwright")
        run("uv", "venv", str(environment), "--python", "3.12")
        run("uv", "pip", "install", "--python", str(python), str(wheel))
        run(str(dagwright), "version")
        run(str(dagwright), "doctor")
        contract = root / "examples/customer-analytics/dataproduct.yaml"
        suite = root / "examples/customer-analytics/verification.yaml"
        output = Path(directory) / "compiled"
        run(str(dagwright), "validate", str(contract))
        run(str(dagwright), "compile", str(contract), "--target", "spark", "-o", str(output))
        code = """
from pathlib import Path
from dagwright.resources import schema_path
from dagwright.verification import parse_verification_suite_file
assert schema_path('dataproduct-v1alpha1.json').is_file()
assert schema_path('verification-suite-v1alpha1.json').is_file()
assert parse_verification_suite_file(Path(__import__('sys').argv[1])).kind == 'VerificationSuite'
"""
        run(str(python), "-c", code, str(suite))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
