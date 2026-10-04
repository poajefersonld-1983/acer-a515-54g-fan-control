#!/usr/bin/env python3
"""Check runtime dependencies without opening hardware or installing anything."""
import importlib
from pathlib import Path
import shutil
import sys
errors = []
for command in ("pkexec", "systemctl", "xdg-user-dir", "desktop-file-validate"):
    if not shutil.which(command):
        errors.append("Comando ausente: " + command)
for module in ("gi", "cairo"):
    try:
        importlib.import_module(module)
    except ImportError:
        errors.append("Módulo ausente no Python do sistema: " + module)
try:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
except (ImportError, ValueError):
    errors.append("GTK 4 / introspecção indisponível")
if not Path("/run/systemd/system").is_dir():
    errors.append("Este instalador requer Linux inicializado com systemd")
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print("Dependências disponíveis. A compatibilidade de hardware é verificada ao conectar.")
