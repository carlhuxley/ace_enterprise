Feature: Persistent Codebase DAG Manifest

  # ---------------------------------------------------------------------------
  # IMPLEMENTATION CONTRACT — read before writing any test or code
  # ---------------------------------------------------------------------------
  # Module file:  persistent_dag.py
  # Imports:      ONLY `json` and `pathlib` from the standard library.
  #               Do NOT import os, sys, subprocess, shutil, socket or ctypes —
  #               they are blocked by the sandbox and abort the run. Use
  #               pathlib.Path for every filesystem operation
  #               (Path.mkdir(parents=True, exist_ok=True), Path.write_text,
  #               Path.read_text, Path.exists).
  #
  # Public API (all at module level, all importable by name):
  #
  #   MANIFEST_RELPATH = ".ace/dag_manifest.json"
  #
  #   class CircularDependencyError(Exception): ...
  #
  #   def register_module(workspace: Path, name: str, *,
  #                       provides: list[str] | None = None,
  #                       depends_on: list[str] | None = None) -> None
  #       Add or replace a module in the manifest at
  #       workspace / MANIFEST_RELPATH, creating the file and the ".ace"
  #       directory on first call. `provides` / `depends_on` default to [].
  #       Registering the same name again overwrites that module's entry only.
  #       If the write would introduce a dependency cycle among the modules,
  #       raise CircularDependencyError and leave the file on disk byte-for-byte
  #       unchanged (validate fully before writing anything).
  #
  #   def load_manifest(workspace: Path) -> dict
  #       Return the parsed manifest. Shape:
  #         {"modules": {
  #             "<name>": {"provides": ["..."], "depends_on": ["..."]},
  #             ...
  #         }}
  #       Return {"modules": {}} if the file does not exist.
  #
  #   def build_order(workspace: Path) -> list[str]
  #       Topological order of all registered modules: every module appears
  #       after all of its depends_on entries. Break ties by sorting names
  #       lexically so the result is deterministic.
  #
  #   def blast_radius(workspace: Path, name: str) -> set[str]
  #       `name` plus every module that transitively depends on it (all
  #       downstream dependents). Always includes `name` itself.
  #
  # Tests: use pytest's `tmp_path` fixture as the workspace. Import exactly
  #        what you use, e.g.
  #          import json
  #          from pathlib import Path
  #          from persistent_dag import (
  #              register_module, load_manifest, build_order, blast_radius,
  #              CircularDependencyError, MANIFEST_RELPATH,
  #          )
  # ---------------------------------------------------------------------------

  Scenario: Initialize and write a clean manifest to disk
    Given an empty workspace directory
    When register_module is called with name "user_service", provides ["authenticate", "create_user"] and depends_on ["db_pool"]
    Then the file at workspace / ".ace/dag_manifest.json" exists
    And json.loads of that file has "user_service" as a key under "modules"
    And modules["user_service"]["depends_on"] equals ["db_pool"]
    And modules["user_service"]["provides"] equals ["authenticate", "create_user"]

  Scenario: Register a second independent module without disturbing the first
    Given an empty workspace directory
    And register_module was called with name "db_pool", provides ["get_connection"] and depends_on []
    When register_module is called with name "cache", provides ["get", "set"] and depends_on []
    Then load_manifest(workspace)["modules"] has exactly the keys {"db_pool", "cache"}
    And modules["db_pool"]["provides"] still equals ["get_connection"]

  Scenario: Reject a direct circular dependency atomically
    Given an empty workspace directory
    And register_module was called with name "auth_core" and depends_on ["token_store"]
    And register_module was called with name "token_store" and depends_on []
    And the manifest bytes on disk are captured
    When register_module is called with name "token_store" and depends_on ["auth_core"]
    Then a CircularDependencyError is raised
    And the manifest bytes on disk are unchanged from what was captured
    And modules["token_store"]["depends_on"] equals []

  Scenario: Reject an indirect (multi-hop) circular dependency
    Given an empty workspace directory
    And register_module was called for "a" with depends_on ["b"]
    And register_module was called for "b" with depends_on ["c"]
    And register_module was called for "c" with depends_on []
    When register_module is called with name "c" and depends_on ["a"]
    Then a CircularDependencyError is raised

  Scenario: Resolve a multi-level topological build order
    Given an empty workspace directory
    And register_module was called for "db" with depends_on []
    And register_module was called for "models" with depends_on ["db"]
    And register_module was called for "services" with depends_on ["models"]
    And register_module was called for "api_gateway" with depends_on ["services"]
    When build_order(workspace) is computed
    Then it equals exactly:
      | db          |
      | models      |
      | services    |
      | api_gateway |

  Scenario: Break topological ties lexically for determinism
    Given an empty workspace directory
    And register_module was called for "base" with depends_on []
    And register_module was called for "zeta" with depends_on ["base"]
    And register_module was called for "alpha" with depends_on ["base"]
    When build_order(workspace) is computed
    Then it equals exactly ["base", "alpha", "zeta"]

  Scenario: Extract the downstream blast radius for an updated module
    Given an empty workspace directory
    And register_module was called for "utils" with depends_on []
    And register_module was called for "core" with depends_on ["utils"]
    And register_module was called for "web" with depends_on ["core"]
    And register_module was called for "analytics" with depends_on ["utils"]
    When blast_radius(workspace, "core") is calculated
    Then it equals the set {"core", "web"}
    And it does not contain "analytics"

  Scenario: Blast radius of a leaf module is just itself
    Given an empty workspace directory
    And register_module was called for "utils" with depends_on []
    And register_module was called for "web" with depends_on ["utils"]
    When blast_radius(workspace, "web") is calculated
    Then it equals the set {"web"}
