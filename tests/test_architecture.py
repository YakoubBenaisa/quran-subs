"""The layering rule: logic packages never import Qt or the UI packages."""
import ast
import os

import pytest

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quran_companion")
QT_FREE = ["core", "data", "layout", "playback", "ipc", "sync"]
FORBIDDEN = ("PySide6", "quran_companion.overlay", "quran_companion.settings_ui")


def imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:   # resolve relative imports against the file's package
                parts = os.path.relpath(os.path.dirname(path), os.path.dirname(PKG)).split(os.sep)
                mod = ".".join(parts[: len(parts) - node.level + 1] + ([mod] if mod else []))
            yield mod


@pytest.mark.parametrize("layer", QT_FREE)
def test_logic_layers_do_not_import_ui(layer):
    for root, _, files in os.walk(os.path.join(PKG, layer)):
        for f in files:
            if f.endswith(".py"):
                bad = [m for m in imports(os.path.join(root, f)) if m.startswith(FORBIDDEN)]
                assert not bad, f"{layer}/{f} imports {bad}"
