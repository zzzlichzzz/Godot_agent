"""F2: explicit empty addon only for the approved cache-degradation cases."""
import pytest
from python.runtime import bootstrap

CASE_IDS = {
    'test_api.py': {'013', '014', '015', '016'},
    'test_api_check.py': {'033', '034', '035'},
    'test_verify.py': {'001', '002', '003', '023', '024', '031', '045', '071', '072'},
    'test_verify_bom.py': {'045'},
}
ALWAYS = {
    ('test_api.py', 'test_same_agent_reads_replaced_or_removed_cache'),
    ('test_api_check.py', 'test_same_agent_observes_cache_changes'),
    ('test_tscn_lint_ports.py', 'test_default_bootstrap_binds_consumer_protocols'),
}


@pytest.fixture
def no_bundled_api_cache(request, tmp_path, monkeypatch):
    filename, name = request.node.path.name, request.node.originalname
    parameters = getattr(request.node, 'callspec', None)
    case = parameters.params.get('case') if parameters else None
    selected = (filename, name) in ALWAYS or (
        case is not None and case['id'].split('-', 1)[0] in CASE_IDS.get(filename, set()))
    if not selected:
        return None
    addon = tmp_path / 'explicit-empty-addon'
    addon.mkdir()
    constructor = bootstrap.ApiCacheStore

    def isolated(project_root, state_dir=None, addon_dir=None):
        return constructor(project_root, state_dir=state_dir, addon_dir=addon)

    monkeypatch.setattr(bootstrap, 'ApiCacheStore', isolated)
    return addon
