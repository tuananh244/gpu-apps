"""Giao diện GTK4/libadwaita: chọn app và giám sát card NVIDIA."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import core, monitor  # noqa: E402

APP_ID = core.SELF_ID.removesuffix(".desktop")
REFRESH_MS = 1500


def icon_for(app):
    name = app.entry.get("Icon") or "application-x-executable"
    image = Gtk.Image.new_from_file(name) if name.startswith("/") else Gtk.Image.new_from_icon_name(name)
    image.set_pixel_size(32)
    return image


def fmt(value, unit):
    return "—" if value is None else f"{value:.0f}{unit}"


class Window(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="GPU Apps", default_width=600, default_height=720)
        self.names = {a.id: a.name for a in core.discover().values()}
        self.fetching = False
        self.proc_rows = []

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(self.build_apps_page(), "apps", "Ứng dụng", "view-app-grid-symbolic")
        self.stack.add_titled_with_icon(self.build_monitor_page(), "monitor", "Giám sát GPU",
                                        "utilities-system-monitor-symbolic")
        self.toasts = Adw.ToastOverlay(child=self.stack)
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(Adw.HeaderBar(title_widget=switcher))
        self.set_content(view)

        self.stack.connect("notify::visible-child-name", lambda *_: self.tick())
        GLib.timeout_add(REFRESH_MS, self.tick)

    # Trang chọn ứng dụng

    def build_apps_page(self):
        hint = Gtk.Label(
            label="Bật công tắc để ứng dụng luôn khởi động trên card NVIDIA khi mở từ menu.",
            wrap=True, xalign=0, css_classes=["dim-label"],
        )
        self.search = Gtk.SearchEntry(placeholder_text="Tìm ứng dụng")
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.listbox.set_filter_func(self.filter_row)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        for app in sorted(core.visible_apps(), key=lambda a: (not a.enabled, a.name.lower())):
            self.listbox.append(self.app_row(app))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=18, margin_bottom=18, margin_start=12, margin_end=12)
        box.append(hint)
        box.append(self.search)
        box.append(self.listbox)
        return Gtk.ScrolledWindow(child=Adw.Clamp(child=box, maximum_size=640),
                                  hscrollbar_policy=Gtk.PolicyType.NEVER)

    def app_row(self, app):
        row = Adw.SwitchRow(title=GLib.markup_escape_text(app.name),
                            subtitle=GLib.markup_escape_text(app.short_id), active=app.enabled)
        row.add_prefix(icon_for(app))
        row.search_text = f"{app.name} {app.short_id}".lower()
        row.connect("notify::active", self.on_toggled, app)
        return row

    def filter_row(self, row):
        return self.search.get_text().lower().strip() in row.search_text

    def on_toggled(self, row, _pspec, app):
        if row.get_active() == app.enabled:
            return
        if row.get_active():
            error = core.enable(app)
            if error:
                row.set_active(False)
                self.toast(f"{app.name}: {error}")
                return
        else:
            core.disable(app)
        core.update_database()
        action = "bật" if app.enabled else "tắt"
        self.toast(f"Đã {action} {app.name}. Đóng hẳn app rồi mở lại để có hiệu lực.")

    def toast(self, message):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(message), timeout=5))

    # Trang giám sát

    def stat_row(self, group, title, with_bar=False):
        row = Adw.ActionRow(title=title)
        bar = None
        if with_bar:
            bar = Gtk.LevelBar(min_value=0, max_value=1, width_request=160, valign=Gtk.Align.CENTER)
            row.add_suffix(bar)
        label = Gtk.Label(label="—", width_chars=16, xalign=1, css_classes=["numeric"])
        row.add_suffix(label)
        group.add(row)
        return label, bar

    def build_monitor_page(self):
        card = Adw.PreferencesGroup(title="Card đồ hoạ")
        self.card_group = card
        self.state_label, _ = self.stat_row(card, "Trạng thái")
        self.util_label, self.util_bar = self.stat_row(card, "Mức tải GPU", with_bar=True)
        self.mem_label, self.mem_bar = self.stat_row(card, "VRAM", with_bar=True)
        self.temp_label, _ = self.stat_row(card, "Nhiệt độ")
        self.power_label, _ = self.stat_row(card, "Công suất")

        self.proc_group = Adw.PreferencesGroup(
            title="Ứng dụng đang dùng GPU",
            description="Ứng dụng xuất hiện ở đây nghĩa là nó đang chạy trên card NVIDIA.",
        )
        page = Adw.PreferencesPage()
        page.add(card)
        page.add(self.proc_group)
        return page

    def tick(self):
        if self.stack.get_visible_child_name() == "monitor" and not self.fetching:
            self.fetching = True
            threading.Thread(target=self.fetch, daemon=True).start()
        return True

    def fetch(self):
        GLib.idle_add(self.show_snapshot, monitor.snapshot(self.names))

    def show_snapshot(self, snap):
        self.fetching = False
        stats = snap.stats
        if snap.status == "suspended":
            self.state_label.set_label("Đang ngủ")
        elif stats is None:
            self.state_label.set_label("Không đọc được")
        else:
            self.state_label.set_label("Đang hoạt động")
            self.card_group.set_description(stats.name)

        self.util_label.set_label(fmt(stats and stats.util, "%"))
        self.util_bar.set_value((stats.util or 0) / 100 if stats else 0)
        if stats and stats.mem_used is not None and stats.mem_total:
            self.mem_label.set_label(f"{stats.mem_used:.0f} / {stats.mem_total:.0f} MiB")
            self.mem_bar.set_value(stats.mem_used / stats.mem_total)
        else:
            self.mem_label.set_label("—")
            self.mem_bar.set_value(0)
        self.temp_label.set_label(fmt(stats and stats.temp, " °C"))
        self.power_label.set_label(fmt(stats and stats.power, " W"))

        for row in self.proc_rows:
            self.proc_group.remove(row)
        self.proc_rows = [self.usage_row(u) for u in snap.usage] or [
            Adw.ActionRow(title="Không có ứng dụng nào đang dùng card")
        ]
        for row in self.proc_rows:
            self.proc_group.add(row)
        return False

    def usage_row(self, usage):
        pids = ", ".join(map(str, usage.pids))
        row = Adw.ActionRow(title=GLib.markup_escape_text(usage.label),
                            subtitle=f"{len(usage.pids)} tiến trình · PID {pids}")
        row.add_suffix(Gtk.Label(label=f"{usage.util:.0f}%  ·  {usage.mem:.0f} MiB", css_classes=["numeric"]))
        return row


def main():
    application = Adw.Application(application_id=APP_ID)
    application.connect("activate", lambda a: (a.get_active_window() or Window(a)).present())
    return application.run([])
