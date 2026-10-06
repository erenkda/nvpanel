import os
import shutil
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .backends import BackendError  # noqa: E402
from .model import RANGES, Settings, load_config, save_config  # noqa: E402

APP_ID = "io.github.nvpanel"
AUTOSTART = os.path.expanduser("~/.config/autostart/nvpanel.desktop")

DESCRIPTIONS = {
    "brightness": "Raise or lower the overall light level",
    "contrast": "Difference between dark and bright areas",
    "gamma": "Brightness of the midtones",
    "vibrance": "Boost muted colours without over-saturating vivid ones",
}

CSS = b"""
.value-label { font-feature-settings: "tnum"; min-width: 4.5em; }
"""


def _exec_cmd() -> str:
    exe = shutil.which("nvpanel")
    return exe if exe else f"{sys.executable} -m nvpanel"


def _fmt(key: str, value: float) -> str:
    unit = RANGES[key][4]
    if key == "gamma":
        return f"{value:.2f}"
    sign = "+" if value > 0 and key in ("brightness", "vibrance") else ""
    return f"{sign}{value:.0f}{unit}"


class Window(Adw.ApplicationWindow):
    def __init__(self, app, backend):
        super().__init__(application=app, title="NVIDIA Settings",
                         default_width=560, default_height=740)
        self.backend = backend
        self.config = load_config()
        self.monitors = backend.monitors()
        self._loading = False
        self._apply_src = 0
        self._save_src = 0
        self.scales = {}
        self.value_labels = {}

        caps = backend.capabilities
        notes = backend.unsupported_notes

        # --- header -------------------------------------------------------
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="NVIDIA Settings",
                                                subtitle=backend.title))
        reset_all = Gtk.Button(label="Reset all", tooltip_text="Restore defaults for this display")
        reset_all.connect("clicked", self._on_reset)
        header.pack_start(reset_all)

        # --- content ------------------------------------------------------
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                       margin_top=24, margin_bottom=24, margin_start=12, margin_end=12)

        display_group = Adw.PreferencesGroup(title="Display")
        self.combo = Adw.ComboRow(title="Monitor",
                                  subtitle="Settings are saved separately for each monitor")
        self.combo.set_model(Gtk.StringList.new([m.name for m in self.monitors]))
        self.combo.connect("notify::selected", lambda *_: self._load_monitor())
        display_group.add(self.combo)
        page.append(display_group)

        color_group = Adw.PreferencesGroup(
            title="Colour", description="Changes apply instantly and are remembered.")
        for key, (lo, hi, step, label, unit) in RANGES.items():
            color_group.add(self._make_row(key, caps, notes))
        page.append(color_group)

        general = Adw.PreferencesGroup(title="General")
        self.auto_row = Adw.SwitchRow(
            title="Apply saved settings at login",
            subtitle="Runs a small background helper that also re-applies after "
                     "resume and monitor changes",
            active=os.path.exists(AUTOSTART))
        self.auto_row.connect("notify::active", self._on_autostart)
        general.add(self.auto_row)
        page.append(general)

        clamp = Adw.Clamp(maximum_size=620, tightening_threshold=480, child=page)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=clamp)

        self.toasts = Adw.ToastOverlay(child=scroller)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

        if not self.monitors:
            self._toast("No active monitors found.")
        else:
            self._sync_screen_with_saved()
            self._load_monitor()

    # ------------------------------------------------------------------ rows
    def _make_row(self, key, caps, notes):
        lo, hi, step, label, unit = RANGES[key]
        supported = key in caps
        default = getattr(Settings(), key)

        title = Gtk.Label(label=label, xalign=0, hexpand=True, css_classes=["heading"])
        subtitle = Gtk.Label(
            label=DESCRIPTIONS[key] if supported else notes.get(key, "Not supported by this backend."),
            xalign=0, wrap=True, css_classes=["dim-label", "caption"])
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        text.append(title)
        text.append(subtitle)

        value = Gtk.Label(label=_fmt(key, default), xalign=1, valign=Gtk.Align.CENTER,
                          css_classes=["value-label", "numeric"])
        undo = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text=f"Reset {label.lower()}", css_classes=["flat", "circular"])
        undo.connect("clicked", lambda _b, k=key: self.scales[k].set_value(getattr(Settings(), k)))

        top = Gtk.Box(spacing=8)
        top.append(text)
        top.append(value)
        top.append(undo)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        scale.set_draw_value(False)
        scale.add_mark(default, Gtk.PositionType.BOTTOM, None)
        scale.connect("value-changed", self._on_changed, key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                      margin_top=12, margin_bottom=6, margin_start=14, margin_end=10)
        box.append(top)
        box.append(scale)

        row = Adw.PreferencesRow(child=box, activatable=False, focusable=False)
        row.set_sensitive(supported)
        self.scales[key] = scale
        self.value_labels[key] = value
        return row

    # ----------------------------------------------------------------- state
    def _toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

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
                self._toast(f"Error: {e}")

    @property
    def monitor(self):
        return self.monitors[self.combo.get_selected()]

    def _load_monitor(self):
        s = self.config.get(self.monitor.name, Settings())
        self._loading = True
        for key, scale in self.scales.items():
            scale.set_value(getattr(s, key))
            self.value_labels[key].set_text(_fmt(key, getattr(s, key)))
        self._loading = False

    def _current(self) -> Settings:
        return Settings(**{k: sc.get_value() for k, sc in self.scales.items()})

    def _on_changed(self, scale, key):
        self.value_labels[key].set_text(_fmt(key, scale.get_value()))
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
        except BackendError as e:
            self._toast(f"Error: {e}")
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
            self._toast(f"Could not save settings: {e}")
        return False

    def _on_reset(self, _btn):
        self._loading = True
        for key, scale in self.scales.items():
            scale.set_value(getattr(Settings(), key))
            self.value_labels[key].set_text(_fmt(key, getattr(Settings(), key)))
        self._loading = False
        self._apply_now()

    def _on_autostart(self, row, _p):
        try:
            if row.get_active():
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
            self._toast(f"Autostart error: {e}")


ICON_NAME = "nvpanel"
ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")


def run(backend) -> int:
    app = Adw.Application(application_id=APP_ID)

    def on_activate(a):
        from gi.repository import Gdk

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # Bundled icon, so the window icon also works when running from source.
        Gtk.IconTheme.get_for_display(display).add_search_path(ICON_DIR)
        Gtk.Window.set_default_icon_name(ICON_NAME)
        Window(a, backend).present()

    app.connect("activate", on_activate)
    return app.run([sys.argv[0]])
