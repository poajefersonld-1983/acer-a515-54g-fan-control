#!/bin/bash
set -euo pipefail
if [[ ${EUID} == 0 ]]; then
  echo 'Execute como usuário normal; sudo será solicitado para o serviço.' >&2; exit 1
fi
sudo systemctl disable --now acer-fan-control.service
sudo rm -f /etc/systemd/system/acer-fan-control.service
sudo rm -f /usr/local/lib/acer-fan-control/{pmc3.py,backend.py,daemon.py}
sudo systemctl daemon-reload
rm -f "$HOME/.local/bin/acer-fan-control" "$HOME/.local/share/applications/acer-fan-control.desktop"   "$HOME/.local/share/icons/hicolor/scalable/apps/acer-fan-control.svg"
rm -f "$(xdg-user-dir DESKTOP)/Acer Fan Control.desktop"
for name in panel.py backend.py daemon.py pmc3.py setup-service.py icon.svg; do
  rm -f "$HOME/.local/share/acer-fan-control/$name"
done
printf 'Removido. O perfil em /var/lib/acer-fan-control foi preservado.\n'
