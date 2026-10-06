import os
import shutil
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .backends import BackendError  # noqa: E402
from .model import RANGES, Settings, load_config, save_config  # noqa: E402

APP_ID = "io.github.nvpanel"
AUTOSTART = os.path.expanduser("~/.config/autostart/nvpanel.desktop")


def _exec_cmd() -> str:
    exe = shutil.which("nvpanel")
    return exe if exe else f"{sys.executable} -m nvpanel"


class Window(Gtk.ApplicationWindow):
    def __init__(self, app, backend):
        super().__init__(application=app, title="NVIDIA Settings", default_width=460)
        self.backend = backend
        self.config = load_config()
        self.monitors = backend.monitors()
        self._loading = False
        self._apply_src = 0
        self._save_src = 0

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        self.set_child(box)

        self.combo = Gtk.DropDown.new_from_strings([m.name for m in self.monitors])
        self.combo.connect("notify::selected", lambda *_: self._load_monitor())
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label="Display", xalign=0, hexpand=True))
        row.append(self.combo)
        box.append(row)

        self.scales = {}
        for key, (lo, hi, step, label, unit) in RANGES.items():
            supported = key in backend.capabilities
            box.append(Gtk.Label(label=f"{label}", xalign=0))
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
            scale.set_draw_value(True)
            scale.set_digits(2 if key == "gamma" else 0)
            if unit:
                scale.set_format_value_func(
                    lambda s, v, u=unit: f"{v:.0f}{u}")
            scale.set_sensitive(supported)
            if not supported:
                note = backend.unsupported_notes.get(key, "Not supported by this backend.")
                scale.set_tooltip_text(note)
                box.append(Gtk.Label(label=note, xalign=0, wrap=True, css_classes=["dim-label"]))
            scale.connect("value-changed", self._on_changed, key)
            box.append(scale)
            self.scales[key] = scale

        self.status = Gtk.Label(xalign=0, wrap=True)
        box.append(self.status)

        buttons = Gtk.Box(spacing=8)
        reset = Gtk.Button(label="Reset")
        reset.connect("clicked", self._on_reset)
        buttons.append(reset)
        box.append(buttons)

        auto = Gtk.Box(spacing=8)
        auto.append(Gtk.Label(label="Apply saved settings at login", xalign=0, hexpand=True))
        self.auto_switch = Gtk.Switch(active=os.path.exists(AUTOSTART), valign=Gtk.Align.CENTER)
        self.auto_switch.connect("notify::active", self._on_autostart)
        auto.append(self.auto_switch)
        box.append(auto)

        box.append(Gtk.Label(label=f"Backend: {backend.title}", xalign=0,
                             css_classes=["dim-label"]))
        if not self.monitors:
            self.status.set_text("No active monitors found.")
        else:
            self._sync_screen_with_saved()
            self._load_monitor()

    def _sync_screen_with_saved(self):
        """Make the screen match what the sliders will show.

        Without this the sliders display the saved values while the screen still
        has whatever state was applied last (or nothing), so the first slider move
        applies every value at once and the picture jumps.
        """
        for mon in self.monitors:
            try:
                self.backend.apply(mon, self.config.get(mon.name, Settings()))
            except BackendError as e:
                self.status.set_text(f"Error: {e}")

    @property
    def monitor(self):
        return self.monitors[self.combo.get_selected()]

    def _load_monitor(self):
        s = self.config.get(self.monitor.name, Settings())
        self._loading = True
        for key, scale in self.scales.items():
            scale.set_value(getattr(s, key))
        self._loading = False

    def _current(self) -> Settings:
        return Settings(**{k: sc.get_value() for k, sc in self.scales.items()})

    def _on_changed(self, scale, key):
        if self._loading:
            return
        if self._apply_src:
            GLib.source_remove(self._apply_src)
        self._apply_src = GLib.timeout_add(40, self._apply_now)

    def _apply_now(self):
        self._apply_src = 0
        s = self._current()
        try:
            self.backend.apply(self.monitor, s)
            self.status.set_text("")
        except BackendError as e:
            self.status.set_text(f"Error: {e}")
            return False
        if s.is_default():
            self.config.pop(self.monitor.name, None)
        else:
            self.config[self.monitor.name] = s
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(500, self._save_now)
        return False

    def _save_now(self):
        self._save_src = 0
        try:
            save_config(self.config)
        except OSError as e:
            self.status.set_text(f"Could not save settings: {e}")
        return False

    def _on_reset(self, _btn):
        self._loading = True
        for key, scale in self.scales.items():
            scale.set_value(getattr(Settings(), key))
        self._loading = False
        self._apply_now()

    def _on_autostart(self, switch, _p):
        try:
            if switch.get_active():
                os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
                with open(AUTOSTART, "w") as f:
                    f.write(
                        "[Desktop Entry]\nType=Application\nName=NVIDIA Settings (apply)\n"
                        f"Exec={_exec_cmd()} --daemon\nNoDisplay=true\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            elif os.path.exists(AUTOSTART):
                os.remove(AUTOSTART)
        except OSError as e:
            self.status.set_text(f"Autostart error: {e}")


def run(backend) -> int:
    app = Gtk.Application(application_id=APP_ID)
    app.connect("activate", lambda a: Window(a, backend).present())
    return app.run([sys.argv[0]])
