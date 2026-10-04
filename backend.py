#!/usr/bin/env python3
"""Bounded privileged controller, JSON stdin/stdout; hardware flags stay automatic."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import sys
import time

# -I intentionally excludes the script directory from Python's import path.
spec = importlib.util.spec_from_file_location("acer_pmc3", Path(__file__).with_name("pmc3.py"))
pmc_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pmc_module)


def emit(message):
    print(json.dumps(message, ensure_ascii=False), flush=True)


def decode_command(line):
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("Comando inválido")
    action = message.get("action")
    if action not in ("ping", "auto", "max", "manual", "quit"):
        raise ValueError("Ação inválida")
    if action == "manual":
        pwm = message.get("pwm")
        if type(pwm) is not int or not 183 <= pwm <= 255:
            raise ValueError("Ajuste manual permitido: PWM 183 a 255")
        return action, pwm
    return action, None


def serve(pmc):
    pmc.validate_pwm_limit()
    original = pmc.pwm()
    if not 1 <= original <= 255:
        raise RuntimeError("PWM inicial fora da faixa")
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin, selectors.EVENT_READ)
    os.set_blocking(sys.stdin.fileno(), False)
    mode, target, previous = "auto", None, None
    stopped = False
    changed = False
    pending = b""
    last_ping = time.monotonic()
    next_sample = 0
    temperature = None

    def stop(*_):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    try:
        emit({"event": "ready", "maximum_pwm": 255, "minimum_manual_pwm": 183})
        while not stopped:
            if time.monotonic() - last_ping > 15:
                emit({"event": "error", "message": "Conexão encerrada; retornando ao automático."})
                break
            for _, _ in selector.select(0.15):
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    stopped = True
                    break
                pending += chunk
                if len(pending) > 8192:
                    raise RuntimeError("Comando excede o limite")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    try:
                        action, pwm = decode_command(line)
                    except (ValueError, UnicodeError) as error:
                        emit({"event": "error", "message": str(error)})
                        continue
                    last_ping = time.monotonic()
                    if action == "quit":
                        stopped = True
                        break
                    if action == "ping":
                        continue
                    if action == "auto":
                        if changed:
                            pmc.set_pwm(previous)
                            changed = False
                        mode, target = "auto", None
                    else:
                        if not changed:
                            previous = pmc.pwm()
                        mode, target = action, (255 if action == "max" else pwm)
                    next_sample = 0
            if stopped:
                break
            protected = target is not None and temperature is not None and temperature >= 85
            effective = 255 if protected else target
            if effective is not None:
                changed = True
                pmc.set_pwm(effective)
            if time.monotonic() >= next_sample:
                values = pmc.read_ec_fixed()
                temperature = values[0x0558]
                pwm = values[0x1808]
                rpm = values[0x055c] * 256 + values[0x055d]
                emit({"event": "sample", "mode": mode, "pwm": pwm,
                      "target": target, "rpm": rpm, "cpu_c": temperature,
                      "thermal_override": bool(target is not None and temperature >= 85)})
                next_sample = time.monotonic() + 1
    finally:
        selector.close()
        if changed:
            pmc.set_pwm(previous if previous is not None else original)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("O controlador requer autenticação administrativa")
    lock = os.open("/run/acer-a515-pmc3.lock",
                   os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
            raise RuntimeError("Arquivo de exclusão inválido")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Outro controlador de ventoinha está ativo") from None
        pmc = pmc_module.PMC3()
        try:
            serve(pmc)
        finally:
            pmc.close()
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, BrokenPipeError) as error:
        try:
            emit({"event": "error", "message": str(error)})
        except BrokenPipeError:
            pass
        sys.exit(1)
