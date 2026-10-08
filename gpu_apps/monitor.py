"""Đọc mức sử dụng card NVIDIA: tổng thể và theo từng app."""
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .core import ID_ENV

_SCOPE = re.compile(r"app-(?:gnome|flatpak)-(.+)-\d+\.scope")
_DBUS_SLICE = re.compile(r"app-dbus\\x2d:[\d.]+\\x2d(.+?)\.slice")
_ESCAPE = re.compile(r"\\x([0-9a-f]{2})")


@dataclass
class GpuStats:
    name: str
    util: float | None  # %
    mem_used: float | None  # MiB
    mem_total: float | None  # MiB
    temp: float | None  # °C
    power: float | None  # W


@dataclass
class Proc:
    pid: int
    util: float | None
    mem: float
    command: str


@dataclass
class Usage:
    label: str
    pids: list = field(default_factory=list)
    mem: float = 0.0
    util: float = 0.0


@dataclass
class Snapshot:
    status: str | None  # runtime_status của PCI: "active", "suspended", ...
    stats: GpuStats | None
    usage: list


def gpu_device():
    for dev in sorted(Path("/sys/bus/pci/devices").glob("*")):
        try:
            if (dev / "vendor").read_text().strip() == "0x10de" and (dev / "class").read_text().startswith("0x03"):
                return dev
        except OSError:
            continue
    return None


def runtime_status():
    dev = gpu_device()
    if dev is None:
        return None
    try:
        return (dev / "power/runtime_status").read_text().strip()
    except OSError:
        return None


def _nvidia_smi(*args):
    try:
        result = subprocess.run(["nvidia-smi", *args], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _number(text):
    try:
        return float(text)
    except ValueError:
        return None


def parse_stats(out):
    lines = out.strip().splitlines()
    if not lines:
        return None
    fields = [f.strip() for f in lines[0].split(",")]
    if len(fields) < 6:
        return None
    return GpuStats(fields[0], *(_number(f) for f in fields[1:6]))


def gpu_stats():
    out = _nvidia_smi(
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    )
    return parse_stats(out) if out else None


def parse_pmon(out):
    columns, procs = None, []
    for line in out.splitlines():
        if line.startswith("# gpu"):
            columns = line[1:].split()
            continue
        if columns is None or line.startswith("#") or not line.strip():
            continue
        parts = line.split(None, len(columns) - 1)
        if len(parts) < len(columns):
            continue
        row = dict(zip(columns, parts))
        if not row["pid"].isdigit():
            continue
        procs.append(Proc(int(row["pid"]), _number(row.get("sm", "-")),
                          _number(row.get("fb", "-")) or 0.0, row.get("command", "").strip()))
    return procs


def processes():
    out = _nvidia_smi("pmon", "-c", "1", "-s", "um")
    return parse_pmon(out) if out else []


def app_id_from_cgroup(cgroup):
    """Lấy desktop id từ cgroup mà GNOME/systemd đặt cho app."""
    match = _SCOPE.search(cgroup) or _DBUS_SLICE.search(cgroup)
    if not match:
        return None
    name = _ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), match.group(1))
    return name + ".desktop"


def _marker(pid):
    try:
        for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
            if item.startswith(ID_ENV.encode() + b"="):
                return item.split(b"=", 1)[1].decode(errors="replace")
    except OSError:
        pass
    return None


def _parent(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def app_id_of(pid):
    # Biến đánh dấu thường nằm ở tiến trình cha. Chromium/Electron tự xoá environ của
    # mọi tiến trình, nên với chúng phải dựa vào cgroup mà GNOME đặt khi mở từ menu.
    ancestor = pid
    while ancestor > 1:
        app_id = _marker(ancestor)
        if app_id:
            return app_id
        ancestor = _parent(ancestor)
    try:
        return app_id_from_cgroup(Path(f"/proc/{pid}/cgroup").read_text())
    except OSError:
        return None


def usage_by_app(procs, names, identify=app_id_of):
    """Gộp tiến trình theo app. `names` ánh xạ desktop id sang tên hiển thị."""
    groups = {}
    for proc in procs:
        app_id = identify(proc.pid)
        label = names.get(app_id) or proc.command or str(proc.pid)
        usage = groups.setdefault(label, Usage(label))
        usage.pids.append(proc.pid)
        usage.mem += proc.mem
        usage.util += proc.util or 0.0
    return sorted(groups.values(), key=lambda u: (-u.mem, u.label))


def snapshot(names):
    status = runtime_status()
    if status == "suspended":
        # Gọi nvidia-smi sẽ đánh thức card, nên bỏ qua khi nó đang ngủ.
        return Snapshot(status, None, [])
    return Snapshot(status, gpu_stats(), usage_by_app(processes(), names))
