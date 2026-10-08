#!/bin/sh
# Cài lệnh `gpu-apps` và mục "GPU Apps" trong menu ứng dụng cho người dùng hiện tại.
set -eu

repo=$(cd "$(dirname "$0")" && pwd)
bin_dir="$HOME/.local/bin"
apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$bin_dir" "$apps_dir"
ln -sf "$repo/gpu-apps" "$bin_dir/gpu-apps"

cat > "$apps_dir/io.github.gpu_apps.GpuApps.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GPU Apps
Comment=Chọn ứng dụng chạy trên card NVIDIA và xem mức sử dụng GPU
Exec="$repo/gpu-apps" gui
Icon=video-display
Terminal=false
Categories=Settings;System;
EOF

echo "Đã cài: $bin_dir/gpu-apps và mục 'GPU Apps' trong menu ứng dụng."
