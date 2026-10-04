#!/bin/bash
set -euo pipefail
. /etc/os-release
if [[ "$ID" != fedora ]]; then
  echo 'Este script é para Fedora. Consulte DEPENDENCIES.md.' >&2
  exit 1
fi
sudo dnf install python3 python3-gobject python3-cairo gtk4 polkit systemd xdg-user-dirs desktop-file-utils glib2 git
