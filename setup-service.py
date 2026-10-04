#!/usr/bin/env python3
"""Install/update the fixed root fan service after explicit Polkit authorization."""
import importlib.util
import os
from pathlib import Path
import pwd
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
assert os.geteuid() == 0
assert not __import__("sys").argv[1:]
uid = int(os.environ["PKEXEC_UID"])
assert uid >= 1000 and pwd.getpwuid(uid).pw_uid == uid
spec = importlib.util.spec_from_file_location("pmc", HERE / "pmc3.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pmc = module.PMC3()
try:
    pmc.validate_pwm_limit()
finally:
    pmc.close()
destination = Path("/usr/local/lib/acer-fan-control")
destination.mkdir(mode=0o755, parents=True, exist_ok=True)
os.chown(destination, 0, 0)
os.chmod(destination, 0o755)
for name in ("pmc3.py", "backend.py", "daemon.py"):
    shutil.copyfile(HERE / name, destination / name)
    os.chown(destination / name, 0, 0)
    os.chmod(destination / name, 0o644)
state = Path("/var/lib/acer-fan-control")
state.mkdir(mode=0o700, exist_ok=True)
(state / "uid").write_text(str(uid) + "\n")
os.chmod(state / "uid", 0o600)
unit = Path("/etc/systemd/system/acer-fan-control.service")
unit.write_text('''[Unit]
Description=Acer A515-54G fan controller
After=systemd-udevd.service
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
ExecStart=/usr/bin/python3 -I /usr/local/lib/acer-fan-control/daemon.py
Restart=on-failure
RestartSec=3
TimeoutStopSec=3
RuntimeDirectory=acer-fan-control
RuntimeDirectoryMode=0755
StateDirectory=acer-fan-control
StateDirectoryMode=0700
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run
PrivateTmp=true
RestrictAddressFamilies=AF_UNIX

[Install]
WantedBy=multi-user.target
''')
os.chmod(unit, 0o644)
subprocess.run(["/usr/bin/systemctl", "daemon-reload"], check=True)
subprocess.run(["/usr/bin/systemctl", "enable", "acer-fan-control.service"], check=True)
subprocess.run(["/usr/bin/systemctl", "reset-failed", "acer-fan-control.service"], check=True)
subprocess.run(["/usr/bin/systemctl", "restart", "acer-fan-control.service"], check=True)
import time
for _ in range(30):
    if Path("/run/acer-fan-control/control.sock").exists():
        break
    time.sleep(.1)
else:
    raise RuntimeError("O serviço não disponibilizou a conexão; consulte o journal")
print("Serviço instalado. Só perfis salvos serão mantidos em segundo plano.")
