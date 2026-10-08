"""Bật/tắt PRIME render offload cho từng app bằng file .desktop ghi đè.

Mỗi app được bật sẽ có một file .desktop ghi đè trong ~/.local/share/applications,
với dòng Exec được bọc thêm các biến môi trường offload. Tắt đi thì file ghi đè bị xoá.
"""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

OFFLOAD_ENV = (
    "__NV_PRIME_RENDER_OFFLOAD=1",
    "__VK_LAYER_NV_optimus=NVIDIA_only",
    "__GLX_VENDOR_LIBRARY_NAME=nvidia",
)
# Chromium/Electron trên Wayland bỏ qua offload; phải chạy qua XWayland.
X11_FLAG = "--ozone-platform=x11"
MARKER = "X-GpuApps-Managed"
X11_KEY = "X-GpuApps-X11"
# Gắn vào môi trường của app để phần giám sát biết tiến trình thuộc app nào.
ID_ENV = "GPU_APPS_ID"
SELF_ID = "io.github.gpu_apps.GpuApps.desktop"

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
USER_APPS = DATA_HOME / "applications"
BACKUPS = STATE_HOME / "gpu-apps" / "backups"

_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\S+')
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_CHROMIUM_NAME = re.compile(r"chrom|electron|brave|vivaldi|msedge|microsoft-edge|opera", re.I)
_CHROMIUM_SCRIPT = re.compile(rb"electron|chromium|chrome", re.I)


@dataclass
class App:
    id: str
    name: str
    enabled: bool
    source: Path | None  # file gốc dùng để sinh file ghi đè
    entry: dict

    @property
    def target(self):
        return USER_APPS / self.id

    @property
    def backup(self):
        return BACKUPS / self.id

    @property
    def short_id(self):
        return self.id.removesuffix(".desktop")

    @property
    def visible(self):
        e = self.entry
        return (
            e.get("Type") == "Application"
            and "Exec" in e
            and e.get("NoDisplay", "").lower() != "true"
            and e.get("Hidden", "").lower() != "true"
        )


def read_entry(path):
    entry, group = {}, None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entry
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            group = line
        elif group == "[Desktop Entry]" and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            entry.setdefault(key.strip(), value.strip())
    return entry


def app_dirs():
    dirs = [USER_APPS]
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d:
            dirs.append(Path(d) / "applications")
    return dirs


def discover():
    """Trả về mọi app theo thứ tự ưu tiên XDG, kể cả app đang ẩn."""
    apps = {}
    for d in app_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.desktop")):
            app_id = str(f.relative_to(d)).replace("/", "-")
            known = apps.get(app_id)
            if known:
                if known.enabled and known.source is None:
                    known.source = f
                continue
            entry = read_entry(f)
            managed = d == USER_APPS and entry.get(MARKER) == "true"
            app = App(app_id, entry.get("Name", app_id), managed, None if managed else f, entry)
            if managed and app.backup.exists():
                app.source = app.backup
            apps[app_id] = app
    return apps


def split_exec(cmd):
    """Trả về (vị trí kết thúc của tên chương trình, tên chương trình), bỏ qua tiền tố `env A=b`."""
    tokens = [(m.end(), m.group()) for m in _TOKEN.finditer(cmd)]
    if not tokens:
        return 0, ""
    i = 0
    if os.path.basename(tokens[0][1].strip('"')) == "env":
        i = 1
        while i < len(tokens) and _ASSIGNMENT.match(tokens[i][1]):
            i += 1
        if i >= len(tokens):
            i = 0
    return tokens[i][0], tokens[i][1].strip('"')


def wrap_exec(cmd, x11, app_id):
    end, _ = split_exec(cmd)
    flag = f" {X11_FLAG}" if x11 and "--ozone-platform" not in cmd else ""
    return f"env {ID_ENV}={app_id} {' '.join(OFFLOAD_ENV)} {cmd[:end]}{flag}{cmd[end:]}"


def is_chromium_based(program):
    if _CHROMIUM_NAME.search(os.path.basename(program)):
        return True
    path = shutil.which(program)
    if not path:
        return False
    real = Path(path).resolve()
    if (real.parent / "chrome_100_percent.pak").exists():
        return True
    try:
        with real.open("rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return head.startswith(b"#!") and _CHROMIUM_SCRIPT.search(head) is not None


def rewrite(text, x11, app_id):
    out = []
    for line in text.splitlines():
        if line.startswith("X-GpuApps-"):
            continue
        if line.startswith("Exec="):
            line = "Exec=" + wrap_exec(line[5:], x11, app_id)
        elif line.startswith("DBusActivatable="):
            # Nếu để D-Bus kích hoạt thì dòng Exec (và biến môi trường) bị bỏ qua.
            line = "DBusActivatable=false"
        out.append(line)
        if line.strip() == "[Desktop Entry]":
            out.append(f"{MARKER}=true")
            out.append(f"{X11_KEY}={'true' if x11 else 'false'}")
    return "\n".join(out) + "\n"


def flatpak_missing_nvidia(program):
    if os.path.basename(program) != "flatpak":
        return False
    try:
        runtimes = subprocess.run(
            ["flatpak", "list", "--runtime", "--columns=application"],
            capture_output=True, text=True, check=False,
        ).stdout
    except OSError:
        return True
    return "org.freedesktop.Platform.GL.nvidia" not in runtimes


def enable(app, x11=None):
    """Bật offload cho app. Trả về chuỗi lỗi, hoặc None nếu thành công."""
    if app.source is None:
        return "không tìm thấy file .desktop gốc (app đã bị gỡ?)"
    text = app.source.read_text(encoding="utf-8", errors="replace")
    _, program = split_exec(read_entry(app.source).get("Exec", ""))
    if flatpak_missing_nvidia(program):
        return ("app Flatpak, nhưng chưa có runtime org.freedesktop.Platform.GL.nvidia-* "
                "khớp với driver (thử `flatpak update`)")
    if x11 is None:
        x11 = is_chromium_based(program)
    if app.source.parent != BACKUPS and USER_APPS in app.source.parents:
        # File do người dùng tự tạo: cất đi để khôi phục khi tắt.
        BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.move(app.source, app.backup)
        app.source = app.backup
    USER_APPS.mkdir(parents=True, exist_ok=True)
    tmp = app.target.with_suffix(".tmp")
    tmp.write_text(rewrite(text, x11, app.id), encoding="utf-8")
    tmp.replace(app.target)
    app.enabled = True
    return None


def disable(app):
    if not app.enabled:
        return
    app.target.unlink(missing_ok=True)
    if app.backup.exists():
        shutil.move(app.backup, app.target)
    app.enabled = False


def update_database():
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", "-q", str(USER_APPS)], check=False)


def visible_apps():
    apps = [a for a in discover().values() if (a.visible or a.enabled) and a.id != SELF_ID]
    return sorted(apps, key=lambda a: a.name.lower())
