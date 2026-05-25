"""Stage 4 — Stamp AGPLv3 SPDX headers onto synthesized files and write repo scaffold.

Applies to every .py and .ts file that doesn't already carry an SPDX identifier.
Python files get  # SPDX-...  headers; TypeScript files get  // SPDX-...  headers.
Also writes:
  - LICENSE  (short-form notice + pointer to full text)
  - pyproject.toml  (Python target) OR package.json + tsconfig.json (TypeScript target)
  - .gitignore
"""
from pathlib import Path

from bootstrap.audit_log import BootstrapAuditLog

_SPDX_HEADER = """\
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Carl Huxley <carlhuxley@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""

_LICENSE_NOTICE = """\
ACE Enterprise — Open Source Release
Copyright (C) 2026 Carl Huxley <carlhuxley@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

Full license text: https://www.gnu.org/licenses/agpl-3.0.txt
SPDX identifier:   AGPL-3.0-only

NOTE TO DISTRIBUTORS: Replace this file with the full AGPLv3 license text
obtained from https://www.gnu.org/licenses/agpl-3.0.txt before publishing.
"""

_PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
description = "{description}"
authors = [{{name = "{author}", email = "{email}"}}]
readme = "README.md"
requires-python = ">=3.10"
license = {{text = "AGPL-3.0-only"}}

dependencies = [
    "pydantic>=2.5.0",
    "httpx>=0.26.0",
    "python-dotenv>=1.0.0",
    "sqlalchemy>=2.0.0",
    "bandit>=1.9.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.12.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests", "src"]
python_files = "test_*.py"
"""

_SPDX_HEADER_TS = """\
// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Carl Huxley <carlhuxley@gmail.com>
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// by the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

"""

_TS_PACKAGE_JSON = """\
{{
  "name": "{name}",
  "version": "0.1.0",
  "type": "module",
  "description": "{description}",
  "license": "AGPL-3.0-only",
  "devDependencies": {{
    "typescript": "^5.4.0",
    "vitest": "^1.6.0"
  }},
  "scripts": {{
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  }}
}}
"""

_TS_TSCONFIG = """\
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true
  },
  "include": ["**/*.ts"]
}
"""

_GITIGNORE_PY = """\
__pycache__/
*.pyc
.venv/
.env
*.db
*.egg-info/
.pytest_cache/
htmlcov/
output/
"""

_GITIGNORE_TS = """\
node_modules/
dist/
.env
*.js.map
coverage/
"""


def stamp_directory(
    out_dir: Path,
    log: BootstrapAuditLog,
    *,
    lang: str = "python",
    project_name: str = "ace-enterprise-oss",
    author: str = "Carl Huxley",
    email: str = "carlhuxley@gmail.com",
    description: str = "ACE Enterprise — AGPLv3 open-source release",
) -> int:
    """Stamp all source files and write repo scaffold. Returns count of stamped files."""
    _write_scaffold(out_dir, lang, project_name, author, email, description, log)

    stamped = 0

    if lang == "typescript":
        patterns = [("*.ts", _SPDX_HEADER_TS, "//")]
    else:
        patterns = [("*.py", _SPDX_HEADER, "#")]

    for glob, header, _ in patterns:
        for src_file in sorted(out_dir.rglob(glob)):
            original = src_file.read_text(encoding="utf-8")
            if "SPDX-License-Identifier" in original:
                continue
            src_file.write_text(header + original, encoding="utf-8")
            log.record(
                "STAMP_APPLY",
                file=str(src_file),
                spdx="AGPL-3.0-only",
                sha256=BootstrapAuditLog.sha256(src_file),
            )
            stamped += 1

    return stamped


def _write_scaffold(
    out_dir: Path,
    lang: str,
    project_name: str,
    author: str,
    email: str,
    description: str,
    log: BootstrapAuditLog,
) -> None:
    license_path = out_dir / "LICENSE"
    license_path.write_text(_LICENSE_NOTICE, encoding="utf-8")
    log.record("LICENSE_WRITE", path=str(license_path), sha256=BootstrapAuditLog.sha256(license_path))

    if lang == "typescript":
        pkg_path = out_dir / "package.json"
        pkg_path.write_text(
            _TS_PACKAGE_JSON.format(name=project_name, description=description),
            encoding="utf-8",
        )
        log.record("PACKAGE_JSON_WRITE", path=str(pkg_path))
        tsconfig_path = out_dir / "tsconfig.json"
        tsconfig_path.write_text(_TS_TSCONFIG, encoding="utf-8")
        log.record("TSCONFIG_WRITE", path=str(tsconfig_path))
        (out_dir / ".gitignore").write_text(_GITIGNORE_TS, encoding="utf-8")
    else:
        pyproject_path = out_dir / "pyproject.toml"
        pyproject_path.write_text(
            _PYPROJECT.format(
                name=project_name, description=description, author=author, email=email,
            ),
            encoding="utf-8",
        )
        log.record("PYPROJECT_WRITE", path=str(pyproject_path))
        (out_dir / ".gitignore").write_text(_GITIGNORE_PY, encoding="utf-8")
