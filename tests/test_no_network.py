"""Guard that enforces stdlib-only + no network code anywhere in src/moatleak, and no dynamic imports.

Static ast.Import/ImportFrom checks catch `import socket` and `from urllib import ...`.
Dynamic imports via __import__(), exec(), eval(), or importlib.import_module() bypass
the static guard. This test walks the AST of every .py file under src/moatleak and
flags Call nodes whose func is:
  - Name: __import__, exec, eval, or import_module (bare Name from `from importlib import import_module`)
  - Attribute: importlib.import_module

Note: importlib.resources is whitelisted (stdlib, no network risk).

The release offline run (`unshare -rn`) is the complementary runtime check.
"""
import ast, pathlib

CORE = pathlib.Path(__file__).parent.parent / "src" / "moatleak"
BANNED = {"socket", "urllib", "http", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib"}

def _imports(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module.split(".")[0]

def test_core_has_no_network_imports():
    offenders = []
    for py in CORE.rglob("*.py"):
        bad = BANNED & set(_imports(py))
        if bad:
            offenders.append(f"{py.relative_to(CORE)}: {sorted(bad)}")
    assert not offenders, "network imports in core:\n" + "\n".join(offenders)

def test_no_connectors_package():
    assert not (CORE / "connectors").exists()

def test_core_has_no_dynamic_imports():
    """Flag dynamic imports like __import__(), exec(), eval(), importlib.import_module()."""
    offenders = []
    for py in CORE.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Check for __import__(), exec(), eval()
                if isinstance(func, ast.Name) and func.id in {"__import__", "exec", "eval"}:
                    offenders.append(f"{py.relative_to(CORE)}: {func.id}() call")
                # Check for bare Name import_module (from importlib import import_module; import_module(...))
                elif isinstance(func, ast.Name) and func.id == "import_module":
                    offenders.append(f"{py.relative_to(CORE)}: import_module() call (bare Name)")
                # Check for importlib.import_module() (Attribute form)
                elif isinstance(func, ast.Attribute) and func.attr == "import_module":
                    if isinstance(func.value, ast.Name) and func.value.id == "importlib":
                        offenders.append(f"{py.relative_to(CORE)}: importlib.import_module() call")
    assert not offenders, "dynamic imports in core:\n" + "\n".join(offenders)
