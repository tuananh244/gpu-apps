"""Giao diện dòng lệnh của gpu-apps."""
import argparse
import curses
import locale
import sys

from . import core, monitor


def find(apps, query):
    q = query.lower().removesuffix(".desktop")
    exact = [a for a in apps if a.short_id.lower() == q or a.name.lower() == q]
    matches = exact or [a for a in apps if q in a.short_id.lower() or q in a.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        sys.exit(f"Không tìm thấy app nào khớp với '{query}'. Xem `gpu-apps list`.")
    names = ", ".join(a.short_id for a in matches)
    sys.exit(f"'{query}' khớp với nhiều app: {names}")


def cmd_list(_args):
    for a in core.visible_apps():
        print(f"[{'x' if a.enabled else ' '}] {a.name}  ({a.short_id})")


def apply_changes(to_enable, to_disable, x11=None):
    for a in to_disable:
        core.disable(a)
        print(f"Đã tắt: {a.name}")
    failed = False
    for a in to_enable:
        error = core.enable(a, x11)
        if error:
            failed = True
            print(f"Bỏ qua {a.name}: {error}", file=sys.stderr)
        else:
            print(f"Đã bật: {a.name}")
    if to_enable or to_disable:
        core.update_database()
        print("Đóng hẳn app rồi mở lại để thay đổi có hiệu lực.")
    return 1 if failed else 0


def cmd_enable(args):
    apps = core.visible_apps()
    return apply_changes([find(apps, q) for q in args.apps], [], args.x11)


def cmd_disable(args):
    apps = core.visible_apps()
    return apply_changes([], [find(apps, q) for q in args.apps])


def cmd_refresh(_args):
    """Sinh lại file ghi đè, dùng sau khi app được cập nhật."""
    failed = False
    for a in core.visible_apps():
        if not a.enabled:
            continue
        error = core.enable(a, a.entry.get(core.X11_KEY) == "true")
        if error:
            failed = True
            print(f"Bỏ qua {a.name}: {error}", file=sys.stderr)
        else:
            print(f"Đã làm mới: {a.name}")
    core.update_database()
    return 1 if failed else 0


def _fmt(value, unit):
    return "?" if value is None else f"{value:.0f}{unit}"


def cmd_status(_args):
    """In mức sử dụng card NVIDIA và các app đang dùng nó."""
    names = {a.id: a.name for a in core.discover().values()}
    snap = monitor.snapshot(names)
    if snap.status == "suspended":
        print("Card NVIDIA đang ngủ: không có app nào dùng nó.")
        return 0
    if snap.stats is None:
        print("Không đọc được nvidia-smi. Driver NVIDIA đã chạy chưa?", file=sys.stderr)
        return 1
    s = snap.stats
    print(f"{s.name}: tải {_fmt(s.util, '%')}, VRAM {_fmt(s.mem_used, '')}/{_fmt(s.mem_total, ' MiB')}, "
          f"{_fmt(s.temp, '°C')}, {_fmt(s.power, ' W')}")
    if not snap.usage:
        print("Không có app nào đang dùng card.")
        return 0
    print(f"\n{'Ứng dụng':<28} {'Tải':>5} {'VRAM':>9}  PID")
    for u in snap.usage:
        pids = ", ".join(map(str, u.pids))
        print(f"{u.label[:28]:<28} {u.util:>4.0f}% {u.mem:>5.0f} MiB  {pids}")
    return 0


def cmd_gui(_args):
    from . import gui
    return gui.main()


def pick(stdscr, apps):
    curses.curs_set(0)
    curses.use_default_colors()
    checked = [a.enabled for a in apps]
    pos = top = 0
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        rows = max(1, height - 2)
        top = min(top, pos)
        if pos >= top + rows:
            top = pos - rows + 1
        stdscr.addnstr(0, 0, "Chọn app chạy bằng GPU NVIDIA  |  ↑↓ di chuyển · Space chọn · Enter lưu · q huỷ",
                       width - 1, curses.A_BOLD)
        for i in range(top, min(len(apps), top + rows)):
            line = f"[{'x' if checked[i] else ' '}] {apps[i].name}  ({apps[i].short_id})"
            stdscr.addnstr(2 + i - top, 0, line, width - 1, curses.A_REVERSE if i == pos else 0)
        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            pos = max(0, pos - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            pos = min(len(apps) - 1, pos + 1)
        elif key == curses.KEY_PPAGE:
            pos = max(0, pos - rows)
        elif key == curses.KEY_NPAGE:
            pos = min(len(apps) - 1, pos + rows)
        elif key == ord(" "):
            checked[pos] = not checked[pos]
        elif key in (curses.KEY_ENTER, 10, 13):
            return checked
        elif key in (ord("q"), 27):
            return None


def cmd_interactive(_args):
    apps = core.visible_apps()
    if not apps:
        sys.exit("Không tìm thấy app nào.")
    checked = curses.wrapper(pick, apps)
    if checked is None:
        print("Đã huỷ, không thay đổi gì.")
        return 0
    to_enable = [a for a, c in zip(apps, checked) if c and not a.enabled]
    to_disable = [a for a, c in zip(apps, checked) if not c and a.enabled]
    if not to_enable and not to_disable:
        print("Không có thay đổi.")
        return 0
    return apply_changes(to_enable, to_disable)


def main():
    locale.setlocale(locale.LC_ALL, "")
    parser = argparse.ArgumentParser(
        prog="gpu-apps",
        description="Chọn app nào luôn khởi động trên card NVIDIA. Không có lệnh con thì mở danh sách để tick chọn.",
    )
    parser.set_defaults(func=cmd_interactive)
    sub = parser.add_subparsers(metavar="lệnh")
    sub.add_parser("gui", help="mở giao diện đồ hoạ").set_defaults(func=cmd_gui)
    sub.add_parser("list", help="liệt kê app và trạng thái").set_defaults(func=cmd_list)
    p = sub.add_parser("enable", help="bật GPU NVIDIA cho app")
    p.add_argument("apps", nargs="+", metavar="app")
    p.add_argument("--x11", action=argparse.BooleanOptionalAction, default=None,
                   help=f"ép thêm/bỏ cờ {core.X11_FLAG} (mặc định: tự nhận diện app Chromium/Electron)")
    p.set_defaults(func=cmd_enable)
    p = sub.add_parser("disable", help="trả app về GPU mặc định")
    p.add_argument("apps", nargs="+", metavar="app")
    p.set_defaults(func=cmd_disable)
    sub.add_parser("refresh", help="sinh lại file ghi đè sau khi app được cập nhật").set_defaults(func=cmd_refresh)
    sub.add_parser("status", help="xem mức dùng card NVIDIA theo từng app").set_defaults(func=cmd_status)
    args = parser.parse_args()
    return args.func(args)
