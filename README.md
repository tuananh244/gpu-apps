# gpu-apps

Chọn app nào luôn khởi động trên card NVIDIA rời trên laptop hybrid (Intel + NVIDIA, PRIME render offload). Tick app một lần, từ đó mở app từ menu ứng dụng là nó tự chạy bằng GPU NVIDIA.

## Yêu cầu

- Driver NVIDIA đã hoạt động (`nvidia-smi` chạy được)
- Python 3.10+ (chỉ dùng thư viện chuẩn)

- Giao diện đồ hoạ cần GTK4, libadwaita và PyGObject (có sẵn trên GNOME)

## Cài đặt

```sh
./install.sh
```

Lệnh này tạo liên kết `~/.local/bin/gpu-apps` và thêm mục **GPU Apps** vào menu ứng dụng.

## Giao diện đồ hoạ

Mở **GPU Apps** từ menu ứng dụng, hoặc chạy `gpu-apps gui`.

- **Ứng dụng**: bật công tắc cạnh app để nó luôn khởi động trên card NVIDIA.
- **Giám sát GPU**: trạng thái card (đang hoạt động hay đang ngủ), mức tải, VRAM, nhiệt độ, công suất, và danh sách app đang dùng card kèm % tải và VRAM của từng app. Số liệu cập nhật mỗi 1,5 giây.

## Dòng lệnh

```sh
gpu-apps                    # mở danh sách, Space để tick, Enter để lưu
gpu-apps gui                # mở giao diện đồ hoạ
gpu-apps list               # xem app nào đang bật
gpu-apps enable chromium    # bật cho một app (theo tên hoặc id)
gpu-apps disable chromium   # trả về GPU mặc định
gpu-apps refresh            # sinh lại sau khi app được cập nhật
gpu-apps status             # mức dùng card NVIDIA, theo từng app
```

Sau khi bật hoặc tắt, phải đóng hẳn app rồi mở lại.

## Kiểm tra app có chạy trên GPU không

Mở app, rồi xem trang **Giám sát GPU** hoặc chạy `gpu-apps status`:

```
NVIDIA GeForce RTX 3050 Ti Laptop GPU: tải 33%, VRAM 258/4096 MiB, 50°C, 9 W

Ứng dụng                       Tải      VRAM  PID
Chromium                       44%   116 MiB  25548
Code - OSS                      0%    54 MiB  25679
```

App có tên trong danh sách nghĩa là nó đang chạy trên card NVIDIA. Cột "Tải" là 0% khi app không vẽ gì mới.

Số liệu lấy từ `nvidia-smi`. Tên app được xác định qua cgroup mà GNOME đặt khi mở app từ menu; app mở từ terminal có thể hiện dưới tên terminal đó.

## Cách hoạt động

Khi bật một app, công cụ chép file `.desktop` của app vào `~/.local/share/applications/` (vị trí được ưu tiên hơn file hệ thống) và sửa dòng `Exec`:

```
Exec=env __NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia <lệnh gốc>
```

Khi tắt, file ghi đè bị xoá. Nếu trước đó bạn đã có file `.desktop` riêng cho app đó, nó được cất vào `~/.local/state/gpu-apps/backups/` và khôi phục lại khi tắt. Không cần quyền root và không sửa file hệ thống nào.

## Lưu ý

- **Chromium/Electron** (Chromium, VS Code, ...): trên Wayland các app này bỏ qua offload, nên công cụ tự thêm cờ `--ozone-platform=x11` để chạy qua XWayland. Dùng `--x11` / `--no-x11` với lệnh `enable` nếu nhận diện sai.
- **Flatpak**: cần runtime `org.freedesktop.Platform.GL.nvidia-*` khớp phiên bản driver; nếu thiếu, công cụ từ chối bật và báo lý do.
- **Chỉ áp dụng khi mở từ menu ứng dụng.** Chạy lệnh trong terminal thì vẫn dùng `prime-run <lệnh>`.
- **Giám sát giữ card thức**: khi trang Giám sát GPU đang mở, việc đọc số liệu ngăn card chuyển sang chế độ ngủ. Đóng cửa sổ khi không cần để tiết kiệm pin.
- **Cập nhật app**: file ghi đè là bản sao, nên sau khi gói được cập nhật hãy chạy `gpu-apps refresh`.

## Kiểm thử

```sh
python3 -m unittest discover -s tests
```
