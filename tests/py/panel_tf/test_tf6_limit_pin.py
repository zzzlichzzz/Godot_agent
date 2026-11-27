"""D108 measured permission cannot accept old bytes or same-size mutations."""
from pathlib import Path
import hashlib
import pytest

ROOT = Path(__file__).resolve().parents[3]
ROUTE = 'python/substrate/assistant/server/chat_routes.py'


def test_delivered_route_cap_is_exact_full_sha_not_filename_only():
    from tools import check_limits
    raw = (ROOT / ROUTE).read_bytes()
    assert check_limits.SERVER_NATIVE_CAPS[ROUTE] == (1142, hashlib.sha256(raw).hexdigest())
    assert raw.count(b'\n') == raw.count(b'\r\n') == 1142


@pytest.mark.parametrize('change', ['same-size', 'old-pin'])
def test_measured_permission_refuses_non_delivered_bytes(tmp_path, monkeypatch, change):
    from tools import check_limits
    raw = (ROOT / ROUTE).read_bytes()
    if change == 'same-size':
        raw = raw.replace(b'POST', b'P0ST', 1)
    else:
        monkeypatch.setattr(check_limits, 'SERVER_NATIVE_CAPS', {
            ROUTE: (1169, '91c8a9689096a670d9b514d09c58829d38d294edc8140f43554d98077fdfda0f')})
    path = tmp_path / ROUTE
    path.parent.mkdir(parents=True); path.write_bytes(raw)
    monkeypatch.setattr(check_limits, 'ROOT', tmp_path)
    monkeypatch.setattr(check_limits, 'PYTHON', tmp_path / 'python')
    assert check_limits.check_files() == [ROUTE + ': 1142 строк (лимит 400)']
