"""SEC-K1: profile-only secrets and unconditional lazy-adapter restoration."""
import importlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from tests.py.chat_k1.isolation import isolated_chat_native_generation

ROOT=Path(__file__).resolve().parents[3]

@pytest.mark.parametrize('fault',['logger','redactor'])
def test_restores_even_when_final_log_raises(tmp_path,monkeypatch,fault):
    from python.substrate.assistant.chat_gateway import ChatGateway
    from python.substrate.llm import runtime_bindings
    runtime_bindings.register()
    from python.substrate.llm.api import api_keys
    from python.substrate.llm.backends.api_backend import ApiBackend
    from python.substrate.llm.parsers import parser_base
    project=tmp_path/'project'; project.mkdir()
    monkeypatch.setenv(api_keys.ENV_CONFIG_DIR,str(tmp_path/'original'))
    before=(os.environ[api_keys.ENV_CONFIG_DIR],api_keys._cfg_cache,api_keys._secrets_cache,
            api_keys._dirs_ready,api_keys._session_spent,parser_base._save_corpus_sample)
    def interrupt(*a,**k): raise KeyboardInterrupt('synthetic finalization failure')
    target='python.substrate.assistant.chat_gateway.logging.Logger.info' if fault=='logger' else 'python.substrate.llm.api.api_keys.redact'
    try:
        with (patch.object(ApiBackend,'send',return_value=dict(raw='ok\n===DONE===',finish_reason='stop')),
              patch(target,side_effect=interrupt)):
            with pytest.raises(KeyboardInterrupt):
                ChatGateway(project,tmp_path/'state',ROOT).send('hello',provider='custom',model='offline')
        after=(os.environ[api_keys.ENV_CONFIG_DIR],api_keys._cfg_cache,api_keys._secrets_cache,
               api_keys._dirs_ready,api_keys._session_spent,parser_base._save_corpus_sample)
        assert after[0]==before[0] and all(a is b for a,b in zip(after[1:],before[1:]))
        assert list(project.rglob('*'))==[]
    finally:
        os.environ[api_keys.ENV_CONFIG_DIR]=before[0]
        (api_keys._cfg_cache,api_keys._secrets_cache,api_keys._dirs_ready,
         api_keys._session_spent,parser_base._save_corpus_sample)=before[1:]

def test_mask_redact_protect_reply_action_and_log(tmp_path,monkeypatch,caplog):
    from python.substrate.assistant.chat_gateway import ChatGateway
    from python.substrate.llm import runtime_bindings
    runtime_bindings.register()
    from python.substrate.llm.api import api_keys
    from python.substrate.llm.backends.api_backend import ApiBackend
    project=tmp_path/'project'; project.mkdir()
    state=tmp_path/'state'; config=state/'api_config'; config.mkdir(parents=True)
    token='synthetic-private-value-93857'
    (config/'api_keys.json').write_text(json.dumps({'providers':{'custom':{'keys':[{'key':token}]}},
        'defaults':{'provider':'custom','model':'offline'}}),encoding='utf-8')
    monkeypatch.setenv(api_keys.ENV_CONFIG_DIR,str(tmp_path/'original'))
    def echo(*a,**k):
        print('native diagnostic '+token)
        return dict(raw='secret '+token+'\n```agent_action\n'+json.dumps({'action':'invented','data':token})+'\n```\n===DONE===',finish_reason='stop')
    with patch.object(ApiBackend,'send',echo),caplog.at_level('INFO'):
        result=ChatGateway(project,state,ROOT).send('hello')
    assert token not in json.dumps(result) and token not in caplog.text
    assert token not in os.environ[api_keys.ENV_CONFIG_DIR]
    assert list(project.rglob('*'))==[]
