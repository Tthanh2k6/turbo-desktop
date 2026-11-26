# Báo cáo đêm 18/11: rà soát và sửa turbo-desktop

Làm từ 00:10 đến 02:45. Nguồn danh sách: [AUDIT_DEM_18-11.md](AUDIT_DEM_18-11.md) (Gemini đọc toàn bộ hub, desktop-mcp, app, các file design và tài liệu, 32 mục có dẫn file). Claude kiểm lại từng mục trước khi giao.

Phân vai: Codex hết lượt đến 14:56 ngày 18/11, nên phần backend giao Gemini 4 Argon High, phần app giao Gemini kèm skill frontend-design, web-design-guidelines, ui-ux-pro-max. Claude giao việc, chạy test, sửa chỗ hỏng và commit. Mỗi việc commit riêng, chưa push.

## Việc làm trước khi rà soát (cùng đêm)
| Việc | Commit | Kiểm thật |
|---|---|---|
| Hoàn tất tối ưu B4 của desktop-mcp | `a26cf1f` | Suite 175 qua; bench Calculator 4 lượt/714 token → 2 lượt/621 token |
| Duyệt lệnh Claude Code từ xa (điện thoại + hộp duyệt trên PC, không timeout) | `5212683` | Phiên CLI phụ: bấm trên PC → chạy; chủ máy bấm trên điện thoại 2 lần → chạy; STOP → từ chối. Máy ảo: thẻ duyệt + thông báo đẩy |
| Zoom và độ nét khi xem màn hình | `c3cdf3c` | Máy ảo: chạm đúp → tải phần đang xem nét, chạm đúp lại → về bình thường. Đo trên PC: 960 px ~35 KB, 1600 px ~108 KB, 1920 px ~195 KB, phần zoom 17–34 KB |
| Tài liệu thiết kế còn dở trong git status | `b836fc4` | |
| CODEBASE.md + agent.md | `7e1e4ef`, `7e5bea8` | Claude đối chiếu đường dẫn và lệnh trong tài liệu với repo |

## Kết quả 32 mục
| # | Mức | Mục | Trạng thái | Commit |
|---|---|---|---|---|
| 1 | P1 | Hub đọc sai khoá trạng thái PC (khoá máy, pin) nên không bao giờ chặn | Đã sửa + test | `fd597a1` |
| 2 | P1 | App luôn hỏi vân tay kể cả khi mức bảo mật không yêu cầu | **Giữ nguyên, có chủ ý**: duyệt lệnh từ xa nên luôn cần vân tay. Hub vẫn chấp nhận khi không bật | — |
| 3 | P1 | Mở app bằng tên Start Menu ("Bitwarden", "Windows PowerShell") lách được luật cấm | Đã sửa + test | `e20967b` |
| 4 | P1 | Ảnh màn hình gửi điện thoại không che cửa sổ trình quản lý mật khẩu, hộp duyệt | Đã sửa + test | `fd597a1` |
| 5 | P1 | OCR và ảnh cắt cho duyệt không che ô mật khẩu | Đã sửa + test | `e20967b` |
| 6 | P1 | Hộp duyệt cục bộ của desktop-mcp chưa nằm trong vùng cấm | Đã sửa + test | `e20967b` |
| 7 | P1 | Nhật ký và sự kiện trên điện thoại thiếu cửa sổ/điều khiển/hành động | Đã sửa + test | `fd597a1` |
| 8 | P1 | `tasks.jsonl` lưu nội dung câu lệnh | **Giữ**: anh muốn lịch sử còn sau khi khởi động lại hub; file chỉ nằm trên máy anh | — |
| 9 | P1 | Đăng nhập Cloudflare Access trong app mở ra trình duyệt ngoài | Đã sửa (WebViewClient, DOM storage, trạng thái trống) | `03986db` |
| 10 | P2 | Mặc định 5 hình/giây khác tài liệu (2) | **Giữ 5** (đã chỉnh có chủ ý hôm 17/11), sửa tài liệu | `b9bd8fd` |
| 11 | P2 | `windows_list` dạng chữ làm tóm tắt trên điện thoại hiện thô | Đã sửa + test | `fd597a1` |
| 12 | P2 | `launch_app` có thể chờ 2 lần thời gian `wait` | **Giữ**: đúng brief B4 (chờ thêm cho app khởi động qua launcher như Zalo) | — |
| 13 | P2 | Việc bị STOP không ghi token; báo cáo bỏ qua token cache | Đã sửa + test | `fd597a1`, `322760a` |
| 14 | P2 | "App dùng nhiều" trong Báo cáo bỏ sót phần lớn thao tác | Đã sửa + test | `ec56258` |
| 15 | P2 | Thêm mục `[desktop.*]` vào toml làm mất preset cấp ngoài | Đã sửa + test | `e20967b` |
| 16 | P2 | Nhật ký trên app hiện mã thô cho yêu cầu Claude Code, chế độ khoá | Đã sửa + test | `03986db` |
| 17 | P2 | Chọn mức bảo mật trên app không đổi được mức của PC | Đã thêm dòng giải thích trên màn Chào mừng (mức trên PC quyết định) | `03986db` |
| 18 | P2 | Thu hồi thiết bị không lưu phiên; luồng sự kiện chạy tiếp sau khi phiên mất | Đã sửa + test | `fd597a1` |
| 19 | P2 | Tin header `Cf-Connecting-Ip` từ mọi nguồn | Đã sửa + test. Claude sửa thêm: bản của Gemini bỏ đếm lần sai của request qua proxy (thử mật khẩu vô hạn được), nay đếm riêng nhóm `proxy:<ip>` | `fd597a1` |
| 20 | P2 | Gọi Win32 qua ctypes thiếu kiểu tham số | Đã sửa | `fd597a1`, `e20967b` |
| 21 | P2 | Khoá cả việc (mức Chặt) tự nhả sau 8 giây chờ model | Nâng lên 45 giây cho `whole_task` + test | `e20967b` |
| 22 | P2 | Ẩn nhầm nút "Close" hợp lệ trong hộp thoại | Đã sửa + test | `e20967b` |
| 23 | P2 | `act` không có window/ref thì lỗi nội bộ | Đã sửa + test | `e20967b` |
| 24 | P2 | Rò GDI khi chụp cửa sổ lỗi | Đã sửa + test | `e20967b` |
| 25 | P2 | File cấu hình MCP tạm không bao giờ xoá; `taskkill` chặn vòng lặp async | Đã sửa | `fd597a1` |
| 26 | P2 | Bấm việc cũ không thấy câu trả lời | Đã sửa (hub lưu `answer`, app hiện) + test | `fd597a1`, `03986db` |
| 27 | P2 | Khi tạm dừng, đầu trang vẫn báo "AI đang điều khiển" | Đã sửa | `03986db` |
| 28 | P2 | Ô relay trùng nhãn; URL thiếu `http://` làm app crash | Đã sửa + test | `03986db` |
| 29 | P2 | Thiếu test giao diện v3 | Đã thêm 3 test giao diện; 9/9 qua trên máy ảo Android 16 | `5bdceab` |
| 30 | P3 | Nhãn "control", "qua UIA" sai chỗ | Đã sửa | `fd597a1`, `03986db` |
| 31 | P3 | Script chạy thật bỏ mất OPERATOR_PROMPT; script máy ảo chỉ hiểu tiếng Việt | Đã sửa | `b9bd8fd` |
| 32 | P3 | README/DESIGN lỗi thời | Đã sửa | `b9bd8fd`, `2c3b03b` |

Tổng: 28 đã sửa, 4 giữ nguyên có lý do (2, 8, 10, 12).

## Test sau cùng
- hub: 110 qua.
- desktop-mcp: 185 qua, 8 bỏ qua (test chuột/phím thật, chỉ chạy khi máy rảnh ≥ 2 phút; đêm nay anh còn dùng máy).
- Android: test đơn vị qua, 9/9 test giao diện qua trên máy ảo, build release 11,1 MB.
- Bench desktop-mcp sau sửa: Calculator 2 lượt / 617 token, form 2 lượt / 373 token.
- Hub đang chạy đã khởi động lại với code mới (02:1x).

## Chưa làm
- Cài app mới lên điện thoại: máy không cắm USB, adb không thấy. Tải ở `http://100.92.52.84:8799/turbo-remote-18-11.apk` (qua Tailscale) rồi cài đè.
- Thử hook duyệt với bản VS Code của Claude Code: chưa bật hook cho các phiên thật (anh tự bật bằng `python -m turbo_hub cc-hook install`).
- 8 test chuột/phím thật và đợt chạy 30 việc thật: cần anh không dùng máy.
- Keystore release riêng (app vẫn ký bằng khoá debug).
- 3 mục "Not sure" trong bản rà soát (tranh chấp file trạng thái khi tải nặng, gõ tiếng Việt qua UniKey, nhiều màn hình khác DPI): cần chạy thật.
