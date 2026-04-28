from pathlib import Path


def test_writing_area_reports_activity_with_12s_throttle():
    repo_root = Path(__file__).resolve().parents[3]
    writing_area = repo_root / "frontend" / "src" / "components" / "layout" / "WritingArea.vue"
    content = writing_area.read_text(encoding="utf-8")

    assert "const ACTIVITY_REPORT_INTERVAL_MS = 12000" in content
    assert "function reportWritingActivity()" in content
    assert "roomApi.reportRoomActivity(roomId, 'writing').catch(() => {})" in content
    assert "function handleInput()" in content
    assert "reportWritingActivity()" in content
    handle_input_section = content.split("function handleInput()", 1)[1].split("function focusEditor()", 1)[0]
    assert "reportWritingActivity()" in handle_input_section
    confirm_section = content.split("async function confirmSubmit()", 1)[1].split("async function initWritingDoc()", 1)[0]
    assert "reportWritingActivity()" in confirm_section
