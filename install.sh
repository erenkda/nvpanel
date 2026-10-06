#!/usr/bin/env bash
# nvpanel installer: installs dependencies for your distro, then installs
# nvpanel into ~/.local (no pip, no root needed for nvpanel itself).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
SKIP_DEPS=0
for a in "$@"; do [ "$a" = "--no-deps" ] && SKIP_DEPS=1; done

install_deps() {
    . /etc/os-release
    local ids=" ${ID:-} ${ID_LIKE:-} "
    local sudo=""; [ "$(id -u)" -ne 0 ] && sudo="sudo"
    case "$ids" in
    *" ubuntu "*|*" debian "*|*" linuxmint "*|*" pop "*)
        $sudo apt-get update
        $sudo apt-get install -y python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 x11-xserver-utils
        $sudo apt-get install -y nvidia-settings || echo "note: nvidia-settings not installed (only needed on X11)" ;;
    *" fedora "*|*" rhel "*|*" centos "*)
        $sudo dnf install -y python3 python3-gobject gtk4 libadwaita xrandr
        $sudo dnf install -y nvidia-settings || echo "note: nvidia-settings needs RPM Fusion (only needed on X11)" ;;
    *" arch "*|*" manjaro "*|*" endeavouros "*|*" cachyos "*)
        $sudo pacman -S --needed --noconfirm python python-gobject gtk4 libadwaita xorg-xrandr nvidia-settings ;;
    *" opensuse "*|*" suse "*|*" sles "*)
        $sudo zypper install -y python3 python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 xrandr
        $sudo zypper install -y nvidia-settings || echo "note: nvidia-settings not installed (only needed on X11)" ;;
    *)
        echo "Unknown distro. Install manually: Python 3, PyGObject, GTK 4, libadwaita (+ xrandr, nvidia-settings for X11)." ;;
    esac
}

[ "$SKIP_DEPS" -eq 0 ] && install_deps

LIB="$PREFIX/share/nvpanel"
mkdir -p "$LIB" "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps"
rm -rf "$LIB/nvpanel"
cp -r "$HERE/nvpanel" "$LIB/nvpanel"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +

cat > "$PREFIX/bin/nvpanel" <<LAUNCH
#!/usr/bin/env sh
PYTHONPATH="$LIB\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m nvpanel "\$@"
LAUNCH
chmod +x "$PREFIX/bin/nvpanel"
sed "s|^Exec=nvpanel|Exec=$PREFIX/bin/nvpanel|" "$HERE/data/io.github.nvpanel.desktop" > "$PREFIX/share/applications/io.github.nvpanel.desktop"
cp "$HERE/nvpanel/icons/hicolor/scalable/apps/nvpanel.svg" "$PREFIX/share/icons/hicolor/scalable/apps/"
command -v gtk4-update-icon-cache >/dev/null && gtk4-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null && update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true

echo
echo "Installed nvpanel to $PREFIX (make sure $PREFIX/bin is in your PATH)."
if [ "${XDG_CURRENT_DESKTOP:-}" != "${XDG_CURRENT_DESKTOP/GNOME/}" ] && [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    echo "GNOME on Wayland detected: for Digital Vibrance run  nvpanel --install-extension  and log out/in once."
fi
