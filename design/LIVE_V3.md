# Live v3: owner feedback after the first real-phone tasks (17/11/2026 ~19:05)

Owner, after "mở zalo và xem tin nhắn từ marry pham" (took 3 min 9 s):
1. The live log is mostly noise. Keep it, collapsed and compact.
2. Input (the task) and output (the answer) need their own clear places.
3. Wanted: watch the PC screen from the phone, like a video player.
4. The keyboard/mouse lock and the glow only happen while the AI is physically acting, so the owner can still click in the gaps between steps and break the run. From the moment a task is sent until the answer arrives, the PC must be locked and glowing the whole time.

Also seen in that run's events:
- The task was submitted twice within 1 s. Two tasks then shared one Claude process and one failed with `readuntil() called while another coroutine is already waiting`.
- `launch_app("zalo")` failed (not on PATH). The agent then spent about 2 minutes opening File Explorer windows to find the Start Menu shortcut, and left three Explorer windows open.

## Decisions

### A. Whole-task lock and glow (hub + desktop-mcp)
- A task started from the phone holds the lock and the solid glow from `task_started` until `task_finished`, in every preset. Config is `[input_lock] remote_task = "whole_task"` (default), with `"real_input"` as the alternative. Local `turbo_hub run` keeps `mode`.
- The hub writes `<state>/task_active.json` = `{"task": id, "since": epoch, "heartbeat": epoch, "source": "phone"}` and refreshes the heartbeat every 5 s. It deletes the file when the task ends, on STOP, and on takeover.
- desktop-mcp watches the file once a second:
  - If it exists and the heartbeat is under 15 s old: lock input, show the solid glow and the banner "AI đang làm việc theo lệnh từ điện thoại · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng".
  - If the heartbeat is stale, for example because the hub died: release.
  - Esc ×3 releases the lock, writes `<state>/owner_took_over.json`, and the hub pauses the task, as it does now for takeover.
- Hard cap is `[input_lock] max_task_minutes = 15`. When it is reached, desktop-mcp releases and the hub pauses with a reason.
- desktop-mcp also writes `<state>/indicator.json` and `<state>/input_lock.json` and honours `<state>/RELEASE`. The hub's bridge.py already reads these, but nothing was writing them.

### B. One task at a time (hub + app)
- `POST /tasks` while a task is running returns 409 `{"detail":"busy","running":id}`. Queuing can come later.
- The app disables Send while a send is in flight and while a task is running.

### C. launch_app finds apps by their Start Menu name (desktop-mcp)
- If the name is not an executable on PATH or an App Paths entry, search Start Menu `.lnk` files in `%ProgramData%` and `%APPDATA%` by display name (case- and diacritic-insensitive, prefix match), then search UWP apps via `shell:AppsFolder`.
- Report what was launched and how: `{"how":"start-menu","shortcut":...}`.
- Operator prompt: "close windows you opened only to look for something".

### D. Screen view on the phone (hub + app)
- `GET /screen.jpg?w=960&q=60` needs a session and a signed request. It returns a JPEG of the primary monitor.
  - **Redaction before encoding:** black out every visible top-level window whose title matches the secret patterns (the same list as desktop-mcp's deny zone, in `[privacy] secret_title_patterns`).
  - Rate limit: at most `[screen_view] max_fps` (default 2) per device.
- While frames are being served (in the last 5 s), the PC shows a small banner, "Điện thoại đang xem màn hình". Audit `screen_view` once per minute of viewing.
- `[screen_view] enabled`: true for easy and balanced, false for strict.
- Known limit: what is on screen is visible, apart from redacted windows. Password fields show dots anyway.

### E. App layout (mockups v3 before code)
The Tasks and Live tabs become one "Việc" screen:
1. A 16:9 screen player at the top. It shows a still frame when idle and refreshes live while a task runs. Tap to go full screen; it has a pause button.
2. The current task card holds the prompt (input), a status line ("Đang làm · bước 7 · 1:42"), and below it the answer (output) in full as soon as it arrives.
3. "Chi tiết từng bước", collapsed by default. It is one line per step with an icon and a short label; consecutive reads are grouped.
4. The composer stays at the bottom, as in a chat app. Send is disabled while busy.

History is a list under the card; tapping an item opens its prompt and answer. The bottom navigation shrinks to Việc · Duyệt · Nhật ký · Cài đặt.

### F. Numbers out of the main screens (owner, 19:20)
Token counts and the raw log on the main screens confused the owner. No token or cost figures on Việc. The Nhật ký tab becomes **Báo cáo** with two segments:
- **Tổng quan**: tasks done, stopped or failed; time the AI worked; tasks per day; tokens in plain words with a one-line explanation; top apps used.
- **Nhật ký**: the audit list.

Dollar amounts are hidden by default. They can be turned on in Settings with "Hiện chi phí quy đổi theo API".
