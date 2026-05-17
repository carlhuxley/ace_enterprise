import ast

DEFAULT_BLOCKLIST = frozenset({
    "os", "subprocess", "socket", "sys", "shutil", "ctypes",
})

# Builtins that are dangerous as calls
DEFAULT_BLOCKED_BUILTINS = frozenset({"eval", "exec"})


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
        """
        tree = ast.parse(code)  # propagates SyntaxError directly

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
