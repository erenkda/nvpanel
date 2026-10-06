"""Settings model, gamma-ramp math and on-disk persistence."""
import json
import os
from dataclasses import asdict, dataclass, fields

CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "nvpanel",
    "config.json",
)


@dataclass
class Settings:
    brightness: float = 0.0  # -50 .. 50  (percent offset)
    contrast: float = 100.0  # 30 .. 150  (percent)
    gamma: float = 1.0  # 0.4 .. 2.8
    vibrance: float = 0.0  # -100 .. 100 (percent of the driver range)

    def clamped(self) -> "Settings":
        return Settings(
            brightness=min(50.0, max(-50.0, self.brightness)),
            contrast=min(150.0, max(30.0, self.contrast)),
            gamma=min(2.8, max(0.4, self.gamma)),
            vibrance=min(100.0, max(-100.0, self.vibrance)),
        )

    def is_default(self) -> bool:
        return self == Settings()

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in data.items() if k in known}).clamped()


# Ranges used by the GUI: key -> (min, max, step, label, unit)
RANGES = {
    "brightness": (-50.0, 50.0, 1.0, "Brightness", "%"),
    "contrast": (30.0, 150.0, 1.0, "Contrast", "%"),
    "gamma": (0.4, 2.8, 0.01, "Gamma", ""),
    "vibrance": (-100.0, 100.0, 1.0, "Digital Vibrance", "%"),
}


def build_ramp(s: Settings, size: int) -> list:
    """16-bit ramp implementing contrast -> brightness -> gamma."""
    s = s.clamped()
    inv_gamma = 1.0 / s.gamma
    ramp = []
    for i in range(size):
        x = i / (size - 1)
        y = (x - 0.5) * (s.contrast / 100.0) + 0.5 + s.brightness / 100.0
        y = min(1.0, max(0.0, y)) ** inv_gamma
        ramp.append(int(round(y * 65535)))
    return ramp


def load_config() -> dict:
    """Return {monitor_name: Settings}."""
    try:
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
        return {name: Settings.from_dict(v) for name, v in raw.get("monitors", {}).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def save_config(config: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"monitors": {k: asdict(v) for k, v in config.items()}}, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
