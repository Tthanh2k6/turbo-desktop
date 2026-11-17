# turbo-desktop hub

Cho AI điều khiển máy tính Windows của bạn, và bạn ra lệnh, duyệt, xem trực tiếp, bấm STOP từ điện thoại.
Hub là chương trình Python chạy trên máy tính. Nó nhận lệnh, chạy một agent AI (mặc định Claude Code), chuyển các câu hỏi "cho phép không?" sang điện thoại.

## Bắt đầu nhanh (5 phút, mức Thoáng)

Cần: Windows 10/11, Python 3.12+, Claude Code đã đăng nhập (hoặc agent khác, xem bên dưới).

```powershell
cd hub
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m turbo_hub setup        # Enter = Thoáng; trả lời c nếu bạn sẽ ghép điện thoại (cùng Wi-Fi)
.venv\Scripts\python -m turbo_hub serve        # để cửa sổ này chạy
```

Cửa sổ khác:

```powershell
.venv\Scripts\python -m turbo_hub run "mở Máy tính và tính (12,5 + 7) * 3"
```

Nếu bạn trả lời có cho điện thoại, hub nghe thêm trên địa chỉ LAN của máy (không bao giờ 0.0.0.0) để điện thoại cùng Wi-Fi ghép được. Không ghép điện thoại thì hub chỉ nghe 127.0.0.1.

Việc nhạy cảm (xoá vĩnh viễn, thanh toán, gỡ phần mềm, cài đặt bảo mật Windows) sẽ hỏi ngay trong cửa sổ này: gõ `c` để cho phép, phím khác để từ chối. Không cần điện thoại. Muốn dùng điện thoại thì xem "Ghép điện thoại".

Dừng khẩn cấp: `python -m turbo_hub stop` (hoặc nút STOP trên điện thoại, hoặc phím nóng của desktop-mcp). Cho chạy lại: `python -m turbo_hub resume`.

## Ba mức bảo mật

| | Thoáng (mặc định) | Cân bằng | Chặt |
|---|---|---|---|
| Kết nối | máy này; thêm LAN nếu bạn ghép điện thoại | + LAN, Tailscale | Tailscale, Cloudflare (có Access) |
| Phiên | 12 giờ | 2 giờ | 2 giờ |
| Mã Google Authenticator | không | khi mở phiên | khi mở phiên |
| Vân tay trên điện thoại | không | không | có (mở phiên + duyệt) |
| Hỏi trước khi | xoá vĩnh viễn, thanh toán, gỡ phần mềm, cài đặt bảo mật Windows | + gửi, xoá, cài đặt, terminal | + OK trong hộp thoại xoá/thanh toán, Enter trong chat, Task Manager |
| Vùng cấm | ô mật khẩu | + trình quản lý mật khẩu, ngân hàng | + ứng dụng Windows Security |
| Khoá phím/chuột khi AI dùng chuột thật | khi đang dùng chuột thật | khi đang dùng chuột thật | cả việc |

Chọn lại bất cứ lúc nào: `python -m turbo_hub setup`, hoặc sửa một mục trong `turbo-desktop.toml`. Mọi mục đều có thể bật/tắt riêng.

## Phần không tắt được (nền tối thiểu)

Các mục này luôn bật ở mọi mức vì chúng không tốn gì của bạn mà chặn được hậu quả xấu nhất:

- **STOP** (điện thoại, lệnh `stop`, phím nóng): nếu AI làm sai, bạn phải dừng được ngay.
- **Nhật ký kiểm toán** nối chuỗi băm: sửa hoặc xoá một dòng sẽ bị phát hiện.
- **Giá trị ô mật khẩu không bao giờ gửi cho mô hình** (desktop-mcp thực thi).
- **Mọi yêu cầu không phải từ localhost phải do thiết bị đã ghép ký hợp lệ**: không có điều khiển từ xa ẩn danh.
- **Chỉ ghép thiết bị ngay tại máy tính**, trong cửa sổ 5 phút, không bao giờ qua tunnel.
- Khung cam trên màn hình và thanh thông báo luôn hiện khi AI đang gửi phím/chuột thật hoặc đang khoá bàn phím.

## Ghép điện thoại

```powershell
.venv\Scripts\python -m turbo_hub pair
```

In mã QR (hết hạn sau 5 phút) và một dòng `turbo-pair:...` để dán nếu không quét được. Mở app Turbo Remote, quét. App tạo khoá trong Android Keystore (không xuất ra được). Hai bên đối chiếu 5 nhóm ký tự "mã hub" để chắc chắn đúng máy.

Mã 2FA chỉ có ở mức Cân bằng và Chặt; mức Thoáng không hỏi mã và app không hiện ô nhập. App biết điều này qua `GET /policy` và câu trả lời lúc ghép.

Khi cần 2FA, ghép xong hub mở "cửa sổ lấy khoá" trong 5 phút (bằng thời hạn mã ghép). Trong lúc đó, ngay trên điện thoại, vào Cài đặt > 2FA bấm **Thêm vào Authenticator** (hoặc sao chép khoá, hoặc gõ khoá chữ). Khoá chỉ tải được một lần, cần cả hai khoá thiết bị (có vân tay) và không đi qua tunnel. Cũng có thể quét mã QR thứ hai mà lệnh `pair` in ra. Mỗi lần mở phiên (hết 2 giờ) app hỏi mã 6 số rồi hỏi vân tay. Một mã chỉ dùng được một lần.

Mất mục Authenticator hoặc đổi điện thoại: chạy `python -m turbo_hub totp` (hiện lại khoá, mở lại cửa sổ 5 phút cho điện thoại) hoặc `python -m turbo_hub totp --rotate` (tạo khoá mới, mục cũ hết tác dụng ngay).

Thu hồi một điện thoại: `python -m turbo_hub devices` rồi `python -m turbo_hub revoke <id>`.

## Kết nối từ ngoài nhà

`[server] connections` trong `turbo-desktop.toml` là danh sách xếp theo thứ tự thử: `local`, `lan`, `tailscale`, `cloudflare`. Hub chỉ nghe trên 127.0.0.1 và địa chỉ của từng cách bạn bật, không bao giờ nghe 0.0.0.0.

### Tailscale (khuyên dùng)
Cài Tailscale trên máy tính và điện thoại, đăng nhập cùng tài khoản. Thêm `"tailscale"` vào `connections`. Hub tự nghe trên địa chỉ 100.x.

### Cloudflare Tunnel (khi không dùng được Tailscale)
`cloudflared` chỉ kết nối ra ngoài, không mở cổng trên router.
```powershell
cloudflared tunnel login
cloudflared tunnel create turbo
cloudflared tunnel route dns turbo turbo.ten-mien-cua-ban.com
cloudflared tunnel run --url http://127.0.0.1:8750 turbo
```
Trong `turbo-desktop.toml`: `[server] connections = ["tailscale","cloudflare"]` và `[cloudflare] url = "https://turbo.ten-mien-cua-ban.com"`.

**Nên đặt Cloudflare Access** (Zero Trust, gói miễn phí) trước tên miền đó: đăng nhập bằng email một lần mã hoặc Google. Đây là lớp chặn thêm trước khi yêu cầu chạm tới hub. Mức Chặt đặt `require_access = true`: hub từ chối yêu cầu qua tunnel nếu không có dấu vết đã qua Access. Hạn chế hiện tại: app chưa có màn hình đăng nhập Access (dự kiến mở WebView lấy cookie `CF_Authorization`); khi bật Access hãy thêm một chính sách Bypass hoặc Service Token, hoặc chờ bản UI.

Dù đi đường nào: mọi yêu cầu vẫn phải có chữ ký, dấu thời gian trong 60 giây, nonce chưa dùng; phản hồi và sự kiện của hub được ký nên app phát hiện endpoint giả. Sai 5 lần trong 10 phút từ một nguồn bị khoá 15 phút, hub ghi nhật ký và báo cho điện thoại. Nhớ rằng địa chỉ `http://` qua Internet không mã hoá nội dung: dùng https (Cloudflare) hoặc Tailscale.

## Đánh thức máy tính từ xa (Wake-on-LAN)

Máy tính không tự bật được. Cần một thiết bị luôn bật trong cùng mạng LAN (máy tính bảng root có Termux, Raspberry Pi, một PC khác) chạy `relay/wol_relay.py` (chỉ dùng thư viện chuẩn của Python):

```bash
python wol_relay.py serve --mac AA:BB:CC:DD:EE:FF --bind 100.x.y.z --pair
```
Relay chỉ nghe trên địa chỉ Tailscale bạn đưa vào, chỉ nhận yêu cầu ký bởi điện thoại đã ghép với relay (danh sách riêng), rồi gửi gói magic packet tới cổng 9 và 7. Trong app có nút "Đánh thức PC": gọi relay rồi hỏi hub cho tới khi trả lời (tối đa 2 phút).

Điều kiện, nói thẳng:
- Wi-Fi gần như không bật được máy qua WOL, nhất là laptop. **Máy cần cắm dây mạng (Ethernet).** Máy đang dùng Wi-Fi thì tính năng này sẽ không chạy.
- Bật Wake on LAN trong BIOS/UEFI.
- Trong Device Manager, card mạng > Power Management: bật "Allow this device to wake the computer" và "Only allow a magic packet to wake the computer".
- Tắt Fast Startup (Control Panel > Power Options) nếu muốn đánh thức từ trạng thái tắt hẳn.
- Máy không tự mở khoá màn hình. Dùng khi máy không đặt khoá tự động, hoặc đã đăng nhập.

## Dùng agent khác (Codex, Gemini CLI, mô hình chạy cục bộ)

```toml
[agent]
mode = "oneshot"
command = ["codex", "exec", "{task}"]
parser = "text"       # hoặc "jsonl"
```
Chế độ `oneshot` chạy một tiến trình mỗi việc và hiển thị từng dòng đầu ra. Hub **không thể chặn từng thao tác** của một CLI không có cơ chế duyệt quyền; vẫn có STOP, nhật ký và các vùng cấm của desktop-mcp nếu agent dùng nó. Chế độ mặc định `claude-stream-json` giữ một tiến trình Claude Code chạy suốt phiên (nhanh, không khởi động lại mỗi lệnh) và hỏi hub trước mỗi thao tác.

## Hiển thị trên điện thoại

Token và chi phí hiện theo việc, theo phiên và theo ngày (lấy từ kết quả của agent). Khi AI dùng chuột/phím thật, điện thoại hiện khung cam và dòng "AI đang điều khiển" hoặc "PC đang khoá phím/chuột", cùng nút **Lấy lại quyền** (mở khoá ngay và tạm dừng việc, cho chạy tiếp bằng nút Resume). Trên điện thoại Xiaomi/HyperOS, app chạy dịch vụ nền với thông báo cố định và hướng dẫn tắt tối ưu pin, bật tự khởi động; app không dùng FCM.

## Phần nâng cao / bảo mật

**Danh tính.** Ghép bằng QR + mã 6 số dùng một lần (5 phút, tối đa 5 lần thử). Điện thoại có hai khoá EC P-256 trong Keystore: khoá thường (ký mọi yêu cầu) và khoá bắt xác thực (vân tay mạnh hoặc mã khoá màn hình, hiệu lực 30 giây) dùng để mở phiên và trả lời duyệt. Hub lưu khoá công khai của cả hai.

**Yêu cầu có chữ ký.** `METHOD\nPATH?QUERY\nSHA256(body)\nTS\nNONCE`, ECDSA-SHA256 (DER, base64), tiêu đề `X-Device, X-Ts, X-Nonce, X-Sig` (+ `X-Auth-Sig`, `X-Session`). Hub từ chối chữ ký sai, thời gian lệch quá 60 giây, nonce dùng lại, thời điểm trước lúc hub khởi động (nonce chỉ ở trong bộ nhớ). Phản hồi và sự kiện SSE được hub ký (khoá hub được ghim lúc ghép).

**Phiên.** Mở bằng yêu cầu ký hai khoá + mã TOTP (RFC 6238, SHA1, 6 số, ±1 bước, không dùng lại bước đã dùng). Mặc định phiên chỉ nằm trong bộ nhớ: khởi động lại hub thì phải mở lại. `session.persist = true` để giữ (mã hoá DPAPI).

**Duyệt.** desktop-mcp phân loại hành động (nó biết tên điều khiển thật) và hỏi qua tệp trong `desktop-state/`; hub chuyển sang điện thoại kèm ảnh cắt điều khiển; không trả lời sau 2 phút = Từ chối. `approval.engine = "hub"` dùng danh mục trong `turbo-desktop.toml` cho agent không có desktop-mcp.

**Bí mật trên máy.** Khoá riêng của hub, danh sách thiết bị, khoá TOTP, phiên (nếu bật) mã hoá bằng DPAPI (người dùng hiện tại). Giới hạn thật: mã độc chạy cùng tài khoản Windows vẫn gọi được DPAPI; lớp này chỉ ngăn chép tệp sang máy khác.

**Chống dò.** Khoá 15 phút sau 5 lần sai trong 10 phút từ một nguồn (chữ ký, TOTP, ghép), giới hạn kích thước thân 64 KB, kiểm tra thiết bị đã biết trước mọi bước tốn kém. Không có endpoint nào không cần xác thực ngoài `/pair`, và `/pair` + `/admin/*` bị từ chối nếu thấy tiêu đề của proxy/tunnel.

**Nhật ký.** `audit.jsonl`, mỗi dòng gắn băm sha256 của dòng trước. `python -m turbo_hub verify-audit` kiểm tra. Giới hạn: cắt bớt các dòng cuối thì chuỗi vẫn hợp lệ; muốn chống cần neo băm ra ngoài.

**Tiến trình agent.** Nằm trong Windows job object: hub chết đột ngột thì agent chết theo; lần khởi động sau dọn nốt phần còn sót.

**Cấu hình.** Thứ tự tìm `turbo-desktop.toml` (giống desktop-mcp): biến `TURBO_DESKTOP_CONFIG`, thư mục hiện tại, `%APPDATA%\turbo-desktop\`, thư mục người dùng. Hub luôn truyền đường dẫn đó và tên mức (`TURBO_DESKTOP_PRESET`) cho tiến trình agent để desktop-mcp dùng cùng mức. Mọi khoá có chú thích nằm trong `hub/turbo_hub/defaults.toml`.

**Kiểm thử.**
```powershell
.venv\Scripts\python scripts\with_lock.py -- .venv\Scripts\python -m pytest -q   # xin khoá chung để không chạy trùng desktop-mcp
.venv\Scripts\python -m pytest ..\relay\tests -q
.venv\Scripts\python scripts\gen_vectors.py                                    # tạo lại vector chữ ký cho test Android
powershell -File scripts\smoke_real.ps1 calc                                   # chạy thật: tốn chút hạn mức Claude (Haiku)
```

## Thử trên điện thoại thật (việc 32, chờ bạn)

1. Cài Tailscale trên cả hai máy. Chạy `setup`, chọn Cân bằng, thêm Tailscale vào `connections`, chạy `serve`.
2. `python -m turbo_hub pair`, quét QR trong app, so mã hub, quét QR Authenticator.
3. Mở phiên (mã 6 số + vân tay), giao việc "mở Máy tính và tính 2+2".
4. Đợi hết phiên (hoặc đặt `session.hours` nhỏ), mở lại chỉ bằng mã + vân tay, không quét QR.
5. Bật chế độ máy bay vài giây giữa lúc chạy: app phải báo mất kết nối, không báo thành công giả; bật lại thì hiện đúng trạng thái.
