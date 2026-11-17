# Turbo Remote performance (measured 17/11/2026, Xiaomi 25098PN5AC, Android 16 / HyperOS)

Method: `adb shell am start -S -W` (3 cold starts), `dumpsys meminfo` (TOTAL PSS after start), `dumpsys gfxinfo` reset → 10 s idle / 15 s live screen view at 1 fps, `top` for CPU. Hub frame: `capture_screen_jpeg()` on the PC (Lenovo LOQ 15IAX9).

| | Before | After |
|---|---|---|
| Frames drawn while idle (10 s) | 108, CPU ~11% | 2, CPU ~0% |
| Frames drawn, live view 1 fps (15 s) | 963, CPU ~30%, p99 109 ms | 120 (debug) / 218 with taps (release), p99 9 ms (release) |
| Cold start (TotalTime) | 478–547 ms (debug) | 116–171 ms (release) |
| Memory (TOTAL PSS) | 158 MB (debug) | 79 MB (release) |
| APK | 108 MB (debug) | 11.1 MB (release, R8 + shrinkResources, arm64-v8a) |
| PC frame for screen view | | ~40 KB JPEG at 960 px q60, 50–80 ms capture + encode (first call ~700 ms) |

Fixes:
- The edge "breathing" animation ran all the time and was read during composition, so the whole main screen recomposed every frame. It now runs only while the AI is acting, and the value is read inside the draw lambda.
- The approvals countdown ticked every second even with nothing pending.
- The screen-view JPEG is decoded on `Dispatchers.Default` instead of the main thread.
- Release build: R8, resource shrinking, arm64 only. Install `app/build/outputs/apk/release/app-release.apk` on phones; the debug build is for the emulator and the adb test hooks.

Data use of screen view: about 40 KB per frame, so 1 fps ≈ 2.4 MB/min, 0.5 fps ≈ 1.2 MB/min, 5 fps ≈ 12 MB/min.
