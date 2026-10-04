#!/bin/bash
set -euo pipefail
app_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${EUID} == 0 ]]; then
  echo 'Execute como usuário normal, sem sudo.' >&2; exit 1
fi
/usr/bin/python3 "$app_dir/check-deps.py"
source_dir=$app_dir
app_dir="$HOME/.local/share/acer-fan-control"
mkdir -p "$app_dir"
for name in panel.py backend.py daemon.py pmc3.py setup-service.py icon.svg; do
  if [[ "$source_dir" != "$app_dir" ]]; then
    install -m 0644 "$source_dir/$name" "$app_dir/$name"
  fi
done
desktop_dir=$(xdg-user-dir DESKTOP)
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" \
  "$HOME/.local/share/icons/hicolor/scalable/apps" "$desktop_dir"
/usr/bin/python3 - "$app_dir" "$HOME/.local/bin/acer-fan-control" <<'PY'
import shlex,sys
from pathlib import Path
Path(sys.argv[2]).write_text('#!/bin/bash\nexec /usr/bin/python3 -I '
                           + shlex.quote(str(Path(sys.argv[1])/'panel.py')) + ' "$@"\n')
PY
chmod +x "$HOME/.local/bin/acer-fan-control"
cp "$app_dir/icon.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/acer-fan-control.svg"
cat > "$HOME/.local/share/applications/acer-fan-control.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Acer Fan Control
Comment=Controle de ventoinha, RPM e temperaturas do Aspire A515-54G
Exec="$HOME/.local/bin/acer-fan-control"
Icon=acer-fan-control
Terminal=false
Categories=System;Monitor;
Keywords=Acer;ventoinha;fan;MX250;temperatura;
StartupNotify=true
EOF
desktop-file-validate "$HOME/.local/share/applications/acer-fan-control.desktop"
cp "$HOME/.local/share/applications/acer-fan-control.desktop" "$desktop_dir/Acer Fan Control.desktop"
chmod +x "$desktop_dir/Acer Fan Control.desktop"
if command -v gio >/dev/null; then
  gio set "$desktop_dir/Acer Fan Control.desktop" metadata::trusted true 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$HOME/.local/share/applications"
fi
printf 'Instalado: %s/Acer Fan Control.desktop\n' "$desktop_dir"
