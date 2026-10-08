import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

_loader = importlib.machinery.SourceFileLoader("gpu_apps", str(Path(__file__).parent.parent / "gpu-apps"))
_spec = importlib.util.spec_from_loader("gpu_apps", _loader)
gpu_apps = importlib.util.module_from_spec(_spec)
_loader.exec_module(gpu_apps)

ENV = "env " + " ".join(gpu_apps.OFFLOAD_ENV)


class WrapExecTest(unittest.TestCase):
    def test_plain_command(self):
        self.assertEqual(gpu_apps.wrap_exec("blender %f", False), f"{ENV} blender %f")

    def test_x11_flag_goes_right_after_program(self):
        self.assertEqual(
            gpu_apps.wrap_exec("/usr/bin/chromium %U", True),
            f"{ENV} /usr/bin/chromium --ozone-platform=x11 %U",
        )

    def test_quoted_program_with_spaces(self):
        self.assertEqual(
            gpu_apps.wrap_exec('"/opt/My App/app" --foo %U', True),
            f'{ENV} "/opt/My App/app" --ozone-platform=x11 --foo %U',
        )

    def test_existing_env_prefix_is_skipped(self):
        self.assertEqual(
            gpu_apps.wrap_exec("env FOO=1 code-oss %F", True),
            f"{ENV} env FOO=1 code-oss --ozone-platform=x11 %F",
        )

    def test_existing_ozone_flag_is_kept(self):
        cmd = "chromium --ozone-platform=wayland %U"
        self.assertEqual(gpu_apps.wrap_exec(cmd, True), f"{ENV} {cmd}")


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
        out = gpu_apps.rewrite(self.SOURCE, False)
        self.assertIn(f"Exec={ENV} demo %U\n", out)
        self.assertIn(f"Exec={ENV} demo --new\n", out)
        self.assertIn("DBusActivatable=false\n", out)
        self.assertIn("[Desktop Entry]\nX-GpuApps-Managed=true\nX-GpuApps-X11=false\n", out)

    def test_rewrite_is_idempotent_on_markers(self):
        once = gpu_apps.rewrite(self.SOURCE, True)
        self.assertEqual(once.count("X-GpuApps-Managed"), 1)
        self.assertEqual(gpu_apps.rewrite(once, True).count("X-GpuApps-Managed"), 1)


if __name__ == "__main__":
    unittest.main()
