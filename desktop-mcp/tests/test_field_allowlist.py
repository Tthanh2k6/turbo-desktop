"""Unit tests enforcing strict target allowlist and launch argument splitting in run_field.py / engine.py."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "field"))
import run_field  # noqa: E402
from turbo_desktop import engine  # noqa: E402


@pytest.mark.parametrize("good", [
    "calc",
    "calculator",
    "Calculator",
    "turbo_fixture.exe",
    "turbo_editor.exe",
    "turbo_canvas.exe",
    str(run_field.FIX / "turbo_fixture.exe"),
    str(run_field.FIX / "turbo_editor.exe"),
    str(run_field.FIX / "turbo_canvas.exe"),
])
def test_allowlist_accepts_only_calc_and_fixtures(good):
    assert run_field.validate_target(good) in run_field.ALLOWED_TARGETS


@pytest.mark.parametrize("bad", [
    "",
    "notepad",
    "notepad.exe",
    "explorer",
    "explorer.exe",
    "vscode",
    "code",
    "edge",
    "msedge",
    "chrome",
    "settings",
    "systemsettings",
    "mspaint",
    "paint",
    "control",
    "clock",
    "photos",
    "powershell",
    "cmd",
    r"C:\tmp\evil\turbo_fixture.exe",
])
def test_allowlist_rejects_disallowed_targets(bad):
    with pytest.raises(ValueError):
        run_field.validate_target(bad)


def test_all_30_tasks_pass_allowlist_and_have_no_forbidden_apps():
    assert [str(i) for i in range(1, 31)] == list(run_field.TASKS.keys())
    for tid, task in run_field.TASKS.items():
        normed = run_field.validate_task(task)
        assert normed, tid
        assert not run_field.refuses(task), f"task {tid} matched refuses()"


def test_validate_task_rejects_disallowed_target_and_forbidden_prompt():
    with pytest.raises(ValueError):
        run_field.validate_task({"targets": ["notepad.exe"], "prompt": "Open something"})
    with pytest.raises(ValueError):
        run_field.validate_task({"targets": ["turbo_editor.exe"], "prompt": "Open Explorer on temp"})
    with pytest.raises(ValueError):
        run_field.validate_task({"prompt": "Missing targets"})


def test_split_launch_args_preserves_windows_paths_with_spaces():
    got = engine._split_launch_args('--mode vfiles --workdir "C:\\Users\\TRUNG THANH\\AppData\\Local\\Temp\\turbo-field"')
    assert got == ["--mode", "vfiles", "--workdir", r"C:\Users\TRUNG THANH\AppData\Local\Temp\turbo-field"]
    assert engine._split_launch_args("--splash 5.5") == ["--splash", "5.5"]
    assert engine._split_launch_args("") == []


def test_resolve_launch_target_recognizes_shell_appsfolder_explicitly():
    res = engine.resolve_launch_target(r"shell:AppsFolder\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App")
    assert res is not None
    assert res["how"] == "appsfolder"
    assert res["appId"] == "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
    assert res["path"] == r"shell:AppsFolder\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"


def test_system_state_reports_on_input_desktop():
    from turbo_desktop import winsys
    st = winsys.system_state()
    assert isinstance(st["onInputDesktop"], bool)
    assert st["onInputDesktop"] == winsys.on_input_desktop()


def test_field_transcript_helpers_handle_double_encoded_json_and_snapshot_error(tmp_path):
    assert not run_field._is_tool_error('{"result":"{\\"ok\\":true,\\"via\\":\\"pattern\\",\\"snapshotError\\":\\"no window matches \'w2\'\\"}"}')
    assert run_field._is_tool_error('{"result":"{\\"ok\\":false,\\"error\\":\\"element has no ExpandCollapse pattern\\"}"}')
    assert run_field._is_tool_error("Error: bad ref")

    (tmp_path / "transcript.json").write_text(
        '[{"tool":"inspect_compact","result":"{\\"result\\":\\"-- 0 elements, treeEmpty: true, via: \\\\\\"ocr\\\\\\"\\"}"}'
        ',{"tool":"act","result":"{\\"result\\":\\"{\\\\\\"ok\\\\\\":true,\\\\\\"length\\\\\\":600}\\"}"}'
        ',{"tool":"batch_actions","result":"{\\"result\\":\\"{\\\\\\"ok\\\\\\":false,\\\\\\"steps\\\\\\":[{\\\\\\"stopped\\\\\\":true}]}\\"}"}]',
        encoding="utf-8",
    )
    assert run_field._any_result_has(tmp_path, 'via: "ocr"')
    assert run_field._any_result_has(tmp_path, '"length":600')
    assert run_field._any_result_has(tmp_path, '"stopped":true')
    assert 'Short code' in run_field.TASKS["19"]["prompt"]
    assert "00abcdefgh" in run_field.TASKS["19"]["prompt"] and "59abcdefgh" in run_field.TASKS["19"]["prompt"]
