"""D70 lazy pinned API/parser adapter; all persistent state is profile-owned."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import logging
import os
from pathlib import Path

from python.kernel.errors import AppError
from python.substrate.context.librarian_read import _LOCK, _contains


class ChatGateway:
    def __init__(self, project_root, state_dir, addon_dir):
        self.project_root = Path(project_root).absolute()
        self.state_dir = Path(state_dir).absolute()
        self.addon_dir = Path(addon_dir).absolute()
        key = hashlib.sha256(str(self.project_root).encode('utf-8')).hexdigest()
        self.storage_base = self.state_dir/'assistant_chat'/key
        self.config_dir = self.state_dir/'api_config'
        self._record = None
        self._spent = {}

    def _guard_storage(self):
        profile = os.path.normcase(os.path.realpath(self.state_dir))
        forbidden = [os.path.normcase(os.path.realpath(p)) for p in
                     (self.project_root, self.addon_dir)]
        paths = [self.state_dir, self.config_dir, self.storage_base,
                 self.config_dir/'api_keys.json', self.config_dir/'api_keys.json.tmp',
                 self.config_dir/'models_cache.json', self.config_dir/'catalog.json',
                 self.storage_base/'chats.json', self.storage_base/'api_history']
        inherited = os.environ.get('GODOT_AGENT_CONFIG_DIR')
        if inherited and any(_contains(root, os.path.normcase(os.path.realpath(inherited))) for root in forbidden):
            raise AppError('denied', 'хранилище ключей не может находиться в проекте')
        for base in (self.config_dir, self.storage_base):
            if base.is_dir():
                for directory, folders, files in os.walk(base, followlinks=False):
                    paths.extend(Path(directory)/name for name in (*folders, *files))
        for path in paths:
            actual = os.path.normcase(os.path.realpath(path))
            if not _contains(profile, actual) or any(_contains(root, actual) for root in forbidden):
                raise AppError('denied', 'хранилище chat должно быть внутри профиля и вне проекта')

    def system_prompt(self, *, tree='', architecture='', godot_version='4'):
        from python.substrate.llm.api import agent_prompts
        return agent_prompts.PRIMING_TEMPLATE.replace('{godot_version}', godot_version).replace(
            '{architecture}', architecture).replace('{tree}', tree)

    def send(self, prompt, *, system_text=None, provider=None, model=None, max_chars=200000):
        if not self.project_root.is_dir():
            raise AppError('not_found', 'корень проекта не найден')
        self._guard_storage()
        with _LOCK:
            from python.substrate.llm import runtime_bindings
            runtime_bindings.register()
            from python.substrate.llm.backends.api_backend import ApiBackend
            from python.substrate.llm.api import api_keys, chat_store
            from python.substrate.llm.parsers import parser_base
            previous_env = os.environ.get(api_keys.ENV_CONFIG_DIR)
            previous = (api_keys._cfg_cache, api_keys._secrets_cache,
                        api_keys._dirs_ready, api_keys._session_spent,
                        parser_base._save_corpus_sample)
            log = StringIO()
            try:
                os.environ[api_keys.ENV_CONFIG_DIR] = str(self.config_dir)
                api_keys._cfg_cache = {'key': False, 'value': None}
                api_keys._secrets_cache = {'list': None}
                api_keys._dirs_ready = {}
                api_keys._session_spent = self._spent
                parser_base._save_corpus_sample = lambda _raw, _error: None
                self._guard_storage()
                with redirect_stdout(log):
                    defaults = api_keys.get_defaults()
                    if self._record is None:
                        pid = provider or defaults.get('provider') or ''
                        pinned_model = model or defaults.get('model') or api_keys.get_model(pid)
                        record = chat_store.create_chat(str(self.storage_base), title=chat_store.title_from_prompt(prompt))
                        self._record = chat_store.update_chat(str(self.storage_base), record['id'],
                                                             provider=pid, model=pinned_model)
                    fixed = system_text if system_text is not None else self.system_prompt()
                    backend = ApiBackend(self._record, str(self.storage_base), system_text_provider=lambda: fixed)
                    reply = backend.send(prompt)
                    raw = reply.get('raw') or ''
                    candidate = raw or reply.get('text') or ''
                    best = parser_base.select_best_answer_variant([('api', candidate[:max_chars])])
                    text, action_raw = parser_base.split_net_text_and_action(best[1])
                    action, error = parser_base.parse_action_json(action_raw) if action_raw else (None, None)
                    value = dict(text=text, raw=raw[:max_chars], action=action,
                                 done=parser_base.DONE_MARKER in raw,
                                 finish_reason=reply.get('finish_reason') or '', parse_error=error or '')
                    return self._redact(value, api_keys.redact)
            finally:
                try:
                    logging.getLogger('godot_agent.chat').info(api_keys.redact(log.getvalue()))
                finally:
                    (api_keys._cfg_cache, api_keys._secrets_cache, api_keys._dirs_ready,
                     api_keys._session_spent, parser_base._save_corpus_sample) = previous
                    if previous_env is None:
                        os.environ.pop(api_keys.ENV_CONFIG_DIR, None)
                    else:
                        os.environ[api_keys.ENV_CONFIG_DIR] = previous_env

    @staticmethod
    def _redact(value, redact):
        if isinstance(value, str):
            return redact(value)
        if isinstance(value, dict):
            return {key: ChatGateway._redact(item, redact) for key, item in value.items()}
        if isinstance(value, list):
            return [ChatGateway._redact(item, redact) for item in value]
        return value
