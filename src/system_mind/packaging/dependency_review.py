"""Automated dependency and supply-chain auditor enforcing strict pinning and zero ambient shell packages."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

BANNED_PYTHON_PACKAGES = {
    "sh",
    "plumbum",
    "pexpect",
    "ptyprocess",
    "fabric",
    "invoke",
}

BANNED_NODE_PACKAGES = {
    "child_process",
    "execa",
    "shelljs",
    "sudo-prompt",
    "node-pty",
    "open",
}

BANNED_RUST_CRATES = {
    "pyo3",
    "cpython",
    "inline-python",
}


@dataclass(frozen=True)
class DependencyReviewResult:
    """Audit result for monorepo dependency declarations."""

    valid: bool
    issues: tuple[str, ...]
    scanned_files: tuple[str, ...]
    python_packages_count: int
    rust_crates_count: int
    node_packages_count: int

    def to_dict(self) -> dict[str, object]:
        """Converts to dictionary for structured logging and CLI output."""
        return {
            "valid": self.valid,
            "issues": list(self.issues),
            "scanned_files": list(self.scanned_files),
            "python_packages_count": self.python_packages_count,
            "rust_crates_count": self.rust_crates_count,
            "node_packages_count": self.node_packages_count,
        }


class DependencyReviewer:
    """Audits monorepo dependency manifests across Python, Rust, and TypeScript tiers."""

    @classmethod
    def audit(cls, root_dir: Path | None = None) -> DependencyReviewResult:
        """Audits all package manifests in the monorepo."""
        base_dir = root_dir or ROOT_DIR
        issues: list[str] = []
        scanned_files: list[str] = []
        py_pkg_count = 0
        rust_crate_count = 0
        node_pkg_count = 0

        # 1. Audit Python requirements files
        py_req_files = [base_dir / "requirements.txt", base_dir / "requirements-dev.txt"]
        for req_file in py_req_files:
            if not req_file.exists():
                issues.append(f"Missing Python dependency manifest: {req_file.name}")
                continue

            scanned_files.append(str(req_file.relative_to(base_dir)))
            content = req_file.read_text(encoding="utf-8")
            for line_no, raw_line in enumerate(content.splitlines(), start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                py_pkg_count += 1
                pkg_match = re.match(r"^([a-zA-Z0-9_\-]+)(.*)$", line)
                if not pkg_match:
                    issues.append(f"{req_file.name}:{line_no}: Malformed requirement specifier: '{line}'")
                    continue

                pkg_name = pkg_match.group(1).lower()
                version_spec = pkg_match.group(2).strip()

                # Check banned packages
                if pkg_name in BANNED_PYTHON_PACKAGES:
                    issues.append(
                        f"{req_file.name}:{line_no}: Banned ambient execution package '{pkg_name}'. Violates SC-01."
                    )

                # Check exact pinning (==)
                if not version_spec.startswith("==") or "~=" in version_spec or ">=" in version_spec:
                    issues.append(
                        f"{req_file.name}:{line_no}: Unpinned dependency '{line}'. Exact pinning (==) is strictly required."
                    )

        # 2. Audit Rust Cargo manifests
        cargo_files = list(base_dir.glob("Cargo.toml")) + list(base_dir.glob("crates/*/Cargo.toml")) + list(base_dir.glob("apps/desktop/src-tauri/Cargo.toml"))
        for cargo_file in cargo_files:
            if not cargo_file.exists():
                continue
            scanned_files.append(str(cargo_file.relative_to(base_dir)))
            content = cargo_file.read_text(encoding="utf-8")

            # Check banned crates
            for banned in BANNED_RUST_CRATES:
                if re.search(rf'^\s*{banned}\s*=', content, re.MULTILINE):
                    issues.append(
                        f"{cargo_file.relative_to(base_dir)}: Forbidden native binding crate '{banned}' detected."
                    )

            # Count dependencies declared in [dependencies] or [dev-dependencies]
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and "dependencies" in stripped:
                    in_deps = True
                elif stripped.startswith("["):
                    in_deps = False
                elif in_deps and "=" in stripped and not stripped.startswith("#"):
                    rust_crate_count += 1

        # 3. Audit TypeScript / Node package.json
        pkg_json_file = base_dir / "apps" / "desktop" / "package.json"
        if pkg_json_file.exists():
            scanned_files.append(str(pkg_json_file.relative_to(base_dir)))
            try:
                pkg_data = json.loads(pkg_json_file.read_text(encoding="utf-8"))
                deps = pkg_data.get("dependencies", {})
                dev_deps = pkg_data.get("devDependencies", {})
                all_node_deps = {**deps, **dev_deps}
                node_pkg_count = len(all_node_deps)

                for dep_name in all_node_deps:
                    if dep_name in BANNED_NODE_PACKAGES:
                        issues.append(
                            f"apps/desktop/package.json: Banned ambient shell package '{dep_name}'. Violates SC-01."
                        )
            except Exception as e:
                issues.append(f"Failed to parse apps/desktop/package.json: {e}")
        else:
            issues.append("apps/desktop/package.json missing.")

        valid = len(issues) == 0
        return DependencyReviewResult(
            valid=valid,
            issues=tuple(issues),
            scanned_files=tuple(scanned_files),
            python_packages_count=py_pkg_count,
            rust_crates_count=rust_crate_count,
            node_packages_count=node_pkg_count,
        )
