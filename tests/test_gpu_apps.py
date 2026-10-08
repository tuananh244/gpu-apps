import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gpu_apps import core, monitor  # noqa: E402

ENV = f"env {core.ID_ENV}=demo.desktop " + " ".join(core.OFFLOAD_ENV)


def wrap(cmd, x11):
    return core.wrap_exec(cmd, x11, "demo.desktop")


class WrapExecTest(unittest.TestCase):
    def test_plain_command(self):
        self.assertEqual(wrap("blender %f", False), f"{ENV} blender %f")

    def test_x11_flag_goes_right_after_program(self):
        self.assertEqual(wrap("/usr/bin/chromium %U", True), f"{ENV} /usr/bin/chromium --ozone-platform=x11 %U")

    def test_quoted_program_with_spaces(self):
        self.assertEqual(
            wrap('"/opt/My App/app" --foo %U', True),
            f'{ENV} "/opt/My App/app" --ozone-platform=x11 --foo %U',
        )

    def test_existing_env_prefix_is_skipped(self):
        self.assertEqual(
            wrap("env FOO=1 code-oss %F", True),
            f"{ENV} env FOO=1 code-oss --ozone-platform=x11 %F",
        )

    def test_existing_ozone_flag_is_kept(self):
        cmd = "chromium --ozone-platform=wayland %U"
        self.assertEqual(wrap(cmd, True), f"{ENV} {cmd}")


class RewriteTest(unittest.TestCase):
    SOURCE = (
        "[Desktop Entry]\n"
        "Name=Demo\n"
        "Exec=demo %U\n"
        "DBusActivatable=true\n"
        "\n"
        "[Desktop Action new]\n"
        "Exec=demo --new\n"
    )

    def test_rewrites_every_exec_and_marks_file(self):
        out = core.rewrite(self.SOURCE, False, "demo.desktop")
        self.assertIn(f"Exec={ENV} demo %U\n", out)
        self.assertIn(f"Exec={ENV} demo --new\n", out)
        self.assertIn("DBusActivatable=false\n", out)
        self.assertIn("[Desktop Entry]\nX-GpuApps-Managed=true\nX-GpuApps-X11=false\n", out)

    def test_rewrite_is_idempotent_on_markers(self):
        once = core.rewrite(self.SOURCE, True, "demo.desktop")
        self.assertEqual(once.count("X-GpuApps-Managed"), 1)
        self.assertEqual(core.rewrite(once, True, "demo.desktop").count("X-GpuApps-Managed"), 1)


PMON = """\
# gpu         pid   type     sm    mem    enc    dec    jpg    ofa     fb   ccpm    command
# Idx           #    C/G      %      %      %      %      %      %     MB     MB    name
    0       2837     G      -      -      -      -      -      -      1      0    gnome-shell
    0      13053     G     12      3      -      -      -      -     34      0    chromium
    0      13060   C+G      5      1      -      -      -      -     20      0    chromium
"""


class MonitorTest(unittest.TestCase):
    def test_parse_pmon(self):
        procs = monitor.parse_pmon(PMON)
        self.assertEqual([p.pid for p in procs], [2837, 13053, 13060])
        self.assertIsNone(procs[0].util)
        self.assertEqual((procs[1].util, procs[1].mem, procs[1].command), (12.0, 34.0, "chromium"))

    def test_parse_pmon_without_processes(self):
        out = PMON.splitlines()[0] + "\n    0          -     -      -      -      -      -      -      -      -      -    -\n"
        self.assertEqual(monitor.parse_pmon(out), [])

    def test_parse_stats(self):
        stats = monitor.parse_stats("NVIDIA GeForce RTX 3050 Ti Laptop GPU, 3, 69, 4096, 46, [N/A]\n")
        self.assertEqual((stats.util, stats.mem_used, stats.mem_total, stats.temp), (3.0, 69.0, 4096.0, 46.0))
        self.assertIsNone(stats.power)

    def test_usage_is_grouped_by_app(self):
        ids = {13053: "chromium.desktop", 13060: "chromium.desktop"}
        usage = monitor.usage_by_app(monitor.parse_pmon(PMON), {"chromium.desktop": "Chromium"}, ids.get)
        self.assertEqual([(u.label, u.mem, u.util, u.pids) for u in usage], [
            ("Chromium", 54.0, 17.0, [13053, 13060]),
            ("gnome-shell", 1.0, 0.0, [2837]),
        ])

    def test_app_id_from_cgroup(self):
        scope = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-code\\x2doss-4242.scope\n"
        self.assertEqual(monitor.app_id_from_cgroup(scope), "code-oss.desktop")
        dbus = ("0::/user.slice/user@1000.service/app.slice/"
                "app-dbus\\x2d:1.2\\x2dorg.gnome.Console.slice/dbus-:1.2-org.gnome.Console@0.service\n")
        self.assertEqual(monitor.app_id_from_cgroup(dbus), "org.gnome.Console.desktop")
        self.assertIsNone(monitor.app_id_from_cgroup("0::/user.slice/session-2.scope\n"))


if __name__ == "__main__":
    unittest.main()
