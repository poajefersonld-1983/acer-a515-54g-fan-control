#!/usr/bin/env python3
"""Validated maximum fan control for Acer A515-54G / BIOS V1.24 / IT8987.

PMC3 command 0x7e reads PWM6; 0x7d + one data byte writes PWM6.
No flash writes, EC mode changes, logical device activation or raw EC setters.
The firmware's automatic loop stays enabled. Maximum requires periodic writes.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time


class PMC3:
    def __init__(self):
        expected = {"product_name": "Aspire A515-54G", "board_name": "Doc_WC",
                    "bios_version": "V1.24"}
        for name, value in expected.items():
            actual = Path("/sys/class/dmi/id", name).read_text().strip()
            if actual != value:
                raise RuntimeError(f"Hardware/BIOS não validado: {name}={actual}")
        self.fd = os.open("/dev/port", os.O_RDWR | os.O_CLOEXEC)
        try:
            self.check_config()
        except BaseException:
            self.close()
            raise

    def close(self):
        os.close(self.fd)

    def read(self, port):
        data = os.pread(self.fd, 1, port)
        if len(data) != 1:
            raise RuntimeError("Leitura de porta incompleta")
        return data[0]

    def write(self, port, value):
        if os.pwrite(self.fd, bytes([value]), port) != 1:
            raise RuntimeError("Escrita de porta incompleta")

    def check_config(self):
        # Only index/LDN selection is written; both selectors are restored.
        saved_index = self.read(0x2e)

        def indexed(index):
            self.write(0x2e, index)
            return self.read(0x2f)

        try:
            if (indexed(0x20), indexed(0x21)) != (0x89, 0x87):
                raise RuntimeError("IT8987 não identificado na porta 0x2e")
            saved_ldn = indexed(7)
            try:
                self.write(0x2e, 7)
                self.write(0x2f, 0x17)
                config = tuple(indexed(i) for i in (0x30, 0x60, 0x61, 0x62, 0x63))
                if config != (1, 0, 0x6a, 0, 0x6e):
                    raise RuntimeError(f"Configuração PMC3 não validada: {config}")
            finally:
                self.write(0x2e, 7)
                self.write(0x2f, saved_ldn)
        finally:
            self.write(0x2e, saved_index)

    def wait(self, mask, expected):
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            status = self.read(0x6e)
            if status & mask == expected:
                return
            time.sleep(0.001)
        raise RuntimeError("PMC3 sem resposta em 250 ms")

    def command(self, command):
        if self.read(0x6e) & 3:
            raise RuntimeError("PMC3 ocupado; operação interrompida")
        self.write(0x6e, command)
        self.wait(2, 0)

    def pwm(self):
        self.command(0x7e)
        self.wait(3, 1)
        return self.read(0x6a)

    def read_ec_fixed(self):
        """Read documented fixed telemetry/config through already-enabled I2EC.

        Only address selectors are written. All selectors are restored.
        No enable bits or EC register contents are written here.
        """
        saved_index = self.read(0x2e)
        saved_sub = saved_hi = saved_lo = None

        def select(sub):
            self.write(0x2e, 0x2e)
            self.write(0x2f, sub)
            self.write(0x2e, 0x2f)

        def memory(address):
            select(0x11)
            self.write(0x2f, address >> 8)
            select(0x10)
            self.write(0x2f, address & 255)
            select(0x12)
            return self.read(0x2f)

        try:
            self.write(0x2e, 0x2e)
            saved_sub = self.read(0x2f)
            select(0x11)
            saved_hi = self.read(0x2f)
            select(0x10)
            saved_lo = self.read(0x2f)
            if (memory(0x2000), memory(0x2001)) != (0x89, 0x87):
                raise RuntimeError("Leitura I2EC não disponível; não será habilitada")
            values = {address: memory(address) for address in
                      (0x180d, 0x1841, 0x180a, 0x1808, 0x0558, 0x055c, 0x055d)}
            # CPUF is a big-endian RPM value, corroborated by ACPI EC and WMI.
            for _ in range(3):
                high = memory(0x055c)
                low = memory(0x055d)
                if high == memory(0x055c):
                    values[0x055c], values[0x055d] = high, low
                    break
            else:
                raise RuntimeError("Tacômetro mudou durante a leitura")
            return values
        finally:
            if saved_hi is not None:
                select(0x11)
                self.write(0x2f, saved_hi)
            if saved_lo is not None:
                select(0x10)
                self.write(0x2f, saved_lo)
            if saved_sub is not None:
                self.write(0x2e, 0x2e)
                self.write(0x2f, saved_sub)
            self.write(0x2e, saved_index)

    def validate_pwm_limit(self):
        values = self.read_ec_fixed()
        if ((values[0x180d] >> 4) & 3) != 1 or values[0x1841] != 255 or values[0x180a] & 64:
            raise RuntimeError("Contador/polaridade PWM6 fora da configuração testada")
        self.maximum_pwm = 255
        return values

    def set_pwm(self, pwm):
        if not 1 <= pwm <= getattr(self, "maximum_pwm", 183):
            raise RuntimeError("PWM fora da faixa validada")
        self.command(0x7d)
        self.write(0x6a, pwm)
        self.wait(2, 0)


def duration(value):
    seconds = float(value)
    if not 1 <= seconds <= 3600:
        raise argparse.ArgumentTypeError("Use entre 1 e 3600 segundos")
    return seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "max"))
    parser.add_argument("--seconds", type=duration,
                        help="Duração do máximo; sem esta opção, termine com Ctrl+C")
    args = parser.parse_args()
    if args.action == "status" and args.seconds is not None:
        parser.error("--seconds só se aplica a max")
    if os.geteuid() != 0:
        parser.error("Execute pelo launcher pmc3-fan (usa pkexec)")
    lock = os.open("/run/acer-a515-pmc3.lock",
                   os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
            raise RuntimeError("Arquivo de exclusão inválido")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Outro controlador PMC3 está ativo") from None
        pmc = PMC3()
        try:
            pmc.validate_pwm_limit()
            original = pmc.pwm()
            if args.action == "status":
                print(json.dumps({"model": "A515-54G", "bios": "V1.24",
                                  "channel": "PMC3", "pwm": original,
                                  "maximum_pwm": pmc.maximum_pwm}))
                return
            if not 1 <= original <= pmc.maximum_pwm:
                raise RuntimeError(f"PWM inicial inesperado: {original}")
            stopped = False

            def stop(*_):
                nonlocal stopped
                stopped = True

            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, stop)
            print("Ventoinha no máximo. Ctrl+C encerra e devolve ao automático.", flush=True)
            started = time.monotonic()
            try:
                while not stopped and (args.seconds is None or
                                       time.monotonic() - started < args.seconds):
                    pmc.set_pwm(pmc.maximum_pwm)
                    time.sleep(0.15)
            finally:
                # No manual-mode flag was set. Restore the starting duty once;
                # the active firmware loop then adjusts it to current conditions.
                pmc.set_pwm(original)
                print("Controle devolvido ao firmware automático.", flush=True)
        finally:
            pmc.close()
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        sys.exit(1)
