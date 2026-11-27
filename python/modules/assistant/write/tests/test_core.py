"""Pure native delta compilation and fail-closed identity validation."""
import base64
import pytest

def test_raw_before_hash_and_crlf_bytes_are_not_normalized():
    from python.modules.assistant.write.domain import core
    before=b'old\r\n';after=b'new\r\n'
    plan,diffs=core.compile_plan([dict(path='res://x.txt',before_bytes=before,after_bytes=after)],{'action':'patch_file'},{},'plan1')
    assert base64.b64decode(plan.steps[0].payload['bytes_b64'])==after
    assert diffs[0]['before']=='old\r\n' and diffs[0]['after']=='new\r\n'

@pytest.mark.parametrize('value',['../x','C:/x','/x','..\\x','',None,'x'*101])
def test_plan_identity_is_checked_before_any_wal_access(value):
    from python.modules.assistant.write.domain import core
    from python.kernel.errors import AppError
    with pytest.raises(AppError):core.validate_id(value)

def test_binary_move_uses_existing_move_not_text_decode_or_a_second_writer():
    from python.modules.assistant.write.domain import core
    raw=b'\x89PNG\r\n\x1a\n\x00\xff'
    files=[dict(path='res://a.png',before_bytes=raw,after_bytes=None),dict(path='res://b.png',before_bytes=None,after_bytes=raw)]
    plan,_=core.compile_plan(files,dict(action='move_file',path='res://a.png',dest='res://b.png'),{},'p1')
    assert len(plan.steps)==1 and plan.steps[0].op=='move' and plan.steps[0].compensates=='move'

def test_assistant_rollback_cannot_adopt_an_untagged_historical_plan():
    from python.modules.assistant.write.domain import core
    from python.kernel.errors import AppError
    with pytest.raises(AppError,match='assistant.write'):
        core.require_owned([dict(state='PREPARED',detail=dict(tool='editing.write_preview'))])

@pytest.mark.parametrize('action',[
    dict(action='create_file',path='res://safe.txt:stream',content='synthetic'),
    dict(action='transaction',operations=[dict(action='move_file',path='res://a.gd',dest='res://b.gd:stream')]),
    dict(action='rename_symbol',declaration='res://a.gd:stream:2'),
])
def test_windows_ads_is_denied_before_native_preparation(action):
    from python.modules.assistant.write.domain import core
    from python.kernel.errors import AppError
    with pytest.raises(AppError):core.validate_action(action)

def test_declaration_coordinates_and_file_content_remain_data():
    from python.modules.assistant.write.domain import core
    core.validate_action(dict(action='rename_symbol',declaration='res://a.gd:12:3'))
    core.validate_action(dict(action='create_file',path='res://a.txt',content='res://safe.txt:stream'))

def test_report_path_cannot_hide_windows_ads():
    from python.modules.assistant.write.domain import core
    from python.kernel.errors import AppError
    with pytest.raises(AppError):
        core.compile_plan([dict(path='res://safe.txt:stream',before_bytes=None,after_bytes=b'synthetic')],{}, {},'p1')
