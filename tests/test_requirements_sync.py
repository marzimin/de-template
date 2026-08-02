"""Guard against pyproject.toml and requirements-airflow.txt drifting apart.

Local development installs from pyproject.toml with uv; Airflow tasks run
against whatever pip put in the image from requirements-airflow.txt. When the
two disagree, code that works on a laptop fails in a task log with a
ModuleNotFoundError, often long after the change that caused it.

Converting that comment into a test makes the drift fail the build instead.
"""

import re
import tomllib

# Packages allowed to appear in only one of the two files, with the reason.
AIRFLOW_ONLY = {
    # Provider package; pulled in by apache-airflow locally.
    "apache-airflow-providers-standard",
}
PYPROJECT_ONLY = {
    # The base image pins Airflow itself; reinstalling would fight that pin.
    "apache-airflow",
}

REQUIREMENT_PATTERN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(.*)$")


def _parse_requirements(text: str) -> dict[str, str]:
    """Map package name (normalised) to its version specifier."""
    parsed = {}
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        match = REQUIREMENT_PATTERN.match(line)
        assert match, f"Could not parse requirement line: {line!r}"
        name, specifier = match.groups()
        parsed[name.lower().replace("_", "-")] = specifier.strip()
    return parsed


def _pyproject_dependencies(project_root) -> dict[str, str]:
    manifest = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    return _parse_requirements("\n".join(manifest["project"]["dependencies"]))


def _airflow_requirements(project_root) -> dict[str, str]:
    return _parse_requirements(
        (project_root / "requirements-airflow.txt").read_text(encoding="utf-8")
    )


def test_every_runtime_dependency_is_installed_in_the_airflow_image(project_root):
    missing = (
        set(_pyproject_dependencies(project_root))
        - set(_airflow_requirements(project_root))
        - PYPROJECT_ONLY
    )

    assert not missing, (
        f"{sorted(missing)} are in pyproject.toml but not requirements-airflow.txt. "
        "Airflow tasks importing them will fail with ModuleNotFoundError. Add them "
        "there, or to PYPROJECT_ONLY if they genuinely should not be in the image."
    )


def test_the_airflow_image_installs_nothing_the_project_does_not_declare(project_root):
    extra = (
        set(_airflow_requirements(project_root))
        - set(_pyproject_dependencies(project_root))
        - AIRFLOW_ONLY
    )

    assert not extra, (
        f"{sorted(extra)} are in requirements-airflow.txt but not pyproject.toml. "
        "Local development will not have them, so code using them passes in a task "
        "and fails on a laptop. Add them to pyproject.toml, or to AIRFLOW_ONLY."
    )


def test_shared_dependencies_pin_the_same_versions(project_root):
    pyproject = _pyproject_dependencies(project_root)
    airflow = _airflow_requirements(project_root)

    mismatched = {
        name: (pyproject[name], airflow[name])
        for name in set(pyproject) & set(airflow)
        if pyproject[name] != airflow[name]
    }

    assert not mismatched, (
        "Version specifiers differ between pyproject.toml and "
        f"requirements-airflow.txt: {mismatched}"
    )
