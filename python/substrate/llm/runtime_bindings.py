"""Explicit B/D33 legacy-name binding; never imported by production bootstrap."""
from importlib import import_module
import sys
from threading import RLock
from python.substrate.context.runtime_parent import bind_parent

BINDINGS = (
    ('cdp_ws', 'python.substrate.llm.browser.cdp_ws'),
    ('net_monitor', 'python.substrate.llm.browser.net_monitor'),
    ('sites', 'python.substrate.llm.browser.sites'),
    ('browser_manager', 'python.substrate.llm.browser.browser_manager'),
    ('ai_studio_net', 'python.substrate.llm.browser.ai_studio_net'),
    ('qwen_net', 'python.substrate.llm.browser.qwen_net'),
    ('text_sanitize', 'python.substrate.llm.parsers.text_sanitize'),
    ('parser_base', 'python.substrate.llm.parsers.parser_base'),
    ('kimi_parser', 'python.substrate.llm.parsers.kimi_parser'),
    ('ai_parser', 'python.substrate.llm.parsers.ai_parser'),
    ('qwen_parser', 'python.substrate.llm.parsers.qwen_parser'),
    ('deepseek_parser', 'python.substrate.llm.parsers.deepseek_parser'),
    ('project_tools', 'python.substrate.project.project_tools'),
    ('project_settings_actions', 'python.substrate.project.project_settings_actions'),
    ('server_state', 'python.substrate.llm.runtime_owner'),
    ('api_keys', 'python.substrate.llm.api.api_keys'),
    ('openai_compat', 'python.substrate.llm.api.openai_compat'),
    ('providers', 'python.substrate.llm.api.providers'),
    ('model_cache', 'python.substrate.llm.api.model_cache'),
    ('catalog', 'python.substrate.llm.api.providers_catalog'),
    ('anthropic_compat', 'python.substrate.llm.api.anthropic_compat'),
    ('agent_prompts', 'python.substrate.llm.api.agent_prompts'),
    ('rate_limit', 'python.substrate.llm.api.rate_limit'),
    ('md_to_bbcode', 'python.substrate.llm.api.md_to_bbcode'),
    ('chat_store', 'python.substrate.llm.api.chat_store'),
    ('api_history', 'python.substrate.llm.api.api_history'),
    ('runtime_debug', 'python.substrate.editor.references.runtime_debug'),
    ('editor_context', 'python.substrate.editor.references.editor_context'),
    ('api_backend', 'python.substrate.llm.backends.api_backend'),
    ('history_manager', 'python.substrate.store.history_manager'),
    ('gd_api_cache', 'python.substrate.engine.gd_api_cache'),
    ('gd_api_check', 'python.substrate.verification.gd_api_check'),
    ('gd_lint', 'python.substrate.verification.gd_lint'),
    ('gd_semantic_parser', 'python.substrate.context.gd_semantic_parser'),
    ('librarian', 'python.substrate.context.librarian'),
    ('tscn_lint', 'python.substrate.verification.tscn_lint'),
    ('runtime_checks', 'python.substrate.verification.runtime_checks'),
    ('godot_headless_validation', 'python.substrate.verification.godot_headless_validation'),
    ('scene_deps', 'python.substrate.scene.scene_deps'),
    ('scene_actions', 'python.substrate.editing.scene_actions'),
    ('file_refactor', 'python.substrate.editing.file_refactor'),
    ('resource_actions', 'python.substrate.editing.resource_actions'),
    ('transaction_actions', 'python.substrate.editing.transaction_actions'),
    ('high_level_actions', 'python.substrate.assistant.high_level_actions'),
    ('symbol_refactor_data', 'python.substrate.code_intel.symbol_refactor_data'),
    ('symbol_refactor_part1', 'python.substrate.code_intel.symbol_refactor_part1'),
    ('symbol_refactor_part2', 'python.substrate.code_intel.symbol_refactor_part2'),
    ('symbol_refactor_part3', 'python.substrate.code_intel.symbol_refactor_part3'),
    ('symbol_refactor', 'python.substrate.code_intel.symbol_refactor'),
    ('answer_judge', 'python.substrate.assistant.answer_judge'),
)
_LOCK, _ABSENT = RLock(), object()


def register():
    """Identity-preserving/idempotent; reject conflicts and roll back new aliases."""
    with _LOCK:
        added = []
        try:
            for name, target in BINDINGS:
                if name == 'librarian':
                    bind_parent(added)
                module = import_module(target)
                previous = sys.modules.get(name, _ABSENT)
                if previous is not _ABSENT and previous is not module:
                    raise RuntimeError('legacy alias already bound: ' + name)
                if previous is _ABSENT:
                    sys.modules[name] = module
                    added.append((name, module))
        except BaseException:
            for name, module in reversed(added):
                if sys.modules.get(name) is module:
                    del sys.modules[name]
            raise


register()
