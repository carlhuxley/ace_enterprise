"""Stage 4 — Stamp Apache-2.0 SPDX headers onto synthesized files and write repo scaffold.

Applies to every .py and .ts file that doesn't already carry an SPDX identifier.
Python files get  # SPDX-...  headers; TypeScript files get  // SPDX-...  headers.
Also writes:
  - LICENSE       (copied verbatim from the repo root — single source of truth,
                    not a hand-duplicated string that could drift out of sync)
  - pyproject.toml  (Python target) OR package.json + tsconfig.json (TypeScript target)
  - .gitignore
"""
from datetime import datetime
from pathlib import Path

from bootstrap.audit_log import BootstrapAuditLog

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SPDX_ID = "Apache-2.0"

_SPDX_HEADER_TEMPLATE = """\
# SPDX-License-Identifier: Apache-2.0
# Copyright {year} {author}
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""

_SPDX_HEADER_TS_TEMPLATE = """\
// SPDX-License-Identifier: Apache-2.0
// Copyright {year} {author}
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"""

_PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
description = "{description}"
authors = [{{name = "{author}", email = "{email}"}}]
readme = "README.md"
requires-python = ">=3.10"
license = {{text = "Apache-2.0"}}

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

_TS_PACKAGE_JSON = """\
{{
  "name": "{name}",
  "version": "0.1.0",
  "type": "module",
  "description": "{description}",
  "license": "Apache-2.0",
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
    description: str = "ACE Enterprise — Apache-2.0 open-source release",
) -> int:
    """Stamp all source files and write repo scaffold. Returns count of stamped files."""
    _write_scaffold(out_dir, lang, project_name, author, email, description, log)

    stamped = 0
    year = datetime.now().year

    if lang == "typescript":
        header = _SPDX_HEADER_TS_TEMPLATE.format(year=year, author=author)
        glob = "*.ts"
    else:
        header = _SPDX_HEADER_TEMPLATE.format(year=year, author=author)
        glob = "*.py"

    for src_file in sorted(out_dir.rglob(glob)):
        original = src_file.read_text(encoding="utf-8")
        if "SPDX-License-Identifier" in original:
            continue
        src_file.write_text(header + original, encoding="utf-8")
        log.record(
            "STAMP_APPLY",
            file=str(src_file),
            spdx=_SPDX_ID,
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
    # Copied verbatim from the repo root rather than a hand-duplicated string —
    # one source of truth, no risk of the synthesized copy drifting out of
    # sync with the real license text.
    license_path.write_text(
        (_REPO_ROOT / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8"
    )
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
