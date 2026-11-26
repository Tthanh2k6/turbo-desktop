# Brief B1: hub (Python) for Live v3

Read design/LIVE_V3.md (sections A, B, D are yours, hub side only), then hub/README.md and hub/turbo_hub/{app.py,manager.py,bridge.py,runners.py,config.py,defaults.toml,__main__.py} and hub/tests/ (style, conftest lock, fixtures). You can only read/edit files; you cannot run commands. The PM runs the tests and will send failures back.

Do:
1. **B. One task at a time.** `POST /tasks` while a task is running returns 409 `{"detail":"busy","running":<id>}`. Use the manager's existing state. Add a test that fires two posts back to back: one is accepted, the other gets 409, and the runner is never called twice at once.
2. **A. task_active heartbeat.** When a task starts from a phone, i.e. a device request rather than the local admin `run`, write `<desktop_state_dir>/task_active.json` = `{"task","since","heartbeat","source":"phone","max_minutes"}` atomically (temp file + replace). Refresh the heartbeat every 5 s while the task runs. Delete the file on task end, failure, STOP and takeover. Config: `[input_lock] remote_task = "whole_task"` (or `"real_input"`, which means do not write the file) and `max_task_minutes = 15`. Put both in defaults.toml with comments, same value in all presets. If `<state>/owner_took_over.json` appears, treat it as takeover: pause the task, emit `taken_over`, delete both files. The bridge may already poll `<state>`; extend it. Add tests with a temp state dir.
3. **D. Screen view.** `GET /screen.jpg`, query `w` (max width, default and maximum 960) and `q` (JPEG quality 30–80, default 60), dependency `in_session`.
   - Capture the primary monitor with the `mss` library. Add it to hub/requirements.txt.
   - Before encoding, black out the rectangle of every visible top-level window whose title matches `[privacy] secret_title_patterns`. Use ctypes EnumWindows, IsWindowVisible, GetWindowTextW and GetWindowRect, and DWM extended frame bounds when available.
   - Default patterns, the same as desktop-mcp's deny zone: `.env`, `secret`, `credentials`, `.pem`, `.key`, `id_rsa`, `.kdbx`, `token`, `password`, `mật khẩu`, `api_key`. Copy the exact list from desktop-mcp/src/turbo_desktop/security.py and put it in defaults.toml. Match case-insensitively.
   - Response is `image/jpeg`. Header `X-Redacted: <n>` gives the number of blacked-out windows. Sign the response the same way other replies are signed: check how `reply()` signs and do the equivalent for bytes.
   - Rate limit per device: `[screen_view] max_fps` (default 2). Faster requests get 429.
   - `[screen_view] enabled` is true for easy and balanced, false for strict. When off, return 403 "screen view is off".
   - Audit `screen_view` at most once per 60 s per device.
   - Write `<state>/screen_view.json` = `{"until": now+5}` on each frame so desktop-mcp can show "Điện thoại đang xem màn hình" on the PC.
   - Put the capture and redaction in a separate module, `screen.py`, with the window enumeration injectable so tests can feed fake windows and a fake frame. Tests:
     - redaction blacks out the right rectangle;
     - the rate limit;
     - off in strict;
     - requires a session.
4. In `runners.OPERATOR_PROMPT` add one sentence: "Close any window you opened only to look for something before you finish."
5. In `/policy` and `/status`, expose `screenView: {enabled, maxFps}` and `lockRemoteTask`.
6. Update hub/README.md (Vietnamese, short): the whole-task lock, screen view, and the 409 busy response.

Do not touch android/, desktop-mcp/, design/ (except reading). Do not change the request-signing or pairing logic. Do not read .env files.

Final answer: changed files, new config keys, tests added, anything unfinished. Under 250 words.
