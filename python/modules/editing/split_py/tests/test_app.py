"""Orchestration with fs-only fakes; denial before reads and safe error mapping."""
import errno
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError


class FS:
    def __init__(self, files=None, fail=None):
        self.files = {'plugin.cfg':b'[plugin]\n', 'donor.py':b'# donor.py\n', 'ref.py':b'import donor\n'} if files is None else files
        self.fail = fail or {}
        self.calls = []

    def perform(self, method, rel=''):
        self.calls.append((method,rel))
        if (method,rel) in self.fail:
            raise self.fail[method,rel]

    def is_file(self, rel):
        self.perform('is_file',rel)
        return rel in self.files

    def read_raw(self, rel):
        self.perform('read_raw',rel)
        return self.files[rel]

    def list_files(self):
        self.perform('list_files')
        return sorted(self.files)


def invoke(args, fs=None, denied=None, tool='split_scan'):
    from python.modules.editing.split_py.app import call
    fs = fs or FS()
    policy = SimpleNamespace(deny_reason=lambda rel: (denied or {}).get(rel))
    return call(tool, args, SimpleNamespace(port=lambda name: fs, path_policy=policy))


@pytest.mark.parametrize('args, kind', [({},'invalid_input'),({'path':None},'invalid_input'),
    ({'path':''},'invalid_input'),({'path':7},'invalid_input'),({'path':'donor.py'},'invalid_input'),
    ({'path':'res://donor.txt'},'invalid_input'),({'path':'res://../donor.py'},'denied'),
    ({'path':'res://C:/donor.py'},'denied'),({'path':'res://donor\0.py'},'denied'),
    ({'path':'res://donor.py','extra':1},'invalid_input')])
def test_reject_before_io(args, kind):
    fs = FS()
    with pytest.raises(AppError) as error:
        invoke(args, fs)
    assert error.value.kind == kind and fs.calls == []


def test_policy_before_metadata():
    fs = FS()
    with pytest.raises(AppError) as error:
        invoke({'path':'res://donor.py'}, fs, {'donor.py':'policy denied'})
    assert error.value.kind == 'denied' and error.value.message == 'policy denied' and not fs.calls


@pytest.mark.parametrize('files, kind', [({'plugin.cfg':b''},'not_found'),({'donor.py':b''},'invalid_input')])
def test_missing_and_no_root_before_read(files, kind):
    fs = FS(files)
    with pytest.raises(AppError) as error:
        invoke({'path':'res://donor.py'}, fs)
    assert error.value.kind == kind and not any(m=='read_raw' for m,r in fs.calls)


@pytest.mark.parametrize('method, rel', [('is_file','donor.py'),('is_file','plugin.cfg'),
    ('read_raw','donor.py'),('list_files','')])
@pytest.mark.parametrize('error, kind', [(PermissionError('C:/secret'),'denied'),
    (OSError(errno.EFBIG,'C:/secret'),'invalid_input'), (OSError(errno.EIO,'C:/secret'),'internal'),
    (FileNotFoundError('C:/secret'),'internal')])
def test_safe_os_errors(method, rel, error, kind):
    fs = FS(fail={(method,rel):error})
    if method == 'read_raw' and isinstance(error,FileNotFoundError):
        kind = 'not_found'
    with pytest.raises(AppError) as raised:
        invoke({'path':'res://donor.py'},fs)
    assert raised.value.kind == kind and 'C:/secret' not in raised.value.message


def test_size_boundary_and_neighbor_skip():
    with pytest.raises(AppError) as error:
        invoke({'path':'res://donor.py'},FS({'plugin.cfg':b'', 'donor.py':b'x'*(4*1024*1024+1)}))
    assert error.value.kind == 'invalid_input'
    fs = FS({'plugin.cfg':b'', 'donor.py':b'x'*(4*1024*1024), 'ref.py':b'import donor\n'})
    assert invoke({'path':'res://donor.py'},fs)['counts']['import'] == 1


def test_neighbor_denied_unreadable_and_outside():
    fs = FS({'inner/plugin.cfg':b'', 'inner/donor.py':b'# donor.py',
             'outside.py':b'import donor\n', 'inner/private.py':b'import donor\n', 'inner/bad.py':b'import donor\n',
             'inner/__pycache__/ref.py':b'import donor\n', 'inner/good.py':b'import donor\n'},
             {('read_raw','inner/bad.py'):OSError(errno.EIO,'C:/secret')})
    answer = invoke({'path':'res://inner/donor.py'},fs,{'inner/private.py':'denied'})
    assert answer['counts']['import'] == 1 and answer['hard_files'] == ['good.py']
    reads = [r for m,r in fs.calls if m=='read_raw']
    assert 'outside.py' not in reads and 'inner/private.py' not in reads and 'inner/__pycache__/ref.py' not in reads


def test_unknown_tool():
    fs = FS()
    with pytest.raises(AppError) as error:
        invoke({},fs,tool='split_unknown')
    assert error.value.kind == 'unknown_tool' and not fs.calls
