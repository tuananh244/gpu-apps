# gpu-apps

Chọn app nào luôn khởi động trên card NVIDIA rời trên laptop hybrid (Intel + NVIDIA, PRIME render offload). Tick app một lần, từ đó mở app từ menu ứng dụng là nó tự chạy bằng GPU NVIDIA.

## Yêu cầu

- Driver NVIDIA đã hoạt động (`nvidia-smi` chạy được)
- Python 3.10+ (chỉ dùng thư viện chuẩn)

## Cài đặt

```sh
ln -s "$PWD/gpu-apps" ~/.local/bin/gpu-apps
```

## Cách dùng

```sh
gpu-apps                    # mở danh sách, Space để tick, Enter để lưu
gpu-apps list               # xem app nào đang bật
gpu-apps enable chromium    # bật cho một app (theo tên hoặc id)
gpu-apps disable chromium   # trả về GPU mặc định
gpu-apps refresh            # sinh lại sau khi app được cập nhật
gpu-apps status             # xem tiến trình nào đang dùng card NVIDIA
```

Sau khi bật hoặc tắt, phải đóng hẳn app rồi mở lại.

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
- **Cập nhật app**: file ghi đè là bản sao, nên sau khi gói được cập nhật hãy chạy `gpu-apps refresh`.

## Kiểm thử

```sh
python3 -m unittest discover -s tests
```
