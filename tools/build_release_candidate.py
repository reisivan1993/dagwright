"""Build and byte-verify a local DAGwright release candidate."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import uuid
import zipfile
from pathlib import Path
from tarfile import open as open_tar
from typing import Any

from packaging.markers import Marker

ROOT = Path(__file__).parents[1]
LOCK = ROOT / "uv.lock"


def run(*command: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def digest(path: Path, algorithm: str) -> str:
    checksum = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def dependency_names(package: dict[str, Any]) -> list[str]:
    return [
        dependency["name"]
        for dependency in package.get("dependencies", [])
        if "marker" not in dependency or Marker(dependency["marker"]).evaluate()
    ]


def locked_runtime_components() -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    lock = tomllib.loads(LOCK.read_text())
    packages: list[dict[str, Any]] = lock["package"]
    project = next(package for package in packages if package["name"] == "dagwright")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for package in packages:
        by_name.setdefault(package["name"], []).append(package)

    pending = [dependency["name"] for dependency in project.get("dependencies", [])]
    selected: set[tuple[str, str]] = set()
    while pending:
        name = pending.pop()
        for package in by_name.get(name, []):
            key = (name, package["version"])
            if key in selected:
                continue
            selected.add(key)
            pending.extend(dependency_names(package))

    components = [
        package for package in packages if (package["name"], package["version"]) in selected
    ]
    return project["version"], components, packages


def license_for(name: str) -> str:
    try:
        metadata = importlib.metadata.metadata(name)
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN"
    expression = metadata.get("License-Expression")
    if expression:
        return expression.strip()
    license_name = metadata.get("License", "").strip()
    if license_name and "\n" not in license_name and len(license_name) <= 120:
        return license_name
    classifiers = metadata.get_all("Classifier", [])
    licenses = [value.split(" :: ")[-1] for value in classifiers if value.startswith("License ::")]
    return ", ".join(licenses) or "UNKNOWN"


def write_supply_chain_files(output: Path, version: str, packages: list[dict[str, Any]]) -> None:
    refs = {
        package["name"]: f"pkg:pypi/{package['name']}@{package['version']}" for package in packages
    }
    project_ref = f"pkg:pypi/dagwright@{version}"
    components = []
    dependencies = [{"ref": project_ref, "dependsOn": sorted(refs.values())}]
    license_rows = []
    for package in sorted(packages, key=lambda item: (item["name"], item["version"])):
        name = package["name"]
        package_ref = f"pkg:pypi/{name}@{package['version']}"
        license_name = license_for(name)
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": package_ref,
            "name": name,
            "version": package["version"],
            "purl": package_ref,
        }
        if license_name != "UNKNOWN":
            component["licenses"] = [{"license": {"name": license_name}}]
        components.append(component)
        dependencies.append(
            {
                "ref": package_ref,
                "dependsOn": sorted(
                    refs[dependency]
                    for dependency in dependency_names(package)
                    if dependency in refs
                ),
            }
        )
        license_rows.append(f"| {name} | {package['version']} | {license_name} |")

    serial_seed = "\n".join([project_ref, *sorted(refs.values())])
    bom = {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": project_ref,
                "name": "dagwright",
                "version": version,
                "purl": project_ref,
                "licenses": [{"license": {"id": "Apache-2.0"}}],
            }
        },
        "components": components,
        "dependencies": dependencies,
    }
    (output / "dagwright.cdx.json").write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")
    report = [
        "# Runtime dependency license inventory",
        "",
        "Generated from `uv.lock` for the default DAGwright installation. Review UNKNOWN or",
        "non-SPDX values against upstream package metadata before release approval.",
        "",
        "| Package | Version | Declared license |",
        "| --- | --- | --- |",
        *license_rows,
        "",
    ]
    (output / "dependency-licenses.md").write_text("\n".join(report))


def verify_distribution_contents(output: Path) -> None:
    sdist = next(output.glob("dagwright-*.tar.gz"))
    wheel = next(output.glob("dagwright-*.whl"))
    required_fragments = {
        "LICENSE",
        "NOTICE",
        "schemas/dataproduct-v1alpha1.json",
        "schemas/dataproduct-overlay-v1alpha1.json",
        "schemas/verification-suite-v1alpha1.json",
    }
    with open_tar(sdist, "r:gz") as archive:
        sdist_names = {"/".join(name.split("/")[1:]) for name in archive.getnames()}
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    for fragment in required_fragments:
        if not any(name.endswith(fragment) for name in sdist_names):
            raise RuntimeError(f"source distribution is missing {fragment}")
        if not any(name.endswith(fragment) for name in wheel_names):
            raise RuntimeError(f"wheel is missing {fragment}")


def main() -> int:
    version, runtime_packages, _ = locked_runtime_components()
    output = ROOT / "build" / "release" / version
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    environment = os.environ.copy()
    commit_time = subprocess.check_output(
        ("git", "show", "-s", "--format=%ct", "HEAD"), cwd=ROOT, text=True
    ).strip()
    environment["SOURCE_DATE_EPOCH"] = commit_time

    with tempfile.TemporaryDirectory(prefix="dagwright-release-") as directory:
        first = Path(directory) / "first"
        second = Path(directory) / "second"
        run("uv", "build", "--out-dir", str(first), env=environment)
        run("uv", "build", "--out-dir", str(second), env=environment)
        first_files = sorted(path.name for path in first.iterdir())
        second_files = sorted(path.name for path in second.iterdir())
        if first_files != second_files:
            raise RuntimeError("repeated builds emitted different artifact names")
        for name in first_files:
            if digest(first / name, "sha256") != digest(second / name, "sha256"):
                raise RuntimeError(f"repeated builds differ: {name}")
            shutil.copy2(first / name, output / name)

    write_supply_chain_files(output, version, runtime_packages)
    verify_distribution_contents(output)
    (output / ".gitignore").unlink(missing_ok=True)
    artifacts = sorted(
        path
        for path in output.iterdir()
        if path.name != "SHA512SUMS" and not path.name.startswith(".")
    )
    checksums = "".join(f"{digest(path, 'sha512')}  {path.name}\n" for path in artifacts)
    (output / "SHA512SUMS").write_text(checksums)
    wheel = next(output.glob("dagwright-*.whl"))
    run("uv", "run", "python", "tools/verify_wheel.py", str(wheel))
    print(f"verified reproducible release candidate: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
