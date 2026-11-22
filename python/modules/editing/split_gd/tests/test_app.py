"""Consumer-owned fs seam; refusal before IO, no ambient filesystem access."""
import errno
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.modules.editing.split_gd import app


class Fs:
    def __init__(self, files=None, failure=None, stage='read'):
        self.files = files if files is not None else {'plugin.cfg': b'', 'donor.gd': b'func ping():\n\tpass\n'}
        self.failure, self.stage, self.events = failure, stage, []

    def event(self, stage, rel=''):
        self.events.append((stage, rel))
        if self.stage == stage and self.failure:
            raise self.failure

    def is_file(self, rel):
        self.event('is_file', rel)
        return rel in self.files

    def read_raw(self, rel):
        self.event('read', rel)
        value = self.files[rel]
        if isinstance(value, Exception):
            raise value
        return value

    def list_files(self):
        self.event('list')
        return list(self.files)


def context(fs, denied=()):
    return SimpleNamespace(port=lambda name: fs,
        path_policy=SimpleNamespace(deny_reason=lambda rel: 'policy refusal' if rel in denied else ''))


@pytest.mark.parametrize('args,kind', [({}, 'invalid_input'), ({'path': False}, 'invalid_input'),
    ({'path': ''}, 'invalid_input'), ({'path': 'donor.gd'}, 'invalid_input'),
    ({'path': 'res://donor.py'}, 'invalid_input'), ({'path': 'res://../donor.gd'}, 'denied'),
    ({'path': 'res://a\x00.gd'}, 'denied'), ({'path': 'res://C:/a.gd'}, 'denied'),
    ({'path': 'res://donor.gd', 'extra': 1}, 'invalid_input')])
def test_refusal_before_any_fs_access(args, kind):
    fs = Fs()
    with pytest.raises(AppError) as caught:
        app.call('split_gd_scan', args, context(fs))
    assert caught.value.kind == kind and fs.events == []


def test_donor_policy_refusal_before_fs():
    fs = Fs()
    with pytest.raises(AppError) as caught:
        app.call('split_gd_scan', {'path': 'res://donor.gd'}, context(fs, ('donor.gd',)))
    assert caught.value.kind == 'denied' and str(caught.value) == 'policy refusal'
    assert fs.events == []


@pytest.mark.parametrize('files,kind', [({}, 'not_found'), ({'donor.gd': b''}, 'invalid_input')])
def test_missing_donor_and_missing_addon_no_content_reads(files, kind):
    fs = Fs(files)
    with pytest.raises(AppError) as caught:
        app.call('split_gd_scan', {'path': 'res://donor.gd'}, context(fs))
    assert caught.value.kind == kind and not any(e[0] == 'read' for e in fs.events)


@pytest.mark.parametrize('stage', ['is_file', 'read', 'list'])
@pytest.mark.parametrize('error,kind', [(PermissionError('private absolute secret'), 'denied'),
    (OSError(errno.EFBIG, 'private'), 'invalid_input'), (OSError(errno.EIO, 'private'), 'internal')])
def test_io_failure_classified_and_sanitized(stage, error, kind):
    fs = Fs(failure=error, stage=stage)
    with pytest.raises(AppError) as caught:
        app.call('split_gd_scan', {'path': 'res://donor.gd'}, context(fs))
    assert caught.value.kind == kind and 'private' not in str(caught.value)


@pytest.mark.parametrize('stage,kind', [('is_file', 'internal'), ('read', 'not_found'), ('list', 'internal')])
def test_missing_during_read_is_donor_refusal_not_blanket_oserror(stage, kind):
    fs = Fs(failure=FileNotFoundError('private absolute path'), stage=stage)
    with pytest.raises(AppError) as caught:
        app.call('split_gd_scan', {'path': 'res://donor.gd'}, context(fs))
    assert caught.value.kind == kind and 'private' not in str(caught.value)


@pytest.mark.parametrize('extra,allowed', [(0, True), (1, False)])
def test_raw_donor_limit_inclusive(extra, allowed):
    fs = Fs({'plugin.cfg': b'', 'donor.gd': b'x' * (READ_TEXT_MAX_BYTES + extra)})
    if allowed:
        assert app.call('split_gd_scan', {'path': 'res://donor.gd'}, context(fs))['lines'] == 1
    else:
        with pytest.raises(AppError) as caught:
            app.call('split_gd_scan', {'path': 'res://donor.gd'}, context(fs))
        assert caught.value.kind == 'invalid_input'


def test_nearest_root_deny_and_read_error_neighbors_skipped():
    fs = Fs({'plugin.cfg': b'', 'inner/plugin.cfg': b'',
             'inner/src/donor.gd': b'func ping():\n\tpass\n',
             'outer.txt': b'donor.gd', 'inner/no.txt': b'donor.gd',
             'inner/gone.txt': OSError('gone'), 'inner/yes.txt': b'donor.gd',
             'inner/build/no.gd': b'.ping()'})
    result = app.call('split_gd_scan', {'path': 'res://inner/src/donor.gd'},
                      context(fs, ('inner/no.txt',)))
    assert result['donor'] == 'src/donor.gd' and result['soft_files'] == ['yes.txt']
    reads = [rel for stage, rel in fs.events if stage == 'read']
    assert 'outer.txt' not in reads and 'inner/no.txt' not in reads and 'inner/build/no.gd' not in reads


def test_unknown_tool_typed_not_enveloped():
    fs = Fs()
    with pytest.raises(AppError) as caught:
        app.call('split_gd_missing', {}, context(fs))
    assert caught.value.kind == 'unknown_tool' and fs.events == []
