import ast

DEFAULT_BLOCKLIST = frozenset({
    "os", "subprocess", "socket", "sys", "shutil", "ctypes",
})

# Builtins that are dangerous as calls
DEFAULT_BLOCKED_BUILTINS = frozenset({"eval", "exec"})

# Attribute name that performs a dynamic import when called on the importlib
# module (importlib.import_module(...)).
_IMPORT_MODULE_ATTR = "import_module"


class ForbiddenImportError(Exception):
    pass


class ImportFilter:
    def __init__(self, blocklist=None, blocked_builtins=None):
        self.blocklist = frozenset(blocklist) if blocklist is not None else DEFAULT_BLOCKLIST
        self.blocked_builtins = (
            frozenset(blocked_builtins) if blocked_builtins is not None else DEFAULT_BLOCKED_BUILTINS
        )

    def check(self, code: str) -> None:
        """Raise ForbiddenImportError if code contains forbidden imports or builtin calls.

        Raises SyntaxError (not ForbiddenImportError) when the code cannot be parsed,
        so callers can distinguish a policy violation from an LLM output failure.

        Static analysis only catches import targets passed as string literals — this
        is a best-effort advisory layer, not the security boundary. The container's
        network isolation and read-only workspace mount (see PodmanRunner) are what
        actually contain untrusted code; this filter narrows the blast radius before
        code even reaches the sandbox.
        """
        tree = ast.parse(code)  # propagates SyntaxError directly
        importlib_aliases, import_module_aliases = self._collect_dynamic_import_aliases(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in self.blocklist:
                        raise ForbiddenImportError(f"Forbidden import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in self.blocklist:
                        raise ForbiddenImportError(f"Forbidden import: from {node.module}")

            elif isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name in self.blocked_builtins:
                    raise ForbiddenImportError(f"Forbidden builtin call: {name}()")

                self._check_dynamic_import_call(node, importlib_aliases, import_module_aliases)

    def _collect_dynamic_import_aliases(self, tree: ast.AST) -> tuple[set[str], set[str]]:
        """Track names bound to the importlib module or to importlib.import_module
        directly, including `as` aliases, so renamed imports are still caught
        (e.g. `import importlib as il; il.import_module(...)`,
        `from importlib import import_module as loader; loader(...)`).
        "importlib" is included unconditionally so a bare `importlib.import_module(...)`
        is still caught even without a preceding `import importlib` in the same snippet.
        """
        importlib_aliases = {"importlib"}
        import_module_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "importlib":
                        importlib_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "importlib":
                    for alias in node.names:
                        if alias.name == _IMPORT_MODULE_ATTR:
                            import_module_aliases.add(alias.asname or alias.name)
        return importlib_aliases, import_module_aliases

    def _check_dynamic_import_call(
        self, node: ast.Call, importlib_aliases: set[str], import_module_aliases: set[str]
    ) -> None:
        func = node.func
        is_dunder_import = isinstance(func, ast.Name) and func.id == "__import__"
        is_import_module_attr = (
            isinstance(func, ast.Attribute)
            and func.attr == _IMPORT_MODULE_ATTR
            and isinstance(func.value, ast.Name)
            and func.value.id in importlib_aliases
        )
        is_import_module_name = isinstance(func, ast.Name) and func.id in import_module_aliases

        if not (is_dunder_import or is_import_module_attr or is_import_module_name):
            return
        if not node.args:
            return

        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            root = first_arg.value.split(".")[0]
            if root in self.blocklist:
                raise ForbiddenImportError(f"Forbidden dynamic import: {first_arg.value}")
