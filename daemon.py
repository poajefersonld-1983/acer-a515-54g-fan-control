#!/usr/bin/env python3
"""Root service: saved fan profile survives GUI disconnection and restart."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fan_backend", HERE / "backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
STATE = Path("/var/lib/acer-fan-control/profile.json")
SOCKET = "/run/acer-fan-control/control.sock"


def read_profile(path=STATE):
    try:
        data = json.loads(path.read_text())
        action, pwm = backend.decode_command(json.dumps({"action": data["mode"], "pwm": data.get("pwm")}))
        if action not in ("auto", "manual", "max"):
            raise ValueError("Perfil inválido")
        return action, (255 if action == "max" else pwm)
    except FileNotFoundError:
        return "auto", None


def save_profile(mode, pwm, path=STATE):
    backend.decode_command(json.dumps({"action": mode, "pwm": pwm}))
    if mode not in ("auto", "manual", "max"):
        raise ValueError("Perfil inválido")
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump({"mode": mode, "pwm": pwm}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def serve(pmc, uid):
    pmc.validate_pwm_limit()
    original = pmc.pwm()
    if not 1 <= original <= 255:
        raise RuntimeError("PWM inicial inesperado")
    saved_mode, saved_pwm = read_profile()
    mode, target = saved_mode, saved_pwm
    selector = selectors.DefaultSelector()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    Path(SOCKET).unlink(missing_ok=True)
    server.bind(SOCKET)
    os.chown(SOCKET, uid, -1)
    os.chmod(SOCKET, 0o600)
    server.listen(4)
    server.setblocking(False)
    selector.register(server, selectors.EVENT_READ)
    clients = {}
    stopped = False
    changed = False
    previous = original
    next_sample = 0
    temperature = None
    sample = None

    def stop(*_):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)

    def restore():
        nonlocal changed
        if changed:
            pmc.set_pwm(previous)
            changed = False

    def detach(client):
        nonlocal mode, target, next_sample
        selector.unregister(client)
        client.close()
        clients.pop(client, None)
        if not clients:
            restore()
            mode, target = saved_mode, saved_pwm
            next_sample = 0

    def send(client, message):
        try:
            client.sendall((json.dumps(message, ensure_ascii=False) + "\n").encode())
        except (OSError, BlockingIOError):
            detach(client)

    def status_fields():
        return {"saved_mode": saved_mode, "saved_pwm": saved_pwm,
                "persistent": saved_mode != "auto"}

    try:
        while not stopped:
            for key, _ in selector.select(.15):
                client = key.fileobj
                if client is server:
                    client, _ = server.accept()
                    _, peer_uid, _ = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    if peer_uid not in (uid, 0):
                        client.close()
                        continue
                    client.setblocking(False)
                    clients[client] = {"pending": b"", "last": time.monotonic()}
                    selector.register(client, selectors.EVENT_READ)
                    send(client, {"event": "ready", "maximum_pwm": 255, **status_fields()})
                    next_sample = 0
                    continue
                try:
                    chunk = client.recv(4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    detach(client)
                    continue
                info = clients[client]
                info["pending"] += chunk
                if len(info["pending"]) > 8192:
                    detach(client)
                    continue
                while b"\n" in info["pending"] and client in clients:
                    line, info["pending"] = info["pending"].split(b"\n", 1)
                    try:
                        message = json.loads(line)
                        if isinstance(message, dict) and message.get("action") == "save":
                            save_profile(mode, target)
                            saved_mode, saved_pwm = mode, target
                            send(client, {"event": "saved", **status_fields()})
                        else:
                            action, pwm = backend.decode_command(line)
                            if action == "quit":
                                detach(client)
                                break
                            if action != "ping":
                                if action == "auto":
                                    restore()
                                    save_profile("auto", None)
                                    saved_mode, saved_pwm = "auto", None
                                    mode, target = "auto", None
                                else:
                                    if not changed:
                                        previous = pmc.pwm()
                                    mode, target = action, (255 if action == "max" else pwm)
                                next_sample = 0
                        info["last"] = time.monotonic()
                    except (ValueError, KeyError, UnicodeError) as error:
                        send(client, {"event": "error", "message": str(error)})
            for client, info in list(clients.items()):
                if time.monotonic() - info["last"] > 15:
                    detach(client)
            if target is not None:
                changed = True
                pmc.set_pwm(255 if temperature is not None and temperature >= 85 else target)
            if time.monotonic() >= next_sample:
                values = pmc.read_ec_fixed()
                temperature = values[0x0558]
                sample = {"event": "sample", "mode": mode, "target": target,
                          "pwm": values[0x1808], "rpm": values[0x055c] * 256 + values[0x055d],
                          "cpu_c": temperature, "thermal_override": bool(target is not None and temperature >= 85),
                          **status_fields()}
                for client in list(clients):
                    send(client, sample)
                next_sample = time.monotonic() + 1
    finally:
        restore()
        for client in list(clients):
            client.close()
        selector.close()
        server.close()
        Path(SOCKET).unlink(missing_ok=True)


def main():
    uid = int(Path("/var/lib/acer-fan-control/uid").read_text())
    lock = os.open("/run/acer-a515-pmc3.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pmc = backend.pmc_module.PMC3()
        try:
            serve(pmc, uid)
        finally:
            pmc.close()
    finally:
        os.close(lock)


if __name__ == "__main__":
    main()
