"""Lazy native read judge; shared Librarian profile routing, never project writes."""
import os

from python.kernel.errors import AppError
from python.substrate.context.librarian_read import LibrarianRead, _LOCK


class JudgeRead(LibrarianRead):
    def _public_value(self, value, root):
        if isinstance(value, str):
            for prefix in (root.replace('\\', '\\\\')+'\\\\', root+'\\', root.replace('\\', '/')+'/'):
                value = value.replace(prefix, 'res://')
            return value
        if isinstance(value, dict):
            return {key: self._public_value(item,root) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._public_value(item,root) for item in value]
        return value

    def judge(self, full_text, *, allow_addons=False, allow_self_edit=False):
        return self._evaluate(full_text, False, allow_addons, allow_self_edit)

    def select(self, variants):
        return self._evaluate(variants, True, False, False)

    def _evaluate(self, value, multiple, allow_addons, allow_self_edit):
        if not os.path.isdir(self._project):
            raise AppError('not_found', 'корень проекта не найден')
        self._guard_storage()
        with _LOCK:
            from python.substrate.llm import runtime_bindings
            runtime_bindings.register()
            from . import answer_judge
            from python.substrate.context import ml_data
            from python.substrate.store import history_manager
            from python.substrate.engine import gd_api_cache
            from python.substrate.llm.parsers import parser_base
            previous = ml_data._BASE_OVERRIDE
            previous_history = history_manager._STORAGE_OVERRIDE
            previous_migration = gd_api_cache._migrate_legacy_addon_cache
            previous_sample = parser_base._save_corpus_sample
            try:
                parser_base._save_corpus_sample = lambda _raw, _error: None
                gd_api_cache._migrate_legacy_addon_cache = lambda _addon_dir: None
                history_manager.set_storage_dir(str(self.storage_base))
                history_path = history_manager._STORAGE_OVERRIDE
                if not history_path or os.path.normcase(os.path.abspath(history_path)) != os.path.normcase(str(self.history_dir)):
                    raise AppError('denied', 'хранилище истории профиля judge недоступно')
                routed = ml_data.set_storage_base(str(self.storage_base))
                if not routed or os.path.normcase(os.path.abspath(routed)) != os.path.normcase(str(self.log_path.parent)):
                    raise AppError('denied', 'хранилище профиля judge недоступно')
                self._guard_storage()
                with self.view(allow_addons=allow_addons,allow_self_edit=allow_self_edit) as root:
                    from python.substrate.fs.project_view import view_addon
                    evaluate=answer_judge.select_best_project_answer if multiple else answer_judge.judge_answer
                    result=evaluate(root, value, addon_dir=view_addon(root,self._project,self.addon_dir),
                                    allow_addons=allow_addons, allow_self_edit=allow_self_edit)
                    if multiple:
                        key,text,best,all_results=result
                        return key,text,self._public_value(best,root),self._public_value(all_results,root)
                    return self._public_value(result,root)
            finally:
                ml_data._BASE_OVERRIDE = previous
                history_manager._STORAGE_OVERRIDE = previous_history
                gd_api_cache._migrate_legacy_addon_cache = previous_migration
                parser_base._save_corpus_sample = previous_sample
