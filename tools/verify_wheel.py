"""Install and smoke-test the built wheel in an isolated environment."""

import argparse
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path


def run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path, help="Wheel file or directory containing one wheel")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if wheel.is_dir():
        metadata = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
        version = metadata["project"]["version"]
        wheels = sorted(wheel.glob(f"dagwright-{version}-*.whl"))
        if len(wheels) != 1:
            parser.error(f"expected exactly one DAGwright wheel in {wheel}, found {len(wheels)}")
        wheel = wheels[0]
    root = Path(__file__).parents[1]
    with tempfile.TemporaryDirectory(prefix="dagwright-wheel-") as directory:
        environment = Path(directory) / "venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        dagwright = environment / ("Scripts/dagwright.exe" if os.name == "nt" else "bin/dagwright")
        run("uv", "venv", str(environment), "--python", "3.12")
        run("uv", "pip", "install", "--python", str(python), str(wheel))
        run(str(dagwright), "version")
        run(str(dagwright), "doctor")
        run(str(dagwright), "ui", "--help")
        contract = root / "examples/customer-analytics/dataproduct.yaml"
        suite = root / "examples/customer-analytics/verification.yaml"
        overlay = root / "examples/customer-analytics/development.overlay.yaml"
        output = Path(directory) / "compiled"
        run(str(dagwright), "validate", str(contract))
        run(str(dagwright), "compile", str(contract), "--target", "spark", "-o", str(output))
        run(
            str(dagwright),
            "compile",
            str(contract),
            "--overlay",
            str(overlay),
            "--target",
            "spark",
            "-o",
            str(Path(directory) / "overlaid"),
        )
        code = """
from pathlib import Path
from dagwright.resources import schema_path
from dagwright.verification import parse_verification_suite_file
from dagwright.viewer import build_viewer_snapshot
from importlib.resources import files
assert schema_path('dataproduct-v1alpha1.json').is_file()
assert schema_path('dataproduct-overlay-v1alpha1.json').is_file()
assert schema_path('verification-suite-v1alpha1.json').is_file()
assert parse_verification_suite_file(Path(__import__('sys').argv[1])).kind == 'VerificationSuite'
assert files('dagwright').joinpath('viewer/index.html').is_file()
assert files('dagwright').joinpath('viewer/app.js').is_file()
assert files('dagwright').joinpath('viewer/style.css').is_file()
assert len(build_viewer_snapshot(Path(__import__('sys').argv[2])).payload) > 1000
"""
        run(str(python), "-c", code, str(suite), str(contract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
