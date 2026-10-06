"""GNOME Wayland (and X11) backend using Mutter's DisplayConfig gamma API."""
from gi.repository import Gio, GLib

from ..model import Settings, build_ramp
from .base import Backend, BackendError, Monitor

_NAME = "org.gnome.Mutter.DisplayConfig"
_PATH = "/org/gnome/Mutter/DisplayConfig"
_VIBRANCE_NAME = "io.github.nvpanel.Vibrance"
_VIBRANCE_PATH = "/io/github/nvpanel/Vibrance"


class MutterBackend(Backend):
    id = "mutter"
    title = "GNOME (Mutter gamma)"

    @property
    def capabilities(self):
        caps = {"brightness", "contrast", "gamma"}
        if self._extension_running():
            caps.add("vibrance")
        return frozenset(caps)

    @property
    def unsupported_notes(self):
        if self._extension_running():
            return {}
        return {
            "vibrance": "Needs the nvpanel GNOME Shell extension: run "
            "'nvpanel --install-extension', then log out and back in."
        }

    def _extension_running(self) -> bool:
        try:
            r = self._bus.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                "NameHasOwner", GLib.Variant("(s)", (_VIBRANCE_NAME,)),
                GLib.VariantType("(b)"), Gio.DBusCallFlags.NONE, 2000,
            )
            return r.unpack()[0]
        except GLib.Error:
            return False

    def __init__(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        except GLib.Error as e:
            raise BackendError(str(e))

    @classmethod
    def available(cls) -> bool:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            bus.call_sync(
                _NAME, _PATH, _NAME, "GetResources", None, None,
                Gio.DBusCallFlags.NONE, 2000,
            )
            return True
        except GLib.Error:
            return False

    def _call(self, method, args=None, reply=None):
        try:
            return self._bus.call_sync(
                _NAME, _PATH, _NAME, method, args, reply, Gio.DBusCallFlags.NONE, 5000
            )
        except GLib.Error as e:
            raise BackendError(f"{method}: {e.message}")

    def _resources(self):
        serial, crtcs, outputs = self._call("GetResources").unpack()[:3]
        return serial, outputs

    def monitors(self) -> list:
        _, outputs = self._resources()
        # output = (id, winsys_id, current_crtc, possible_crtcs, name, ...)
        return [Monitor(o[4]) for o in outputs if o[2] >= 0]

    def apply(self, monitor: Monitor, settings: Settings) -> None:
        serial, outputs = self._resources()
        crtc = next((o[2] for o in outputs if o[4] == monitor.name and o[2] >= 0), None)
        if crtc is None:
            raise BackendError(f"Monitor {monitor.name} is not active")
        size = len(
            self._call(
                "GetCrtcGamma", GLib.Variant("(uu)", (serial, crtc)),
                GLib.VariantType("(aqaqaq)"),
            ).unpack()[0]
        )
        if size < 2:
            raise BackendError(f"{monitor.name}: gamma ramp not available")
        ramp = build_ramp(settings, size)
        self._call(
            "SetCrtcGamma", GLib.Variant("(uuaqaqaq)", (serial, crtc, ramp, ramp, ramp))
        )
        self._set_vibrance(settings.clamped().vibrance / 100.0)

    def _set_vibrance(self, value: float) -> None:
        """The shell extension applies vibrance to the whole desktop (all monitors)."""
        if not self._extension_running():
            return
        try:
            self._bus.call_sync(
                _VIBRANCE_NAME, _VIBRANCE_PATH, _VIBRANCE_NAME, "Set",
                GLib.Variant("(d)", (value,)), None, Gio.DBusCallFlags.NONE, 2000,
            )
        except GLib.Error as e:
            raise BackendError(f"vibrance: {e.message}")

    def watch(self, callback) -> None:
        self._bus.signal_subscribe(
            _NAME, _NAME, "MonitorsChanged", _PATH, None, Gio.DBusSignalFlags.NONE,
            lambda *a: GLib.timeout_add(500, lambda: callback() and False),
        )
        # Re-apply after resume from suspend.
        self._bus.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Manager",
            "PrepareForSleep", "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE,
            lambda c, s, p, i, sig, params: (not params.unpack()[0])
            and GLib.timeout_add(1500, lambda: callback() and False),
        )
