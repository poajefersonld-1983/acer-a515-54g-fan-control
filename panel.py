#!/usr/bin/env python3
"""Acer Fan Control: native desktop panel for the validated A515-54G controller."""
from collections import deque
import json
from pathlib import Path
import subprocess
import socket
import sys
import threading
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

HERE = Path(__file__).resolve().parent
CSS = b"""
window { background: #101722; color: #edf3fa; }
.app-title { font-size: 26px; font-weight: 800; }
.muted { color: #99abc2; }
.card { background: #1a2433; border-radius: 16px; padding: 16px; }
.rpm { font-size: 46px; font-weight: 800; color: #65d6c7; }
.sensor { font-size: 26px; font-weight: 700; }
.section { font-size: 16px; font-weight: 700; }
button { border-radius: 10px; padding: 10px 14px; }
button.active { background: #246d72; color: white; }
button.max { background: #315fcc; color: white; }
.badge { color: #65d6c7; font-weight: 700; }
scale trough { min-height: 7px; border-radius: 6px; }
scale highlight { background: #65d6c7; }
"""


def label(text, css=None):
    widget = Gtk.Label(label=text, xalign=0)
    if css:
        widget.add_css_class(css)
    return widget


class FanPanel(Gtk.Application):
    def __init__(self, smoke=False):
        super().__init__(application_id="local.acer.FanControl")
        self.smoke = smoke
        self.process = None
        self.connecting = False
        self.connected = False
        self.closing = False
        self.samples = deque(maxlen=90)
        self.mode = "auto"
        self.last_error = ""

    def do_activate(self):
        if self.get_active_window():
            self.get_active_window().present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 600)
        self.window = Gtk.ApplicationWindow(application=self, title="Acer Fan Control")
        self.window.set_default_size(740, 880)
        self.window.set_icon_name("acer-fan-control")
        self.window.connect("close-request", self.close_panel)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(root, "set_margin_" + side)(24)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(root)
        self.window.set_child(scroll)
        heading = Gtk.Box(spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        titles.append(label("Acer Fan Control", "app-title"))
        titles.append(label("Aspire A515-54G  ·  GeForce MX250", "muted"))
        heading.append(titles)
        self.connection = Gtk.Button(label="Conectar")
        self.connection.connect("clicked", self.connect_controller)
        heading.append(self.connection)
        root.append(heading)
        self.state = label("Controle automático do notebook", "badge")
        root.append(self.state)
        sensors = Gtk.Box(spacing=12, homogeneous=True)
        self.rpm_label = self.sensor_card(sensors, "VENTOINHA", "—", "rpm", "RPM")
        self.cpu_label = self.sensor_card(sensors, "PROCESSADOR", "—", "sensor", "°C")
        self.gpu_label = self.sensor_card(sensors, "GEFORCE MX250", "—", "sensor", "°C")
        root.append(sensors)
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        controls.add_css_class("card")
        controls.append(label("Modo da ventoinha", "section"))
        row = Gtk.Box(spacing=8, homogeneous=True)
        self.buttons = {}
        for action, text in (("auto", "Automático"), ("manual", "Personalizado"), ("max", "Máximo · 100%")):
            button = Gtk.Button(label=text)
            button.connect("clicked", self.choose_mode, action)
            if action == "max":
                button.add_css_class("max")
            row.append(button)
            self.buttons[action] = button
        controls.append(row)
        slider_row = Gtk.Box(spacing=12)
        slider_row.append(label("Velocidade manual", "muted"))
        self.percent = label("85%", "section")
        self.percent.set_hexpand(True)
        self.percent.set_xalign(1)
        slider_row.append(self.percent)
        controls.append(slider_row)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 72, 100, 1)
        self.scale.set_value(85)
        self.scale.set_draw_value(False)
        self.scale.connect("value-changed", self.slider_changed)
        controls.append(self.scale)
        self.manual_note = label("Faixa manual testada: 72–100%. Automático ajusta toda a faixa.", "muted")
        self.manual_note.set_wrap(True)
        controls.append(self.manual_note)
        root.append(controls)
        self.save_button = Gtk.Button(label="Salvar e manter funcionando")
        self.save_button.connect("clicked", self.save_settings)
        controls.append(self.save_button)
        self.saved_label = label("Nenhum perfil mantido em segundo plano.", "muted")
        self.saved_label.set_wrap(True)
        controls.append(self.saved_label)
        graph_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        graph_box.add_css_class("card")
        graph_header = Gtk.Box()
        graph_header.append(label("Rotação em tempo real", "section"))
        self.pwm_label = label("Aguardando leitura", "muted")
        self.pwm_label.set_hexpand(True)
        self.pwm_label.set_xalign(1)
        graph_header.append(self.pwm_label)
        graph_box.append(graph_header)
        self.graph = Gtk.DrawingArea(content_height=84, hexpand=True)
        self.graph.set_draw_func(self.draw_graph)
        graph_box.append(self.graph)
        graph_box.append(label("Teto medido: ≈ 5.800 RPM  ·  pico observado: 5.972 RPM", "muted"))
        root.append(graph_box)
        self.message = label("Conecte para acompanhar as leituras e controlar a ventoinha.", "muted")
        self.message.set_wrap(True)
        root.append(self.message)
        foot = label("Ao fechar, o perfil salvo continua ativo.\nAutomático desativa o controle salvo.", "muted")
        root.append(foot)
        self.set_controls(False)
        GLib.timeout_add_seconds(4, self.heartbeat)
        self.window.present()
        if self.smoke:
            GLib.timeout_add(250, self.smoke_test)
        elif Path("/run/acer-fan-control/control.sock").exists():
            GLib.idle_add(self.connect_controller)

    def sensor_card(self, parent, heading, value, css, unit):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("card")
        card.append(label(heading, "muted"))
        number = label(value, css)
        card.append(number)
        card.append(label(unit, "muted"))
        parent.append(card)
        return number

    def set_controls(self, ready):
        for button in self.buttons.values():
            button.set_sensitive(ready)
        self.scale.set_sensitive(ready)
        self.save_button.set_sensitive(ready)

    def connect_controller(self, *_):
        if self.process is not None or self.connecting:
            return
        self.connecting = True
        self.connection.set_sensitive(False)
        self.connection.set_label("Conectando…")
        self.message.set_text("Conectando ao controlador; a primeira instalação pede autenticação…")
        threading.Thread(target=self.read_backend, daemon=True).start()

    def read_backend(self):
        connection = None
        error_text = ""
        try:
            def connect_socket():
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    connection.connect("/run/acer-fan-control/control.sock")
                    return connection
                except OSError:
                    connection.close()
                    raise
            try:
                connection = connect_socket()
            except OSError:
                installed = subprocess.run(
                    ["/usr/bin/pkexec", "--disable-internal-agent", "/usr/bin/python3", "-I", str(HERE / "setup-service.py")],
                    capture_output=True, text=True)
                if installed.returncode:
                    raise RuntimeError(installed.stderr.strip() or "Autenticação cancelada")
                import time
                for attempt in range(30):
                    try:
                        connection = connect_socket()
                        break
                    except OSError:
                        if attempt == 29:
                            raise
                        time.sleep(.1)
            if self.closing:
                return
            self.process = connection
            with connection.makefile("r") as stream:
                for line in stream:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    GLib.idle_add(self.receive, message)
        except (OSError, RuntimeError) as error:
            error_text = str(error)
        finally:
            if connection is not None:
                connection.close()
            GLib.idle_add(self.backend_exited, error_text)

    def send(self, action, **extra):
        if not self.process:
            return
        try:
            self.process.sendall((json.dumps({"action": action, **extra}) + "\n").encode())
        except (OSError, ValueError):
            self.message.set_text("Conexão encerrada. Reconecte para controlar a ventoinha.")

    def receive(self, data):
        if self.closing:
            return False
        event = data.get("event")
        if event == "ready":
            self.sync_saved_slider = True
            self.connected = True
            self.set_controls(True)
            self.connection.set_label("Conectado")
            self.message.set_text("Controle conectado. Escolha um modo e salve para mantê-lo ativo.")
            self.update_saved(data)
        elif event == "saved":
            self.update_saved(data)
            self.message.set_text("Configuração salva. Continua funcionando com a janela fechada e após reiniciar.")
        elif event == "error":
            self.last_error = data.get("message", "Falha no controlador")
            self.message.set_text(self.last_error)
        elif event == "sample":
            self.update_saved(data)
            self.mode = data["mode"]
            if getattr(self, "sync_saved_slider", False):
                self.sync_saved_slider = False
                if self.mode == "manual" and data.get("target") is not None:
                    self.synchronizing = True
                    self.scale.set_value(round(data["target"] * 100 / 255))
                    self.synchronizing = False
            self.rpm_label.set_text(f"{data['rpm']:,}".replace(",", "."))
            self.cpu_label.set_text(str(data["cpu_c"]))
            self.pwm_label.set_text(f"PWM atual: {data['pwm'] / 255 * 100:.0f}%")
            self.state.set_text({"auto": "Automático · regulado pelo notebook",
                                 "manual": "Velocidade personalizada",
                                 "max": "Máximo · ventilação a 100%"}[self.mode])
            if data.get("thermal_override"):
                self.state.set_text("Proteção térmica · velocidade máxima")
            if getattr(self, "pending_mode", None) == self.mode:
                self.message.set_text("Modo aplicado. Leituras atualizadas a cada segundo.")
                self.pending_mode = None
            for action, button in self.buttons.items():
                (button.add_css_class if action == self.mode else button.remove_css_class)("active")
            self.samples.append(data["rpm"])
            self.graph.queue_draw()
        return False

    def update_saved(self, data):
        saved_mode = data.get("saved_mode", "auto")
        if saved_mode == "max":
            text = "Salvo: máximo · 100%. Ativo em segundo plano e ao iniciar o sistema."
        elif saved_mode == "manual":
            text = f"Salvo: personalizado · {data['saved_pwm'] / 255 * 100:.0f}%. Ativo em segundo plano e ao iniciar o sistema."
        else:
            text = "Automático. Nenhum ajuste manual salvo em segundo plano."
        self.saved_label.set_text(text)

    def save_settings(self, *_):
        self.send("save")
        self.message.set_text("Salvando o modo atual…")

    def choose_mode(self, button, action):
        self.pending_mode = action
        if action == "manual":
            self.send("manual", pwm=max(183, round(self.scale.get_value() * 255 / 100)))
        else:
            self.send(action)
        self.message.set_text("Aplicando modo…")

    def slider_changed(self, scale):
        self.percent.set_text(f"{scale.get_value():.0f}%")
        if self.connected and self.mode == "manual" and not getattr(self, "synchronizing", False):
            self.send("manual", pwm=max(183, round(scale.get_value() * 255 / 100)))

    def heartbeat(self):
        if self.closing:
            return False
        if self.connected:
            self.send("ping")
            threading.Thread(target=self.read_gpu, daemon=True).start()
        return True

    def read_gpu(self):
        try:
            output = subprocess.check_output(
                ["/usr/bin/nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                timeout=2, text=True, stderr=subprocess.DEVNULL)
            value = str(int(output.strip().splitlines()[0]))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            value = "—"
        GLib.idle_add(self.gpu_label.set_text, value)

    def backend_exited(self, stderr):
        self.process = None
        self.connecting = False
        self.connected = False
        if self.closing:
            self.window.destroy()
            self.quit()
            return False
        self.set_controls(False)
        self.connection.set_label("Reconectar")
        self.connection.set_sensitive(True)
        self.state.set_text("Desconectado do painel · perfil salvo gerenciado em segundo plano")
        self.message.set_text(self.last_error or stderr or "Conexão encerrada ou autenticação cancelada.")
        self.last_error = ""
        return False

    def close_panel(self, *_):
        self.closing = True
        if self.process:
            self.send("quit")
            try:
                self.process.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        # The root service retains the saved profile; unsaved overrides end here.
        return False

    def draw_graph(self, area, cr, width, height):
        cr.set_line_width(1)
        cr.set_source_rgba(.6, .7, .8, .13)
        for fraction in (.25, .5, .75):
            cr.move_to(0, height * fraction)
            cr.line_to(width, height * fraction)
        cr.stroke()
        if len(self.samples) < 2:
            return
        points = [(i * width / 89, height - min(rpm, 6500) / 6500 * (height - 12))
                  for i, rpm in enumerate(self.samples)]
        cr.move_to(*points[0])
        for point in points[1:]:
            cr.line_to(*point)
        cr.set_source_rgb(.396, .839, .780)
        cr.set_line_width(2.5)
        cr.stroke()

    def smoke_test(self):
        self.receive({"event": "ready"})
        for rpm in (3800, 4250, 5100, 5800):
            self.receive({"event": "sample", "mode": "max", "pwm": 255,
                          "rpm": rpm, "cpu_c": 72, "thermal_override": False})
        assert self.rpm_label.get_text() == "5.800"
        assert self.buttons["auto"].get_sensitive()
        self.scale.set_value(92)
        assert self.percent.get_text() == "92%"
        self.gpu_label.set_text("57")
        self.message.set_text("Verificação visual · dados simulados")
        GLib.timeout_add_seconds(5, self.finish_smoke)
        return False

    def finish_smoke(self):
        self.window.close()
        self.quit()
        return False


if __name__ == "__main__":
    smoke = "--smoke-test" in sys.argv
    raise SystemExit(FanPanel(smoke).run([]))
