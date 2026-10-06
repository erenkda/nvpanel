import argparse
import sys

from . import __version__
from .backends import BackendError, pick_backend
from .model import RANGES, Settings, load_config


def _apply_saved(backend) -> int:
    config = load_config()
    failures = 0
    for mon in backend.monitors():
        if mon.name in config:
            try:
                backend.apply(mon, config[mon.name])
            except BackendError as e:
                print(f"{mon.name}: {e}", file=sys.stderr)
                failures += 1
    return 1 if failures else 0


def _install_extension() -> int:
    import os
    import shutil
    import subprocess

    uuid = "nvpanel-vibrance@nvpanel.github.io"
    src = os.path.join(os.path.dirname(__file__), "gnome-extension", uuid)
    dst = os.path.join(os.path.expanduser("~/.local/share/gnome-shell/extensions"), uuid)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    print(f"Installed to {dst}")
    res = subprocess.run(["gnome-extensions", "enable", uuid], capture_output=True, text=True)
    if res.returncode == 0:
        print("Enabled. On Wayland, log out and back in once so GNOME Shell loads it.")
    else:
        print("Could not enable it automatically. After logging out and back in, run:")
        print(f"  gnome-extensions enable {uuid}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="nvpanel", description="NVIDIA display settings for Linux"
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--backend", choices=["x11", "mutter"], help="force a backend")
    p.add_argument("--list", action="store_true", help="list monitors and capabilities")
    p.add_argument("--apply", action="store_true", help="apply saved settings and exit")
    p.add_argument("--daemon", action="store_true",
                   help="apply saved settings and re-apply on monitor change / resume")
    p.add_argument("--install-extension", action="store_true",
                   help="install the GNOME Shell extension that provides Digital Vibrance")
    p.add_argument("--reset", action="store_true", help="reset all monitors to defaults")
    p.add_argument("--monitor", help="monitor for --set (default: first)")
    p.add_argument("--set", nargs="+", metavar="KEY=VALUE",
                   help="set values, e.g. --set brightness=10 gamma=1.2")
    args = p.parse_args(argv)

    if args.install_extension:
        return _install_extension()

    try:
        backend = pick_backend(args.backend)
    except BackendError as e:
        print(f"nvpanel: {e}", file=sys.stderr)
        return 2

    try:
        if args.list:
            print(f"backend: {backend.title}")
            print(f"supports: {', '.join(sorted(backend.capabilities))}")
            for m in backend.monitors():
                print(f"monitor: {m.name}")
            return 0
        if args.reset:
            for m in backend.monitors():
                backend.reset(m)
            return 0
        if args.set:
            mons = backend.monitors()
            mon = next((m for m in mons if m.name == args.monitor), None) if args.monitor else (mons[0] if mons else None)
            if mon is None:
                print("nvpanel: monitor not found", file=sys.stderr)
                return 2
            s = load_config().get(mon.name, Settings())
            for item in args.set:
                key, _, val = item.partition("=")
                if key not in RANGES:
                    print(f"nvpanel: unknown key '{key}' (use {', '.join(RANGES)})", file=sys.stderr)
                    return 2
                setattr(s, key, float(val))
            backend.apply(mon, s.clamped())
            return 0
        if args.apply:
            return _apply_saved(backend)
        if args.daemon:
            from gi.repository import GLib

            _apply_saved(backend)
            backend.watch(lambda: _apply_saved(backend) and False)
            try:
                GLib.MainLoop().run()
            except KeyboardInterrupt:
                pass
            return 0
    except BackendError as e:
        print(f"nvpanel: {e}", file=sys.stderr)
        return 1

    from .gui import run

    return run(backend)
