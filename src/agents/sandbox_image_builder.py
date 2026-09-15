"""Build (and cache) a Podman image layering third-party packages on top of
the fixed harness base image, so module validation/assembly runs can import
what a module's generated code actually needs (#53) -- docker/harness/
Containerfile only ever installs pytest/bandit/pytest-timeout, and nothing
in the sandbox previously had a way to add to that.

`podman build` runs here, outside the `--network none` runtime sandbox
(src/agents/podman_runner.py) that untrusted generated code executes in --
the zero-trust guarantees for code *execution* are unchanged. Only this one
controlled `pip install` step, against a package list this module itself
validates, ever touches the network.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_BASE_IMAGE = "localhost/ace-harness:latest"
_DEPS_IMAGE_PREFIX = "localhost/ace-harness-deps"
_BUILD_TIMEOUT_SECONDS = 300

# PyPI distribution names: letters/digits plus . _ -, per PEP 503. Rejecting
# anything else keeps every package name safe to interpolate into a
# Containerfile RUN line (which a shell parses inside the build) even though
# these names may ultimately be sourced from LLM-generated (untrusted) code.
_VALID_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SandboxImageBuildError(Exception):
    """A package name failed validation, or `podman build` itself failed."""


def ensure_image_with_packages(
    packages: frozenset[str] | set[str],
    *,
    base_image: str = _DEFAULT_BASE_IMAGE,
) -> str:
    """Return the tag of a Podman image with `packages` pip-installed on top
    of `base_image`, building it once and reusing it thereafter.

    Returns `base_image` unchanged when `packages` is empty. Raises
    `SandboxImageBuildError` on an invalid package name or a failed build --
    callers should surface that as a validation failure, not let a generic
    exception propagate.
    """
    if not packages:
        return base_image

    names = sorted(set(packages))
    for name in names:
        if not _VALID_PACKAGE_NAME.match(name):
            raise SandboxImageBuildError(
                f"refusing to install {name!r}: not a valid PyPI package name"
            )

    digest = hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]
    tag = f"{_DEPS_IMAGE_PREFIX}:{digest}"

    exists = subprocess.run(
        ["podman", "image", "exists", tag], capture_output=True,
    )
    if exists.returncode == 0:
        return tag

    logger.info("building sandbox image %s with packages: %s", tag, ", ".join(names))
    containerfile = (
        f"FROM {base_image}\n"
        f"RUN pip install --no-cache-dir {' '.join(names)}\n"
    )
    with tempfile.TemporaryDirectory() as build_ctx:
        cf_path = Path(build_ctx) / "Containerfile"
        cf_path.write_text(containerfile)
        try:
            result = subprocess.run(
                ["podman", "build", "-t", tag, "-f", str(cf_path), build_ctx],
                capture_output=True, text=True, timeout=_BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxImageBuildError(
                f"building sandbox image with {names} timed out after "
                f"{_BUILD_TIMEOUT_SECONDS}s"
            ) from exc

    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-2000:]
        raise SandboxImageBuildError(
            f"podman build failed for packages {names}:\n{tail}"
        )
    return tag
