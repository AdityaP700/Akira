"""Safety test ensuring float is never used in money domain or services."""

import re
from pathlib import Path


def test_no_float_in_domain_or_services() -> None:
    project_root = Path(__file__).resolve().parent.parent.parent
    target_dirs = [project_root / "app" / "domain", project_root / "app" / "services"]

    pattern = re.compile(r"\bfloat\s*\(")

    violations: list[str] = []
    for directory in target_dirs:
        for py_file in directory.rglob("*.py"):
            lines = py_file.read_text(encoding="utf-8").splitlines()
            for line_no, line in enumerate(lines, 1):
                # Ignore comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if pattern.search(line):
                    violations.append(f"{py_file.relative_to(project_root)}:{line_no}: {line}")

    assert not violations, "Found forbidden float() conversions in domain/services:\n" + "\n".join(
        violations
    )
