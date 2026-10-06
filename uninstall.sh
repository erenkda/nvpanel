#!/usr/bin/env bash
set -eu
PREFIX="${PREFIX:-$HOME/.local}"
rm -rf "$PREFIX/share/nvpanel" "$PREFIX/bin/nvpanel" \
       "$PREFIX/share/applications/nvpanel.desktop" \
       "$PREFIX/share/icons/hicolor/scalable/apps/nvpanel.svg" \
       "$HOME/.config/autostart/nvpanel.desktop"
gnome-extensions disable nvpanel-vibrance@nvpanel.github.io 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/nvpanel-vibrance@nvpanel.github.io"
echo "nvpanel removed (settings in ~/.config/nvpanel were kept)."
