import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileDrift:
    file_path: Path
    added_lines: int
    removed_lines: int
    diff_snippet: str


@dataclass
class DriftReport:
    drifted_files: list[FileDrift] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.drifted_files

    def assert_clean(self) -> None:
        if not self.is_clean:
            raise InadvertentDriftError(self)


class InadvertentDriftError(Exception):
    def __init__(self, report: DriftReport) -> None:
        self.report = report
        paths = ", ".join(str(f.file_path) for f in report.drifted_files)
        super().__init__(f"Inadvertent changes detected in non-target files: {paths}")


class FileLockContext:
    def __init__(self, target_files: list[Path], project_root: Path) -> None:
        self._targets = {Path(f).resolve() for f in target_files}
        self._root = Path(project_root)
        self._saved: dict[Path, int] = {}

    def __enter__(self) -> "FileLockContext":
        for py_file in self._lockable_files():
            try:
                mode = py_file.stat().st_mode
                self._saved[py_file] = mode
                py_file.chmod(mode & ~0o222)
            except OSError:
                pass
        return self

    def __exit__(self, *_) -> None:
        for py_file, mode in self._saved.items():
            try:
                py_file.chmod(mode)
            except OSError:
                pass
        self._saved.clear()

    def _lockable_files(self) -> list[Path]:
        result = []
        for py_file in self._root.rglob("*.py"):
            if py_file.is_symlink():
                continue
            if "__pycache__" in py_file.parts:
                continue
            if py_file.resolve() not in self._targets:
                result.append(py_file)
        return result


class DriftDetector:
    def __init__(self, project_root: Path) -> None:
        self._root = Path(project_root)

    def check(self, target_files: list[Path]) -> DriftReport:
        targets = {Path(f).resolve() for f in target_files}

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=self._root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return DriftReport()

        drifted = []
        for rel in result.stdout.splitlines():
            rel = rel.strip()
            if not rel.endswith(".py"):
                continue
            abs_path = (self._root / rel).resolve()
            if abs_path in targets:
                continue
            drift = self._measure_drift(rel)
            if drift:
                drifted.append(drift)

        return DriftReport(drifted_files=drifted)

    def _measure_drift(self, rel_path: str) -> FileDrift | None:
        result = subprocess.run(
            ["git", "diff", rel_path],
            cwd=self._root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout:
            return None

        lines = result.stdout.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        snippet = "\n".join(lines[:10])

        return FileDrift(
            file_path=self._root / rel_path,
            added_lines=added,
            removed_lines=removed,
            diff_snippet=snippet,
        )
