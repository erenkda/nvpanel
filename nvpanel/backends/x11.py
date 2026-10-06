"""X11 backend: nvidia-settings for Digital Vibrance, xrandr for brightness/gamma."""
import os
import re
import shutil
import subprocess

from ..model import Settings
from .base import Backend, BackendError, Monitor

_FALLBACK_RANGE = (-1024, 1023)


def _run(cmd, timeout=10):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise BackendError(f"{cmd[0]}: {e}")


class X11Backend(Backend):
    id = "x11"
    title = "X11 (nvidia-settings + xrandr)"
    capabilities = frozenset({"brightness", "gamma", "vibrance"})
    unsupported_notes = {
        "contrast": "Contrast is not available on X11 (xrandr has no contrast control)."
    }

    def __init__(self):
        self._ranges = {}

    @classmethod
    def available(cls) -> bool:
        return bool(
            os.environ.get("DISPLAY")
            and os.environ.get("XDG_SESSION_TYPE", "x11") == "x11"
            and shutil.which("xrandr")
        )

    def monitors(self) -> list:
        out = _run(["xrandr", "--query"]).stdout
        return [
            Monitor(m.group(1))
            for m in re.finditer(r"^(\S+) connected", out, re.MULTILINE)
        ]

    def _vibrance_range(self, name):
        if name not in self._ranges:
            res = _run(["nvidia-settings", "-q", f"[dpy:{name}]/DigitalVibrance"])
            m = re.search(r"range\s+(-?\d+)\s*-\s*(-?\d+)", res.stdout)
            self._ranges[name] = (
                (int(m.group(1)), int(m.group(2))) if m else _FALLBACK_RANGE
            )
        return self._ranges[name]

    def apply(self, monitor: Monitor, settings: Settings) -> None:
        s = settings.clamped()
        g = f"{s.gamma:.4f}"  # same convention as ours: ramp = x ** (1/gamma)
        res = _run([
            "xrandr", "--output", monitor.name,
            "--brightness", f"{1 + s.brightness / 100:.4f}",
            "--gamma", f"{g}:{g}:{g}",
        ])
        if res.returncode:
            raise BackendError(res.stderr.strip() or "xrandr failed")

        if shutil.which("nvidia-settings"):
            lo, hi = self._vibrance_range(monitor.name)
            value = round(s.vibrance / 100 * (hi if s.vibrance >= 0 else -lo))
            res = _run([
                "nvidia-settings", "-a", f"[dpy:{monitor.name}]/DigitalVibrance={value}",
            ])
            if res.returncode:
                raise BackendError(
                    res.stderr.strip() or "nvidia-settings failed to set DigitalVibrance"
                )
        elif s.vibrance:
            raise BackendError("nvidia-settings is not installed")
