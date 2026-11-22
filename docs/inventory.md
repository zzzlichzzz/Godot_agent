# Карта старого плагина (справочник, не код)

Снято с `addons/Godot_agent/godot_agent` (проект `тест-плагина-ии`).
Разделы — каталоги, внутри — файлы по алфавиту. Для каждого файла:
док-стринг или шапка, классы, функции с сигнатурами, константы,
упоминания инструментов MCP.

Это данные, а не код: лимит R-06 (400 строк) на файл не действует.
Генератор одноразовый и в репозитории не хранится.

## Оглавление

- `.` — 37 файлов (раздел 1)
- `docs` — 8 файлов (раздел 2)
- `docs/limitations` — 1 файл (раздел 3)
- `python` — 3 файла (раздел 4)
- `python/agent_api_cache/agent_api_history` — 1 файл (раздел 5)
- `python/api` — 7 файлов (раздел 6)
- `python/backends` — 2 файла (раздел 7)
- `python/browser` — 7 файлов (раздел 8)
- `python/godot_tools` — 31 файл (раздел 9)
- `python/minilich` — 8 файлов (раздел 10)
- `python/parsers` — 7 файлов (раздел 11)
- `python/server` — 12 файлов (раздел 12)
- `python/tests` — 168 файлов (раздел 13)
- `python/tests/data` — 1 файл (раздел 14)
- `python/tests/fixtures` — 9 файлов (раздел 15)
- `python/tools` — 13 файлов (раздел 16)

## .

### agent_api_export.gd — 4 КБ
- extends: RefCounted

### agent_chat_view.gd — 45 КБ
- extends: Node
- сигналы: message_rollback_requested
- функции: _T, _color, _icon, _load_card_scene, _instantiate_card, _make_user_card, _make_agent_card, _make_plan_card, _make_diff_card, _locale, _t, setup, clear, _make_panel, _make_note_label, add_user_message, add_agent_message, _wire_card_rollback, _on_card_rollback_requested, add_system, add_pending_system, clear_pending_system, add_hint, add_success

### agent_editor_context.gd — 6 КБ
- extends: RefCounted

### agent_entry.gd — 24 КБ
- extends: EditorPlugin
- функции: _enter_tree, _report_entry_ready, _wire_node_rename_intercept, _exit_tree, _build_dock, _build_panel, _handle_command, _build_menu, _on_menu_id, dispatch_menu_id_for_test, _call_panel, _menu_title, _build_context_menus, _register_signals, _addon_path, _load_locale, _build_debugger, _make_runtime_debugger, agent_ask_about, _promote_dock_tab, _ensure_fs_dock_connected, _on_fs_files_moved, _on_fs_folder_moved, _disconnect_fs_dock

### agent_headless_validator.gd — 2 КБ
- extends: SceneTree
- функции: _initialize, _diagnostic, _finish

### agent_highlight.gd — 6 КБ
- extends: RefCounted
- функции: apply, _hook_current_code_edit, _on_hl_text_changed, on_editor_script_changed, clear, _repaint_highlight, watchdog, _mark_script_in_list_experimental

### agent_integration_signals.gd — 10 КБ
- extends: RefCounted
- функции: _init, attach, detach, subscription_count, _bind, _on_script_changed, _on_scene_changed, _watch_subtree, set_node_rename_handler, _watch_node, _clear_node_watch, _on_node_tree_exiting, _on_child_entered_tree, _on_node_renamed, _edited_scene_root, _on_scene_saved, _on_resource_saved, _on_project_settings_changed, _on_editor_state_changed

### agent_locale.gd — 84 КБ
- extends: Object

### agent_mutation_gate.gd — 12 КБ
- extends: RefCounted
- функции: configure, classify, write_scene, write_resource, write_project_settings, begin_undo, commit_undo, abort_undo, undo_pending, undo_context, record, last_entry, notify_changed, _editor_undo_redo

### agent_panel.gd — 80 КБ
- extends: Control
- функции: handle_context_ask, set_editor_plugin, set_runtime_debugger, _on_runtime_status_changed, _start_runtime_inspect, _on_runtime_inspect_completed, _on_runtime_inspect_timeout, _send_runtime_result, _start_runtime_check, _exit_tree, _execute_bound_runtime_check, _on_runtime_check_completed, _send_runtime_check_result, _send_pending_runtime_check_result, _clear_runtime_check_state, _locale, _t, _json_headers, _T, _apply_panel_theme, _ready, _set_pending_action, _has_pending_action, _clear_pending_action_state

### agent_panel_part1.gd — 61 КБ
- extends: RefCounted

### agent_panel_part2.gd — 62 КБ
- extends: RefCounted

### agent_panel_part3.gd — 57 КБ
- extends: RefCounted

### agent_panel_part4.gd — 56 КБ
- extends: RefCounted

### agent_panel_part5.gd — 9 КБ
- extends: RefCounted

### agent_project_settings_executor.gd — 17 КБ
- extends: RefCounted
- функции: configure, set_mutation_gate, _save_project_settings, prepare, execute, _ready, _touched_keys, _capture, _simulate, _simulate_operation, _setting_for, _display_mapping, _display_value, _setting_supported, _apply, _restore, _decode_input_event, _semantic_hash, _file_hash, _sha256, _with_hash, _fail

### agent_resource_executor.gd — 31 КБ
- extends: RefCounted
- функции: configure, set_mutation_gate, prepare, execute, _save_temporary_resource, _validate_saved_resource, reload_after_recovery, _open_target, _apply_operations, _apply_operation, _resolve_target, _set_property, _replace_reference, _replace_in_resource, _animation_add_value_track, _sprite_frames_add_animation, _theme_set_item, _tileset_add_atlas_source, _decode_value, _property_info, _is_stored, _value_matches_type, _value_matches_property, _values_equivalent

### agent_runtime_bridge.gd — 15 КБ
- extends: Node
- функции: _enter_tree, _exit_tree, _capture_message, _process, _start_check, _run_check_steps, _apply_input, _evaluate_assertion, _errors_since, _read_native_property, _finish_check, _capture_check_screenshot, _release_inputs, emit_event, report_error, _capture_snapshot, _capture_tree, _walk_tree, _node_summary, _capture_properties, _read_property, _capture_metrics, _safe_value

### agent_runtime_debugger.gd — 7 КБ
- extends: EditorDebuggerPlugin
- сигналы: status_changed, inspect_completed, check_completed
- функции: _has_capture, _capture, _setup_session, get_status, inspect, run_check, cancel_pending, _on_session_started, _on_session_stopped, _on_session_breaked, _on_session_continued

### agent_scene_executor.gd — 25 КБ
- extends: RefCounted
- функции: configure, set_mutation_gate, note_scene_saved, prepare, execute, _write_scene, _commit_live_scene_undo, reload_after_recovery, _scene_reload_would_lose_edits, _editor_interface, _open_target, _create_detached, _stage_new_scene, _load_detached, _apply_operations, _apply_operation, _node, _is_local, _add_node, _set_node_property, _attach_script, _connect_signal, _reparent_node, _decode_variant

### agent_server.gd — 13 КБ
- extends: RefCounted, class_name: AgentServer

### agent_server_link.gd — 29 КБ
- extends: Node
- сигналы: chats_response, link_status, show_loading_requested, hide_loading_requested, server_state_changed, short_response
- функции: _locale, _t, _ready, post_now, get_now, is_short_busy, _send_now, _on_short_response, is_inflight, request, _fire, _drain_queue, _on_response, _maybe_autostart_server, _on_server_wait_tick, _on_server_alive, _emit_retry_failures, find_server_exe_path, open_server_folder, _load_cached_server_path, _save_cached_server_path, _prefer_onedir, _launch_server_process, _spawn_server

### agent_start_screen.gd — 199 КБ
- extends: Control
- сигналы: new_chat_requested, load_chat_requested, delete_chat_requested, sites_tab_requested, chats_tab_requested, language_changed, open_server_requested, settings_requested, api_tab_requested, api_settings_save_requested, api_models_refresh_requested, api_models_scan_requested
- функции: _T, _color, _ready, _locale, _t, _lang, _on_lang_selected, _rebuild_ui, set_server_running, _apply_server_visibility, _build, _api_section, _api_hint, _build_api_view, _make_header, set_chats, set_sites, _clear_container, _rebuild_chats, _fmt_ts, _rebuild_sites, _pick_chat, _request_chat_delete, _confirm_chat_delete

### agent_theme.gd — 14 КБ
- extends: Object

### agent_updater.gd — 27 КБ
- extends: Node
- сигналы: update_available, update_progress, update_completed, update_error, check_completed
- функции: _ready, _ensure_nodes, get_current_version, check_for_updates, _on_check_completed, start_update, cancel_update, _on_progress_tick, _on_download_completed, verify_and_install_zip, _is_runtime_path, _json_headers, shutdown_server, _kill_own_server, _read_server_pid, _forget_server_pid, _is_agent_server_process, restart_editor, open_github_release

### AgentMessageCard.gd — 12 КБ
- extends: PanelContainer, class_name: AgentMessageCard
- сигналы: rollback_requested
- функции: _T, _t, _ready, _apply_locale, _ensure_rollback_button, _setup_theme, setup, append_text, set_status, add_tool_call, _refresh_collapse_state, _apply_expand_state, _on_copy_pressed, _on_rollback_pressed, set_rollback_target, set_rollback_available, _on_expand_pressed, _set_actions_shown, _show_actions, _hide_actions, get_text

### AgentStatusBar.gd — 5 КБ
- extends: PanelContainer, class_name: AgentStatusBar
- функции: _T, _t, _ready, _setup_theme, _chars_text, show_status, hide_status, update_status, _on_timer_tick, _format_time

### DiffPreviewCard.gd — 20 КБ
- extends: PanelContainer, class_name: DiffPreviewCard
- сигналы: diff_applied, diff_rejected, apply_all_requested
- функции: _T, _t, _ready, _apply_locale, _ensure_header_controls, _setup_theme, setup, setup_diff, _fill_header, set_view_full_texts, get_file_path, set_allow_all_texts, mark_auto_approved, mark_applied, mark_preview_only, _on_header_gui_input, _toggle_expanded, _update_expand_button, _apply_diff_view, _total_lines, _cut_text, _render_diff, _bg_hex, _line_number

### GODOT_INTEGRATION_ROADMAP.md — 30 КБ

### PlanChecklistCard.gd — 5 КБ
- extends: PanelContainer, class_name: PlanChecklistCard
- сигналы: plan_paused, plan_continued, plan_rollback_requested
- функции: _T, _t, _ready, _apply_locale, _setup_theme, setup, _step_scene, update_step, set_paused, _on_pause_pressed, _on_continue_pressed, _on_rollback_pressed

### PlanStepItem.gd — 3 КБ
- extends: HBoxContainer, class_name: PlanStepItem
- функции: _T, _ready, _exit_tree, _setup_theme, setup, update_status, _update_icon, _set_icon, _animate_spinner, stop_spinner

### plugin.cfg — 0 КБ

### plugin_universal.gd — 13 КБ
- extends: EditorPlugin
- функции: _enter_tree, _ensure_fs_dock_connected, _exit_tree, _on_fs_files_moved, _on_fs_folder_moved, _on_safe_rename_menu_pressed, _on_safe_node_rename_menu_pressed, _lt, _promote_dock_tab, _do_promote_once, _find_file, _build_panel

### ToolCallCard.gd — 4 КБ
- extends: PanelContainer, class_name: ToolCallCard
- функции: _T, _ready, _setup_theme, setup, _icon_for_tool, _emoji_for_tool, _format_params, _escape_bbcode, _on_toggle, _apply_expand_state

### UserMessageCard.gd — 6 КБ
- extends: PanelContainer, class_name: UserMessageCard
- функции: _T, _t, _ready, _apply_locale, _setup_theme, setup, _recalc_bubble_width, _on_copy_pressed, _set_actions_shown, _show_actions, _hide_actions, get_text

### VISUAL_UI_ROADMAP.md — 12 КБ

### ОТЛОЖЕНО.md — 39 КБ

## docs

### docs/ARCHITECTURE.md — 11 КБ

### docs/architecture_map.json — 7 КБ

### docs/function_card_plan.md — 20 КБ

### docs/librarian_search_plan.md — 63 КБ

### docs/README.md — 2 КБ

### docs/split_gd_transfer_map.md — 16 КБ

### docs/STATUS.md — 50 КБ

### docs/v3_improvements_plan.md — 24 КБ

## docs/limitations

### docs/limitations/editor_panel_ui_headless.md — 13 КБ

## python

### python/_bootstrap.py — 1 КБ
- докстринг: Настройка путей для плоских импортов (import ai_parser, import sites и т.д.). Модули разложены по подпапкам (parsers/, browser/, godot_tools/, server/, api/, backends/), но продолжают импортироваться …
- константы: _HERE, _PACKAGE_DIRS

### python/main.py — 297 КБ
- функции: _is_addon_path(path); _access_kwargs(); _with_rename_policy(action); _can_write_path(path, project_root=None); _can_read_path(path, project_root=None); _stamp_policy(container); _policy_error_response(container=None, status=409); _pending_policy_current(container); _filter_editor_snapshot_policy(snapshot, project_root); _is_project_settings_path(path); _is_text_scene_path(path); _addon_blocked_message(path); _session_context_error(exc); _admit_chat_continuation(); _current_parser(); _api_system_text()
- константы: FILE_CACHE_MAX_BYTES, MAX_RETRY_WAIT_PER_TURN, PLAN_ALLOWED_ACTIONS, _CHAT_CONTINUATION_PATHS, _EDITOR_ACTION_RESULTS, _RUNTIME_RESULTS, _RUNTIME_RESULT_LIMIT, _RUNTIME_RESULT_TTL

### python/selfcheck.py — 229 КБ
- докстринг: Простая самопроверка аддона без браузера/AI Studio/реального проекта Godot. Зачем это нужно: большая часть того, что может сломаться в агенте (план-режим, откат, защиты API/сцен), не связано с браузер…
- классы: _FP14(_pb14.BaseSiteParser) — 7 методов; _FP16(_pb16.BaseSiteParser) — 6 методов; _FD17(object) — 3 методов; _FP17(_pb17.BaseSiteParser) — 0 методов; _FP19(_pb19.BaseSiteParser) — 10 методов; _FakeGenModel21() — 2 методов; _FakeRng51(object) — 3 методов; _FP27(_pb27.BaseSiteParser) — 7 методов
- функции: check(name, cond, detail=''); fresh_project(); reset_state(root); _sig16(a); _fake_eval53(project_root, model, valid_pairs, addon_dir=None); _run29(events, **kw)
- константы: FAIL, FULL_RUN, PASS, RUN_MINILICH_NEURAL_CHECKS, _NEW16, _NEWTAB17, _OLD16, _OLDER16, _OLDTAB17, _SC18_BASE, _SC18_DOT, _SC18_OK, _SC18_SUB, _SCENE25

## python/agent_api_cache/agent_api_history

### python/agent_api_cache/agent_api_history/reprotest123.json — 0 КБ

## python/api

### python/api/anthropic_compat.py — 11 КБ
- докстринг: Минимальный Anthropic Messages API поверх общего urllib-транспорта. Нужен AgentRouter-моделям Claude: тот же ключ и base URL, но маршрут POST /messages и формат SSE отличаются от OpenAI /chat/completi…
- функции: _request_headers(api_key, extra_headers=None); _body(model, messages, max_tokens=None, temperature=None, stream=False); _usage(raw); _content_parts(obj); complete_chat(base_url, api_key, model, messages, max_tokens=None, temperature=None, extra_headers=None, proxy=None, connect_timeout=oc.DEFAULT_CONNECT_TIMEOUT, extra_body=None); stream_chat(base_url, api_key, model, messages, max_tokens=None, temperature=None, extra_headers=None, proxy=None, connect_timeout=oc.DEFAULT_CONNECT_TIMEOUT, silence_timeout=oc.DEFAULT_SILENCE_TIMEOUT, cancel_cb=None, on_delta=None, stop=None, extra_body=None)
- константы: ANTHROPIC_VERSION, DEFAULT_MAX_TOKENS

### python/api/api_keys.py — 79 КБ
- докстринг: Хранилище ключей API и настроек прокси. ГДЕ ЛЕЖИТ. Ключи ОБЩИЕ для всех проектов Godot: пользователь вводит ключ один раз, а не в каждой игре заново. Поэтому файл живёт не в user:// (это папка КОНКРЕТ…
- функции: config_dir(); config_path(); _int_or(value, default=-1); _float_or(value, default=0.0); _clean_stats(rec); _normalize_keys(rec); _load(); _stat_key(path); _invalidate_cfg(); _cfg(); _save(cfg); mask(key); redact(text); _invalidate_secrets(); _secrets(); _env_name(provider_id)
- константы: DEFAULT_DOH_URL, ENV_CONFIG_DIR, ENV_KEY_INDEX, RECENT_LIMIT, _APP_DIR_NAME, _DEFAULT_CONFIG, _FILE_NAME

### python/api/catalog.py — 59 КБ
- докстринг: Каталог моделей models.dev — ВТОРИЧНЫЙ источник сведений о моделях. ГЛАВНОЕ ПРАВИЛО, ВОКРУГ КОТОРОГО ВСЁ ПОСТРОЕНО. Живой ответ провайдера (/models) — ПЕРВИЧНАЯ правда о том, что доступно ЭТОМУ ключу.…
- функции: catalog_path(); _num_or_none(value); _clean_model(rec); is_free(info); _empty_cache(); transport_for_npm(npm); _clean_url(raw); _clean_provider_meta(pid, rec); _compact_providers(data); _load(); _int_or_zero(value); _clean_model_stored(info); _save(cache); _fetch(etag=''); _compact(data, extra_ids=()); refresh(force=False, extra_ids=())
- константы: CATALOG_URL, CONNECT_TIMEOUT, FILLABLE, FRESH_SECONDS, MAX_BYTES, MAX_ENV_NAMES, MAX_NAME_LEN, MAX_PROVIDERS, MAX_URL_LEN, NOT_IN_CATALOG, PROVIDER_MAP, RETRY_SECONDS, STATUS_DEPRECATED, _FILE_NAME, _KNOWN_STATUS, _NPM_TRANSPORT

### python/api/doh.py — 17 КБ
- докстринг: DNS over HTTPS (DoH) для запросов к провайдерам API. ЗАЧЕМ. Если провайдер (например openrouter.ai) не разрешается системным DNS — интернет-провайдер отдаёт NXDOMAIN или подменённый адрес, — обычный з…
- функции: configure(enabled, url); is_enabled(); clear_cache(); validate_url(raw); doh_host(); _build_query(host, qtype=1); _skip_name(data, i); parse_answer(data, want_type=1); is_unusable_address(ip); query(host, url=None, timeout=TIMEOUT); resolve(host); _is_local(host); _looks_like_ip(host); _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0); install(); uninstall()
- константы: DEFAULT_TTL, MAX_TTL, MIN_TTL, TIMEOUT, _LOCAL, _UNUSABLE_V4_PREFIXES, _UNUSABLE_V6

### python/api/model_cache.py — 12 КБ
- докстринг: Кэш списков моделей провайдеров — отдельным файлом от настроек. ЗАЧЕМ ЭТО НУЖНО. Панель ищет модель по названию СРАЗУ У ВСЕХ провайдеров: человек знает, что ему нужен «kimi» или «deepseek», но не знае…
- функции: cache_path(); _clean_records(records); _load(); _save(cache); put_bulk(mapping); put(provider_id, records); get(provider_id); index(); forget(provider_id)
- константы: MAX_ID_LEN, MAX_PER_PROVIDER, _CATALOG_ONLY, _FILE_NAME, _LIVE_BOOL_FIELDS, _LIVE_INT_FIELDS, _LIVE_NUM_FIELDS

### python/api/openai_compat.py — 39 КБ
- докстринг: Транспорт к нейросетям по OpenAI-совместимому протоколу. ОДИН ТРАНСПОРТ НА ВСЕХ. POST <base_url>/chat/completions с телом {model, messages, stream} понимают OpenRouter, Groq, Gemini (через слой совмес…
- классы: ApiError(Exception) — 1 методов; AuthError(ApiError) — 0 методов; ForbiddenError(ApiError) — 0 методов; PaymentRequiredError(ApiError) — 0 методов; ModelNotFoundError(ApiError) — 0 методов; RateLimitError(ApiError) — 1 методов; ContextTooLongError(ApiError) — 0 методов; ServerError(ApiError) — 0 методов
- функции: is_local_host(host); _build_opener(url, proxy); _headers(api_key, extra_headers, accept); _socket_of(resp); _set_socket_timeout(resp, seconds); _force_close(resp); _spawn_reader(resp, q, stop); _extract_provider_message(raw_body); _parse_retry_after(value); classify_http_error(status, body, headers=None); split_sse_lines(buf); parse_sse_line(line); extract_delta(obj); error_in_event(obj); build_body(model, messages, max_tokens=None, temperature=None, stream=True, stop=None, extra_body=None); _open(url, api_key, extra_headers, proxy, payload, accept, connect_timeout, method='POST')
- константы: DEFAULT_CONNECT_TIMEOUT, DEFAULT_SILENCE_TIMEOUT, USER_AGENT, _CONTEXT_MARKERS, _DAILY_MARKERS, _LOCAL_HOSTS, _OVERLOAD_MARKERS, _POLL_INTERVAL, _READ_CHUNK

### python/api/providers.py — 72 КБ
- докстринг: Реестр провайдеров API — нейросети, доступные по ключу, а не через браузер. ПОЧЕМУ ОТДЕЛЬНО ОТ sites.py. У записи браузерного сайта есть new_chat_url, match-домены и needs_visibility_spoof — для работ…
- функции: _catalog_record(meta); catalog_records(); _stat_key(path); is_from_catalog(provider_id); get_provider(provider_id); provider_ids(); all_records(); env_map(); env_names_for(provider_id); base_url_for(provider_id, rec=None); models_url(provider_id); registry_models(provider_id); headers_for(provider_id); unavailable_reason(provider_id, rec=None); transport_for(provider_id, model=''); connect_timeout_for(provider_id)
- константы: AGENTROUTER_UNAVAILABLE, APP_TITLE, DEFAULT_PROVIDER_ID, MODELS_FRESH_SECONDS, MODELS_RETRY_SECONDS, PROVIDERS, _CATALOG_FREE_EN, _CATALOG_FREE_RU, _CATALOG_MULTI_EN, _CATALOG_MULTI_RU, _CATALOG_NOTE_EN, _CATALOG_NOTE_RU

## python/backends

### python/backends/api_backend.py — 90 КБ
- докстринг: Бэкенд работы по ключу API — сиблинг браузерного, не наследник. ЧТО ЗДЕСЬ ЕСТЬ И ЧЕГО НЕТ. Есть: сборка messages, вызов транспорта, живая трансляция в панель, разбор блока agent_action, запись истории…
- классы: ApiBackend(object) — 19 методов
- функции: pop_rate_limit_status(); pop_retry_after(); _note_rate_limit(status, retry_after=None); split_action_block(text); strip_done_marker(text); parse_action(raw_text); _parse_legacy_tool_call(raw); _guess_user_kind(prompt); usable_action(raw); _trim_overlap(head, tail); _merge_usage(base, extra); budgets_for(provider_id, model, max_tokens=None, budget_tokens=None); _note_budgets(chat_id, model, out, hist, window, src); _is_client_rejected(msg); describe_api_error(e, provider_name, model=u''); _fmt_num(n)
- константы: ACTION_PLACEHOLDER, HISTORY_CAP, HISTORY_SAVE_WARNING, HISTORY_SHARE, HISTORY_SHRINK_FACTOR, KEY_SWITCH_NOTE, LENGTH_NOTE, MAX_CONTINUATIONS, MAX_CONTINUATION_OVERLAP, MAX_HISTORY_SHRINKS, MIN_ANSWER_TOKENS, OUTPUT_CAP, OUTPUT_SHARE, PARTIAL_SHOW_LIMIT, RESCUE_NOTE, SHOW_USAGE_IN_CHAT

### python/backends/browser_backend.py — 3 КБ
- докстринг: Браузерный бэкенд — адаптер над существующими парсерами сайтов. Ничего не меняет в работе браузерного режима: просто заворачивает вызов модуля-парсера в тот же интерфейс, что у ApiBackend, чтобы main.…
- классы: BrowserBackend(object) — 5 методов

## python/browser

### python/browser/ai_studio_net.py — 10 КБ
- докстринг: Сетевой монитор Google AI Studio: читает ответ модели из СЕТИ (CDP), а не из DOM. Построен на общей базе net_monitor.BaseNetMonitor (v87.10), как KimiChatMonitor. Эндпоинт (подтверждён реальным дампом…
- классы: AiStudioChatMonitor(BaseNetMonitor) — 8 методов
- функции: _bytes_to_text_prefix(raw_bytes); _iter_model_contents(node, out); extract_parts(obj); has_finish_marker(node); _decode_chunks_from_start(text); decode_aistudio_chunks_partial(raw_bytes)

### python/browser/browser_manager.py — 12 КБ
- функции: find_chrome(); _wait_for_debug_port(port=9222, timeout=15.0); harden_background_tab(driver); setup_browser()
- константы: START_URL, VISIBILITY_SPOOF_JS

### python/browser/cdp_ws.py — 15 КБ
- докстринг: CDP (Chrome DevTools Protocol) minimal client, stdlib only. Selenium's driver.execute_cdp_cmd only does request/response CDP commands, it cannot receive push events (Network.responseReceived, Network.…
- классы: WSError(Exception) — 0 методов; MiniWebSocket() — 7 методов; CDPSession() — 7 методов
- функции: _ws_handshake(sock, host, path); _ws_mask(data); list_targets(host='127.0.0.1', port=9222, timeout=5.0); browser_ws_url(host='127.0.0.1', port=9222, timeout=5.0); find_page_ws_url(url_substr, host='127.0.0.1', port=9222, timeout=5.0); find_page_ws_url_for_host(page_host, host='127.0.0.1', port=9222, timeout=5.0); find_page_ws_url_for_target(target_id, host='127.0.0.1', port=9222, timeout=5.0); decode_connect_frames(raw_bytes); decode_connect_frames_partial(raw_bytes); encode_connect_frame(obj, flags=0)

### python/browser/live_input.py — 4 КБ
- докстринг: v88.11/v88.14: живой ввод — зеркалирование текста из панели агента в поле сайта. Пользователь печатает в панели Godot, панель с тротлингом (~0.35 с) шлёт текущий текст на POST /chat/live_input. Сервер…
- классы: LiveInputMirror(object) — 3 методов

### python/browser/net_monitor.py — 24 КБ
- докстринг: Общая сетевая логика чтения ответов нейросетей через CDP (v87.10). Выделена из kimi_parser (v87.1-v87.8), где схема «читаем ответ из СЕТИ, а не из DOM» была обкатана впервые. Здесь живёт всё, что НЕ з…
- классы: BaseNetMonitor() — 29 методов

### python/browser/qwen_net.py — 12 КБ
- докстринг: Сетевой монитор Qwen (chat.qwen.ai) — v104.1 (база v88.6). Читает ответ модели из СЕТИ (SSE-стрим), а не из DOM — как у kimi (v87.x) и AI Studio (v88.0). Формат снят с реального обмена (июль 2026): PO…
- классы: QwenChatMonitor(BaseNetMonitor) — 11 методов
- функции: decode_qwen_sse_lines(text); decode_qwen_sse_partial(raw_bytes); _looks_like_sse(raw)

### python/browser/sites.py — 10 КБ
- докстринг: Реестр сайтов-нейросетей, с которыми работает агент. Сейчас поддержаны: Google AI Studio, DeepSeek. Чтобы добавить новый: допиши запись в SITES (id, name, new_chat_url, match-домены, parser). В будуще…
- функции: _host(url); _all_sites(); list_sites(); get_site(site_id); get_parser_module(site_id=None, url=None); detect_site(url); same_site(url_a, url_b); site_name_for_url(url); needs_visibility_spoof(url=None, site_id=None); load_custom_sites(); register_custom_site(name, url, parser_profile=None)
- константы: SITES

## python/godot_tools

### python/godot_tools/answer_judge.py — 25 КБ
- докстринг: Deterministic project-aware judge for parallel model answers. The judge never writes to disk. It parses agent_action, applies write actions to an in-memory overlay, reuses the Librarian project index …
- функции: _finding(severity, category, message, path=None, step=None); _judge_structural_action(project_root, action, addon_dir, allow_addons=False, allow_self_edit=False); _read_text(project_root, path, overlay); _path_exists(project_root, path, overlay); _validate_candidate(project_root, path, text, addon_dir, planned_paths); _judge_read_action(project_root, action, addon_dir=None, allow_addons=False, allow_self_edit=False); _apply_write_action(project_root, action, overlay, addon_dir, planned_paths, step=None, allow_addons=False, allow_self_edit=False); judge_answer(project_root, full_text, addon_dir=None, allow_addons=False, allow_self_edit=False); select_best_project_answer(project_root, variants, addon_dir=None, allow_addons=False, allow_self_edit=False)
- константы: READ_ACTIONS, WRITE_ACTIONS

### python/godot_tools/arch_map.py — 22 КБ
- докстринг: arch_map.py — карта архитектуры агента: ядро и потребители. Зачем. Функциональность агента живёт в ядре (python/godot_tools), а оболочки (панель, сервер, browser, api, backends, tools) вызывают ядро. …
- функции: _glob_to_re(pattern); load_map(addon_dir); zone_for(map_data, rel_path); core_dir_of(map_data); line_policy(map_data); count_lines(text); name_checks_enabled(map_data, rel_path); public_names(text); _source_signature(addon_dir, exts); _py_signature(addon_dir); name_index(addon_dir); _join_hits(hits, limit=3); check_new_file(addon_dir, rel_path, text, map_data=None, index=None, replaced=()); check_new_files(addon_dir, items, map_data=None, replaced=()); audit(addon_dir, map_data=None)
- константы: _DEFAULT_LINE_LIMITS, _INDEX_CACHE, _MAP_CACHE, _SKIP_DIRS

### python/godot_tools/file_refactor.py — 66 КБ
- докстринг: Refactor file paths with automatic reference updates across GDScript, scenes, and project settings.
- классы: FileRefactorError(ValueError) — 0 методов; StaleFileRefactorError(RuntimeError) — 0 методов
- функции: _project_lock(project_root); _sha256(data); _normalize_godot_path(path); _is_case_only_rename(old_godot_path, new_godot_path, abs_old=None, abs_new=None); _read_file_text(abs_path); find_file_references(project_root, old_godot_path, allow_addons=False, skip_source_check=False, allow_self_edit=False, addon_dir=None); update_internal_relative_paths(text, old_godot_path, new_godot_path, project_root, moved_files_map=None); _assert_no_agent_tree_relocation(project_root, path, addon_dir); prepare_directory_relocation(project_root, old_path, new_path, update_references=True, allow_addons=False, allow_self_edit=False, addon_dir=None); prepare_file_rename(project_root, old_godot_path, new_godot_path, update_references=True, allow_addons=False, allow_self_edit=False, addon_dir=None); apply_prepared_file_rename(project_root, prepared, chat_id=None, chat_title=None, chain_id=None, allow_addons=False, allow_self_edit=False, addon_dir=None); sync_references_after_external_move(project_root, old_path, new_path, is_directory=False, allow_addons=False, chat_id=None, chat_title=None, allow_self_edit=False, addon_dir=None); _sync_references_after_external_move_impl(project_root, old_path, new_path, is_directory=False, allow_addons=False, chat_id=None, chat_title=None, allow_self_edit=False, addon_dir=None)
- константы: _LOCKS, _LOCKS_GUARD, _MAX_FILE_BYTES, _SKIP_DIRS

### python/godot_tools/function_card.py — 37 КБ
- докстринг: Глубокая карточка функции (docs/function_card_plan.md, S2–S3). Продолжение карточки символа L7 (librarian.py::_symbol_card): обычная карточка даёт объявление и все ссылки; глубокая карточка отвечает н…
- функции: _cap(items, limit); _uid_map(project_root); _autoload_map(project_root); _own_decl_kinds(); _class_of(entries, rel); _collect(project_root, res_path, func_name, content, addon_dir=None); subclass_count(project_root, res_path); _collect_relations(project_root, res_path, func_name, data); _class_decl_in_text(text); _engine_class_probe(project_root, cls_name, addon_dir); _inherits_chain(project_root, res_path, func_name, data); _tail(count); _format(func_name, res_path, data); build_function_card(project_root, res_path, func_name, content=None, addon_dir=None)
- константы: CARD_MAX_AUTOLOADS, CARD_MAX_CALL_FILES, CARD_MAX_CALL_LINES_PER_FILE, CARD_MAX_CONSTS, CARD_MAX_DYNAMIC, CARD_MAX_EXTERNAL, CARD_MAX_INHERITS, CARD_MAX_LOCALS, CARD_MAX_MEMBERS, CARD_MAX_OVERRIDES, CARD_MAX_PARAMS, CARD_MAX_PROVEN_FUNCS, CARD_MAX_SIGNALS, CARD_MAX_STRING_HITS, CARD_MAX_SUBCLASSES, _AUTOLOAD_RE

### python/godot_tools/gather_context.py — 17 КБ
- докстринг: Bounded, read-only context bundle for one model follow-up.
- функции: _clean_text(value, limit); _bool(value, default=False); validate_request(action); _allowed_path(project_root, path, allow_addons=False, allow_self_edit=False, addon_dir=None); _read_script(project_root, path); _candidate_scripts(project_root, function_name, allow_addons, allow_self_edit=False, addon_dir=None); _resolve_symbol(project_root, request, allow_addons=False, allow_self_edit=False, addon_dir=None); _project_settings(project_root, query, allow_addons=False, allow_self_edit=False, addon_dir=None); _api_sections(project_root, classes, addon_dir); _diagnostics(project_root, paths, addon_dir, dirty_path); _references(project_root, paths, allow_addons, allow_self_edit=False, addon_dir=None); gather(project_root, action, editor_snapshot=None, addon_dir=None, allow_addons=False, allow_self_edit=False); _fit_block(title, body, remaining); format_result(result, max_chars=None)
- константы: DEFAULT_MAX_CHARS, HARD_MAX_CHARS, MAX_API_CLASSES, MAX_SYMBOLS, MIN_MAX_CHARS, _AUTOLOAD_RE, _CLASS_NAME_RE, _CLASS_RE

### python/godot_tools/gd_api_cache.py — 11 КБ
- докстринг: Кэш реального API Godot (из ClassDB), присланный из редактора кнопкой «Обновить справочник API Godot». Без этого кэша проверка в gd_api_check просто ничего не делает (никаких ложных срабатываний — это…
- функции: _migrate_legacy_addon_cache(addon_dir); _cache_path(project_root); save_cache(project_root, classes, godot_version='', addon_dir=None); _load_if_needed(project_root, addon_dir=None); get_cached_version(project_root, addon_dir=None); has_cache(project_root, addon_dir=None); get_class(project_root, class_name, addon_dir=None); resolve_chain(project_root, class_name, max_depth=30, addon_dir=None); collect_members(project_root, class_name, addon_dir=None); collect_signatures(project_root, class_name, addon_dir=None)
- константы: CACHE_FILENAME, DEFAULT_CACHE_FILENAME, DEFAULT_CACHE_SUBDIR

### python/godot_tools/gd_api_check.py — 9 КБ
- докстринг: Проверка кода .gd против реального API Godot (кэш ClassDB из gd_api_cache), а НЕ по памяти обучения модели. Ловит: - self.<xxx>() / self.<xxx> — такого метода/свойства нет ни у базового класса, ни в с…
- функции: _mask(text, mask_strings, mask_comments); _local_symbols(masked_full); _find_matching_paren(text, open_idx); _count_top_level_args(masked_text, open_idx, close_idx); check_api_usage(project_root, text, path='', addon_dir=None)
- константы: MAX_PROBLEMS, _CONNECT_BARE_RE, _CONNECT_SELF_RE, _ENUM_BLOCK_RE, _EXTENDS_RE, _FIELD_DEF_RE, _FUNC_DEF_RE, _SELF_CALL_RE, _SIGNAL_DEF_RE

### python/godot_tools/gd_functions.py — 3 КБ
- докстринг: v48: точечное чтение функций из GDScript-файлов (action=read_function). Вместо полного файла модель может запросить только нужные функции — это экономит токены и лимит файлов за запрос. Разбор индента…
- функции: _indent_width(line); list_functions(text); extract_functions(text, names)
- константы: _FUNC_RE

### python/godot_tools/gd_lint.py — 9 КБ
- докстринг: Лёгкая самопроверка GDScript: ловим явный синтаксический мусор (незакрытые скобки/кавычки, битые отступы, пропущенные двоеточия) ДО показа действия пользователю. Модель получает список проблем и чинит…
- функции: _literal_kind(rhs); lint_gdscript(text)
- константы: MAX_ERRORS, _ARRAY_LIT_RE, _BOOL_LIT_RE, _CLASS_RE, _DICT_LIT_RE, _FLOAT_LIT_RE, _FUNC_RE, _INT_LIT_RE, _LIT_RU, _PAIRS, _STR_LIT_RE, _TYPE_ALLOWED_LITERALS, _TYPE_RU, _VAR_TYPED_RE

### python/godot_tools/gd_semantic_parser.py — 15 КБ
- докстринг: Conservative GDScript lexical facts with exact source ranges.
- функции: _is_ident_start(char); _is_ident_continue(char); tokenize(text); _line_indents(text); _next_identifier(tokens, index, stop_values=()); _declaration(kind, token, owner, path, extra=None); _check_export_annotation(tokens, pos); _inside_brackets(tokens, pos); _parse_enum(tokens, pos, path, owner, declarations, declaration_positions, token_owners); parse(text, path='')
- константы: _DECL_KEYWORDS, _IDENT_CONT_RE, _IDENT_START_RE, _MODIFIERS

### python/godot_tools/godot_headless_validation.py — 21 КБ
- докстринг: Validate staged project changes with Godot in isolated project copies. The existing text linters remain the first barrier. This module adds an independent engine barrier and never writes to the real p…
- классы: HeadlessValidationError(RuntimeError) — 0 методов; StaleValidationError(HeadlessValidationError) — 0 методов
- функции: _sha256(data); _file_hash(path); _canonical_rel(path); _action_candidate(project_root, action); batch_from_action(project_root, action); batch_from_rename(project_root, prepared); _referencer_targets(project_root, changed_paths, excluded=()); make_batch(action_kind, operations, targets, source_hashes, required_targets=()); discover_executable(explicit=None); _copy_project(source, destination); _overlay_path(root, res_path); _apply_operations(root, operations); _harness_source(harness_path=None); _write_manifest(root, targets, harness_path=None); _sandbox_env(base); _normalize_message(message)
- константы: DEFAULT_TIMEOUT, MAX_OUTPUT_CHARS, RESOURCE_EXTENSIONS, SCHEMA_VERSION, _COPY_EXCLUDED, _DIAGNOSTIC_RE

### python/godot_tools/high_level_actions.py — 9 КБ
- докстринг: Compile typed high-level commands into existing validated primitives.
- классы: HighLevelActionError(ValueError) — 0 методов
- функции: _exact_fields(value, required, optional=()); _text(value, field, limit=500); _summary(action); _component_path(parent, name); _compile_scene_component(command, summary); _compile_input_action(command, summary); _compile_autoload(command, summary); _compile_rename(command, _summary); _compile_atomic_files(command, summary); compile_action(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None)
- константы: _COMPILERS

### python/godot_tools/history_manager.py — 48 КБ
- функции: _journal_transaction(function); new_chain_id(); set_storage_dir(base_dir); get_storage_dir(project_root); migrate_from_project(project_root); _history_dir(project_root); _journal_path(project_root); _load_journal(project_root); _save_journal(project_root, journal); _file_hash(abs_path); _prune(project_root, journal); forget_chat(project_root, chat_id); record_change(project_root, action, chat_id=None, chat_title=None, chain_id=None); record_batch_change(project_root, action_type, paths, chat_id=None, chat_title=None, states=None, chain_id=None); commit_change(project_root, entry_id); abort_change(project_root, entry_id)
- константы: HISTORY_DIR_NAME, MAX_DIFF_CHARS, MAX_ENTRIES, _JOURNAL_LOCKS, _JOURNAL_LOCKS_GUARD, _STORAGE_OVERRIDE

### python/godot_tools/librarian.py — 94 КБ
- докстринг: v105: «Библиотекарь» (action=ask_librarian) — единая точка выдачи данных о проекте для модели. Выполняется АВТОМАТИЧЕСКИ, без подтверждения пользователем: исходные файлы проекта не меняются; локальный…
- функции: _signal_label(code, fallback); _is_section_header(line); _synonyms(token); _expanded_query(q); _frag_rank(path); _phrase_key(query); _symbol_name(sym); _phrase_rank(symbols, pk, pk_flat); _path_join_keys(query); _rerank_hits(hits, query, syn_used); _near_tokens(project_root, query, limit=6); _is_addon_rel(path); _query_tokens(query); _query_subtokens(query); _gd_signatures(project_root, godot_path, limit=SIG_PER_FILE); _scene_summary(project_root, godot_path)
- константы: API_CLASSES, API_MEMBERS, AUTOLOAD_LIMIT, CALLERS_FUNCS, CALLERS_LIMIT, CARD_MAX_DECLS, CARD_MAX_LOCALS, CARD_MAX_PARAMS, CARD_MAX_REFS, CARD_MAX_USES, CHAR_BUDGET, FOOTER, FRAGMENT_LIMIT, FRAGMENT_TOKENS, FRAG_PER_FILE, FRAG_POOL

### python/godot_tools/node_refactor.py — 46 КБ
- докстринг: Refactor scene node names with automatic reference updates across .tscn and attached GDScripts.
- классы: NodeRefactorError(ValueError) — 0 методов; StaleNodeRefactorError(RuntimeError) — 0 методов
- функции: _project_lock(project_root); _sha256(data); _read_file_text(abs_path); _normalize_scene_path(project_root, path, allow_addons=False, allow_self_edit=False, addon_dir=None); _normalize_node_name(name); parse_tscn_structure(tscn_text); _rel_path_between(from_node, to_node); find_node_in_scene(nodes, target_spec); prepare_node_rename(project_root, scene_godot_path, target_spec, new_name, update_scripts=True, allow_addons=False, allow_self_edit=False, addon_dir=None, scripts_only=False, previous_name=''); prepare_node_reparent(project_root, scene_godot_path, target_spec, new_parent_spec, update_scripts=True, allow_addons=False, allow_self_edit=False, addon_dir=None); prepare_node_deletion(project_root, scene_godot_path, target_spec, cleanup_code=True, allow_addons=False, allow_self_edit=False, addon_dir=None); apply_prepared_node_refactor(project_root, prepared, chat_id=None, chat_title=None, allow_addons=False, allow_self_edit=False, addon_dir=None)
- константы: _LOCKS, _LOCKS_GUARD, _NODE_NAME_RE

### python/godot_tools/project_settings_actions.py — 13 КБ
- докстринг: Strict schema for project settings changes executed by Godot itself.
- классы: ProjectSettingsActionError(ValueError) — 0 методов
- функции: _exact_fields(value, required, optional=()); _text(value, field, limit=240); _project_path(project_root, value, field, extensions, allow_addons=False, allow_self_edit=False, addon_dir=None); _normalize_event(raw); _normalize_operation(project_root, raw, allow_addons, allow_self_edit=False, addon_dir=None); _validate_sequence(operations); normalize_action(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None); canonical_digest(action); file_sha256(absolute); prepare(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None); public_prepared(prepared)
- константы: MAX_OPERATIONS, _IDENTIFIER_RE, _KEY_RE, _LAYERS, _NAME_RE, _STRETCH_ASPECTS, _STRETCH_MODES, _WINDOW_MODES

### python/godot_tools/project_tools.py — 100 КБ
- классы: MoveRecoveryError(RuntimeError) — 0 методов; CaseOnlyDirCasingTransaction() — 6 методов; _PathOutsideError(ValueError) — 0 методов; _ScanPolicyContext() — 7 методов
- функции: begin_case_only_dir_casing(project_root, src_rel, dst_rel); _is_generated_sidecar(path); exclude_agent_addon_dirs(addon_dir); build_project_tree(project_root, max_depth=8, only_exts=None, max_entries=None, subdir=None, allow_addons=False, allow_self_edit=False, addon_dir=None); _resolve_safe_path(project_root, godot_path); is_addon_path(path, project_root=None); _resolved_project_path(project_root, godot_path); _validated_agent_addon_dir(project_root, addon_dir); validate_agent_addon_dir(project_root, addon_dir); is_agent_path(path, project_root, addon_dir=None); _classification_skeleton(original); _classify_resolved(original, absolute, canonical, root, project_file_identity, agent_dir_identity, agent_root_valid, addon_dir, agent_error=None, rel=None); classify_project_path(path, project_root, addon_dir=None); _path_access_allowed(classification, access, allow_addons, allow_self_edit); can_read_project_path(path, project_root, allow_addons=False, allow_self_edit=False, addon_dir=None); can_write_project_path(path, project_root, allow_addons=False, allow_self_edit=False, addon_dir=None)
- константы: AGENT_ONLY_SEARCH_EXTS, ASSET_EXTS, DIFF_PREVIEW_MAX_LINES, EXCLUDED_DIRS, EXCLUDED_FILES, HASH_MAX_BYTES, HISTORY_DIR_NAME, SEARCH_EXTS, SNIPPET_LINE_MAX, STANDARD_ARCHITECTURE_DIRS, _LINK_FALLBACK_ERRNOS, _LINK_FALLBACK_WINERRORS, _POLICY_CONTROLLED_EXCLUDES, _UNKNOWN_REL

### python/godot_tools/resource_actions.py — 19 КБ
- докстринг: Strict schema and private state for structural edits of existing .tres files.
- классы: ResourceActionError(ValueError) — 0 методов
- функции: _exact(value, required, optional=()); _text(value, field, limit=500, allow_empty=False); _number(value, field, minimum=None, maximum=None, positive=False); _path(project_root, value, field, extensions=None, allow_addons=False, allow_self_edit=False, addon_dir=None); _target(value); _tagged(project_root, value, allow_addons=False, depth=0, counter=None, allow_self_edit=False, addon_dir=None); _normalize_operation(project_root, raw, allow_addons=False, subresource_counter=None, allow_self_edit=False, addon_dir=None); normalize_action(project_root, action, allow_addons=False, require_exists=True, allow_self_edit=False, addon_dir=None); _operation_dependencies(value); canonical_digest(action); file_sha256(absolute); prepare(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None); public_prepared(prepared); operation_summary(action)
- константы: MAX_OPERATIONS, _CLASS_RE, _INTERPOLATION, _MEMBER_RE, _THEME_TYPES, _THEME_VALUE_TYPES, _UPDATE_MODES

### python/godot_tools/runtime_checks.py — 20 КБ
- докстринг: Strict deterministic game-check protocol; no arbitrary runtime RPC.
- классы: RuntimeCheckError(ValueError) — 0 методов
- функции: _exact(value, allowed, name); _text(value, name, limit, allow_empty=False); _node_path(value); _property_name(value); _number(value, name); _expected(value); _scene_path(project_root, value, allow_addons, allow_self_edit=False, addon_dir=None); normalize_action(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None); _log_path(user_data_dir); capture_log_cursor(user_data_dir); collect_log_errors(cursor); log_source_available(cursor); create_request(action, chat_id, turn_id, project_root, user_data_dir=None); public_request(pending); game_request(pending); normalize_result(value)
- константы: MAX_ASSERTIONS, MAX_HTTP_BODY_BYTES, MAX_INPUT_STEPS, MAX_LOG_DELTA_BYTES, MAX_RESULT_BYTES, MAX_STEPS, MAX_WAIT_FRAMES, MAX_WAIT_MS, OPERATORS, PROTOCOL, RESULT_STATUSES, SAFE_TYPES

### python/godot_tools/runtime_debug.py — 12 КБ
- докстринг: Bounded, read-only runtime debugger protocol shared by Flask routes/tests.
- классы: RuntimeDebugError(ValueError) — 0 методов
- функции: _text(value, name, limit, allow_empty=False); _node_path(value); normalize_status(value); status_prompt(status); attach_status(prompt, status); strip_status(prompt); normalize_action(action); select_session(status, session_id=None); create_request(action, status, chat_id, turn_id, timeout_ms=3000); public_request(pending); runtime_request(pending); _bounded_value(value, depth=0); normalize_snapshot(value); validate_snapshot_request(snapshot, pending); format_snapshot(snapshot)
- константы: MAX_HTTP_BODY_BYTES, MAX_REPORT_CHARS, MAX_SNAPSHOT_BYTES, PROTOCOL, RESULT_STATUSES, SECTIONS

### python/godot_tools/scene_actions.py — 17 КБ
- докстринг: Validation and private server state for structural Godot scene edits. The module deliberately does not parse or rewrite .tscn. Godot validates and executes the normalized operation list through agent_…
- классы: SceneActionError(ValueError) — 0 методов
- функции: _exact_fields(value, required, optional=()); _text(value, field, limit=240); normalize_node_path(value, field='node'); _normalize_scene_path(project_root, value, allow_addons=False, must_exist=True, allow_self_edit=False, addon_dir=None); _normalize_script(project_root, value, allow_addons=False, allow_self_edit=False, addon_dir=None); normalize_variant(value); _normalize_operation(raw); _join(parent, name); _validate_sequence(operations); normalize_action(project_root, action, allow_addons=False, require_target_state=True, allow_self_edit=False, addon_dir=None); canonical_digest(action); file_sha256(absolute); staged_scene_path(absolute, action_id); materialize_staged_scene(absolute, action_id, expected_hash); discard_staged_scene(absolute, action_id); prepare(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None)
- константы: MAX_OPERATIONS, _CLASS_RE, _MEMBER_RE, _NODE_NAME_RE, _SCALAR_TYPES, _VARIANT_ARITY

### python/godot_tools/scene_deps.py — 19 КБ
- докстринг: Анализ зависимостей «скрипт <-> сцена» (v47). Задача: найти в скриптах обработчики сигналов вида `_on_...`, которые НИГДЕ не подключены (ни через [connection] в сценах, ни через connect() в коде), и е…
- функции: to_snake(name); _parse_attrs(head); _attr_id(raw); parse_scene(text); extract_handlers(script_text); _res_to_abs(project_root, res_path); _collect_project_files(project_root); _method_connected_in_code(method, gd_texts); _method_connected_in_scenes(method, scene_texts, exclude_abs=None); _collect_custom_signals(gd_texts); _find_candidates(handler, nodes, script_node); analyze_scene_action(scene_text, scene_res_path, project_root); analyze_script_action(script_text, script_res_path, project_root)
- константы: KNOWN_SIGNALS, _AREAS, _ATTR_RE, _BUTTONS, _CUSTOM_SIGNAL_RE, _HANDLER_RE, _MAX_FILE_BYTES, _RIGID, _SKIP_DIRS

### python/godot_tools/split_gd.py — 62 КБ
- докстринг: split_gd.py — «пила» для .gd-скриптов Godot: вынос методов донора в модули. Зачем. Панель (agent_panel.gd, 5597 строк) и другие крупные .gd-скрипты превышают лимит строк карты архитектуры (docs/archit…
- классы: SplitGdError(ValueError) — 0 методов; StaleSplitGdError(RuntimeError) — 0 методов
- функции: _norm(rel_path); _read_text(abs_path); _newline_of(text); _write_text(abs_path, text, newline='\n'); _replace_text(abs_path, text, newline='\n'); _sha256(text); _files_of(addon_dir); _project_root_of(addon_dir); _camel(name); tokenize(text); _prev_token(tokens, index); _parse_params(sig_text); _collect_locals(tokens); _indent_width(line); _code_skeleton(text); _balance(text)
- константы: SCHEMA, _DEFAULT_TARGET_LINES, _ENGINE_VIRTUALS, _FALLBACK_METHODS, _FALLBACK_PROPS, _FUNC_RE, _KEYWORDS, _LINE_MAX, _LINE_WARN, _MAX_OCCURRENCES, _MAX_SCAN_FILE_BYTES, _MEMBER_RE, _PANEL_PARAM, _SCAN_EXTS, _SCAN_SKIP_DIRS, _TWO_CHAR

### python/godot_tools/split_refactor.py — 43 КБ
- докстринг: split_refactor.py — «пила» для .py-модулей: ссылки, план разбиения, фасад. Зачем. Гейт (arch_map.check_new_file) отклоняет НОВЫЙ файл сверх лимита строк и советует «раздели функциональность на модули …
- классы: SplitError(ValueError) — 0 методов; StaleSplitError(RuntimeError) — 0 методов
- функции: _norm(rel_path); _read_text(abs_path); _write_text(abs_path, text); _replace_text(abs_path, text); _sha256(text); _files_of(addon_dir); _imported_modules(line); _module_matches(candidate, stem); scan_refs(addon_dir, rel_path); _warn_patched_attributes(scan, prepared, warnings); _segment_text(lines, start, end); _expand_comments(lines, next_lineno); _import_bindings(node); _other_item(lines, node, name); file_inventory(text); _used_names(node)
- константы: SCHEMA, _CODING_RE, _DEFAULT_TARGET_LINES, _IMPORT_RE, _MAX_OCCURRENCES, _MAX_SCAN_FILE_BYTES, _SCAN_EXTS, _SCAN_SKIP_DIRS

### python/godot_tools/symbol_refactor.py — 4 КБ
- докстринг: Conservative, hash-guarded GDScript symbol renames.
- функции: public_prepared(prepared); prepared_diffs(prepared)

### python/godot_tools/symbol_refactor_data.py — 1 КБ
- докстринг: symbol_refactor_data — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor). Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
- константы: _DECL_KINDS, _KEYWORDS

### python/godot_tools/symbol_refactor_part1.py — 42 КБ
- докстринг: symbol_refactor_part1 — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor). Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
- классы: RenameError(ValueError) — 1 методов; LocatorError(RenameError) — 0 методов; UnsafeRenameError(RenameError) — 0 методов; UnsupportedRenameError(RenameError) — 0 методов; StaleRenameError(RuntimeError) — 0 методов
- функции: _owner_is_top_level(owner, declarations); _owner_within(owner, root, declarations); _owner_is_script_scope(declaration, declarations); _reference_in_other_scope(fact, declaration, kind, declarations); _decl_kind(kind); _project_lock(project_root); _sha256(data); _collect_path_reference_edits(project_root, file_rename, allow_addons=False, allow_self_edit=False, addon_dir=None); _read_source(project_root, path); _parse_locator(value); _move_with_uid(project_root, file_rename, moved); _plan_file_rename(project_root, target_path, new_name, addon_dir); _unverified_reason(kind, fact, text, tokens, target_path, path, target_class, typed, declarations, subclasses, all_target_classes, root_owner); _validate_action(action); _token_neighbors(tokens, start); _typed_receivers(text)
- константы: KINDS, MODES, _CONN_FIELD_RE, _CONN_HEADER_RE, _DECL_TO_KIND, _IDENTIFIER, _KIND_TO_DECL, _LOCKS, _LOCKS_GUARD, _MAX_SOURCE_CHARS

### python/godot_tools/symbol_refactor_part2.py — 42 КБ
- докстринг: symbol_refactor_part2 — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor). Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
- функции: _reference_is_safe(kind, fact, text, tokens, target_path, path, target_class, typed, declarations, target_static=False, subclasses=None, all_target_classes=None, target_enum_name=None, root_owner=None, root_declarations=None); _collision(declarations, declaration, kind, new_name, subclasses=None); _is_real_conflict(collided, declaration, kind, subclasses=None); _project_global_names(project_root); _engine_class_name(project_root, name, addon_dir=None); _unwritable_subclass_overrides(project_root, target_path, target_class, snapshot, kind, old_name, allow_addons=False, allow_self_edit=False, addon_dir=None); _classify_string_reference(text, tokens, start, end); _classify_string_reference_kind(text, tokens, start, end); _assert_hierarchy_renamed(kind, old_name, new_name, hierarchy_paths, covered, declarations, owner=None); _add_allowed_addon_semantics(snapshot, project_root, allow_addons, allow_self_edit, addon_dir); _exclude_place_kind(entry); _exclude_entry(entry); exclude_place(entry); _excluded_places(excluded); _usage_excluded(excluded, path, line); _usage_query(action)
- константы: _CLASS_NAME_STRING_CALLS, _DYNAMIC_STRING_CALLS, _USAGE_KINDS

### python/godot_tools/symbol_refactor_part3.py — 48 КБ
- докстринг: symbol_refactor_part3 — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor). Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
- функции: prepare_rename(project_root, action, allow_addons=False, addon_dir=None, allow_self_edit=False); _count_renamed(files, target_path, declaration_start); apply_prepared_rename(project_root, prepared, chat_id=None, chat_title=None)

### python/godot_tools/transaction_actions.py — 19 КБ
- докстринг: Prepare and atomically apply deterministic multi-file transactions.
- классы: TransactionError(RuntimeError) — 0 методов; StaleTransactionError(TransactionError) — 0 методов
- функции: _lock(project_root); _hash(data); _text_equivalent(left, right); _read(path); _canonical(project_root, value, allow_addons, allow_self_edit=False, addon_dir=None); _exact(obj, allowed, label); normalize_action(project_root, action, allow_addons=False, allow_self_edit=False, addon_dir=None); _entry(project_root, overlay, path); _validate_script(project_root, path, data, addon_dir); prepare(project_root, action, allow_addons=False, addon_dir=None, allow_self_edit=False); attach_validation(prepared, receipt); public_prepared(prepared); prepared_diffs(prepared); verify_prepared(project_root, prepared); _restore(project_root, files); apply_prepared(project_root, prepared, chat_id=None, chat_title=None)
- константы: MAX_CHECKS, MAX_OPERATIONS, _ALLOWED, _LOCKS, _LOCKS_GUARD

### python/godot_tools/tscn_lint.py — 72 КБ
- докстринг: Структурная проверка .tscn до показа действия пользователю. Аналог gd_lint/gd_api_check, но для сцен: ловит битые ссылки на ресурсы (ExtResource/SubResource без объявления), недостижимые parent-пути, …
- функции: _reorder_resource_sections(text); _strip_invalid_uids(text); _attrs(head); is_scene_path(path); _reorder_nodes_for_parent_order(text); _fix_single_candidate_refs(text, ext_ids, sub_ids); _convert_ctor_values(text, problems); _toposort_sub_resources(text); _scene_node_paths(disk_path); _value_looks_parseable(value); _scan_property_syntax(text); _check_connections_and_parents(text); _scan_value_balance(text); _scan_scene_semantics(text); _scan_scene_semantics_v83(text); _find_resource_cycles(text)
- константы: _ANY_SECTION_RE, _ATTR_RE, _BAD_NAME_CHARS_V83, _BRACKET_CLOSE, _BRACKET_OPEN, _CHUNK_TYPE_RANK, _CLOSING_TAG_RE, _COLLISION_OWNER_2D, _COLLISION_OWNER_3D, _COLLISION_SHAPE_2D, _COLLISION_SHAPE_3D, _CONNECTION_RE, _CTOR_ARGS_RE, _CTOR_LINE_RE, _CTOR_VALUE_RE, _DOTTED_PROP_RE

## python/minilich

### python/minilich/__init__.py — 14 КБ
- докстринг: mini-lich — крошечная локальная нейросеть-помощник (написана с нуля на numpy). Узкая специализация (нейросеть-поддержка, не главный программист): 1) починка неправильно собранных .tscn сцен без обраще…
- функции: _settings_path(project_root); _load_settings(project_root); is_enabled(project_root); set_enabled(project_root, enabled); is_training_mode(project_root); set_training_mode(project_root, training); set_train_pause(project_root, seconds); get_brain(project_root); github_fetch_async(project_root, addon_dir, repos_text); _dir_size(path); status(project_root, addon_dir=None); note_scene_bad(path, candidate, problems); note_scene_ok(project_root, path, candidate); try_fix_scene(scene_text, problems, project_root, addon_dir=None); search_project(project_root, query, limit=8); describe_for_prompt(project_root, query, limit=6)
- константы: BRAIN_PROFILES, SETTINGS_FILE, _MAX_PENDING

### python/minilich/ml_data.py — 32 КБ
- докстринг: Датасет mini-lich: хранение обучающих пар + дедупликация + синтетика. Каждая пара: (сломанная сцена + список проблем от линтера) -> (исправленная сцена). Источники пар: - "live" — реальные исправления…
- функции: set_storage_base(addon_dir, project_root=None); storage_dir(project_root); _dataset_path(project_root); _manifest_path(project_root); _load_manifest(project_root); _save_manifest(project_root, manifest); pair_hash(broken, fixed); record_pair(project_root, broken, problems, fixed, source='live'); _is_protected_ref_line(line); _enforce_limits(project_root); _read_lines(path); load_pairs(project_root, limit=None); dataset_stats(project_root); _reference_dir(project_root); _reference_scene_path(project_root, name); load_reference_scene(project_root, name)
- константы: DATASET_FILE, MANIFEST_FILE, MAX_DATASET_BYTES, MAX_EXAMPLES, MAX_SCENE_CHARS, REFERENCE_EXAM_FILE, REFERENCE_LOG_FILE, REFERENCE_LOG_MAX_PER_KEY, REFERENCE_SCENES, REFERENCE_SUBDIR, REFERENCE_TARGETS, STORAGE_SUBDIR, _BASE_OVERRIDE, _EXT_PACKED_RE, _MESH_SUB_RE, _NODE_RE

### python/minilich/ml_fix.py — 21 КБ
- докстринг: Починка сцен mini-lich: рефлекторный слой + нейрослой + обязательная проверка линтером. Архитектура «как у взрослых», только маленькая: 1) Рефлекторный слой — детерминированные шаблонные починки извес…
- функции: _existing_node_names(scene); classify_problem(problems); think_plan_text(problems); _split_blocks(scene); _block_info(block); _focus_names(problems); _referenced_ids(text); trim_scene_for_context(scene, problems, tok, max_ids); trim_pair_for_context(broken, problems, fixed, max_ids); splice_fixed_fragment(original_scene, kept_keys, fixed_fragment); _fix_unused_packed_scene(scene, problem); _fix_duplicate_node(scene, problem); _fix_dotted_property(scene, problem); reflex_fix(scene_text, problems); build_prompt_ids(broken, problems); build_training_ids(broken, problems, fixed)
- константы: MAX_GEN_TOKENS, _ATTR_RE, _BLOCK_HDR_RE, _DOTTED_RE, _DUP_NODE_RE, _NODE_HDR_RE, _RES_REF_RE, _SUBRES_ASSIGN_TPL, _TOK, _UNUSED_EXT_RE

### python/minilich/ml_github.py — 8 КБ
- докстринг: v77/v81: дообучение mini-lich на сценах с GitHub. v81: запуск кнопкой из панели; пользователь сам указывает ссылки на репозитории; берём ТОЛЬКО сцены Godot 4 (format=3, без классов Godot 3); виды порч…
- функции: _parse_repo_spec(spec); parse_repos_text(text); _acceptable_scene(scene); _api_get_json(url, github_token=None); _default_branch(repo, github_token=None); _list_tscn_files(repo, branch='master', github_token=None, limit=200); _fetch_raw(repo, branch, path); _corruptions(); fetch_and_add_examples(project_root, addon_dir=None, repos=None, repos_text=None, branch=None, max_files=15, github_token=None, log=None)
- константы: API_TIMEOUT_SEC, DEFAULT_REPOS, USER_AGENT, _FORMAT3_RE, _GD3_MARKERS

### python/minilich/ml_model.py — 15 КБ
- докстринг: Крошечный трансформер mini-lich на чистом numpy (без PyTorch/llama.cpp). Архитектура — decoder-only, та же семья, что у больших LLM, только на порядки меньше: эмбеддинги -> N блоков (LayerNorm -> прич…
- классы: TinyTransformer() — 8 методов
- функции: default_config(vocab); _ln_forward(x, g, b, eps=1e-05); _ln_backward(dy, cache)

### python/minilich/ml_project_index.py — 63 КБ
- докстринг: Индекс структуры проекта пользователя для mini-lich и Библиотекаря (v105). Задача: какой бы проект ни был, агент быстро понимает его структуру (файлы, узлы сцен, функции скриптов) и помогает искать ин…
- функции: _nested_symbols(text); _ext_priority(rel); _cap_symbols(symbols, limit=MAX_SYMBOLS); _project_lock(project_root); _cache_key(project_root); _index_stamp(path); _cache_store(project_root, data); _sem_cache_store(project_root, data); _index_path(project_root); _semantic_index_path(project_root); _file_stamp(full); _reuse_or_build(root, rel, prev); _build_entry(root, rel); _save(project_root, data); _read_semantic_index(project_root); _read_semantic_index_raw(project_root)
- константы: EXTS, INDEX_FILE, MAX_FILES, MAX_SYMBOLS, SEMANTIC_INDEX_FILE, SKIP_DIRS, STALE_SEC, _CAMEL_RE, _CLASS_RE, _CONST_RE, _EXT_PRIORITY, _FUNC_RE, _KIND_RANK, _MEM_CACHE, _NESTED_CLASS_RE, _NESTED_CONST_RE

### python/minilich/ml_tokenizer.py — 5 КБ
- докстринг: Токенизатор mini-lich: крошечный фиксированный словарь под синтаксис .tscn. Никакого обучения словаря не требуется: словарь собран заранее — служебные токены, частые ключевые слова формата .tscn и бай…
- классы: MiniLichTokenizer() — 6 методов
- константы: KEYWORDS, SPECIALS

### python/minilich/ml_train.py — 56 КБ
- докстринг: Обучение mini-lich: фоновый тренер + атомарные чекпоинты. Защита от отключения ПК: - чекпоинт пишется во временный файл и атомарно переименовывается; - хранятся ПОСЛЕДНИЕ 3 чекпоинта (если самый свежи…
- функции: _log(msg); _brain_profile(project_root); _brain_profile_config(project_root); ckpt_dir(project_root); _ckpt_list(project_root); _backup_dir(project_root); _rescue_checkpoints(project_root); _archive_mismatched_ckpts(project_root, want_cfg); load_latest_model(project_root); _save_ckpt(project_root, model); _stats_path(project_root); _load_example_stats(project_root); _save_example_stats(project_root, stats); _example_category(problems); _build_sampling_buckets(hashes, categories, stats); _pick_weighted_index(rng, fail_idx, rare_idx, easy_idx, n)
- константы: ADAM_CLIP_NORM, ADAM_WEIGHT_DECAY, BACKUP_EVERY_STEPS, BEST_CKPT_FILE, BEST_CKPT_NAME, BURST_PAUSE_SEC, BURST_STEPS, CKPT_EVERY_STEPS, CKPT_KEEP, EXAMPLE_STATS_FILE, EXAM_EVERY_BURSTS, EXAM_EXAMPLES, EXAM_GREAT_SIM, EXAM_PER_CATEGORY, HEARTBEAT_CHECK_SEC, HEARTBEAT_SILENCE_SEC

## python/parsers

### python/parsers/ai_parser.py — 36 КБ
- классы: _DeliveryUncertainError(RuntimeError) — 0 методов; AiStudioParser(BaseSiteParser) — 17 методов
- функции: get_model_turn_count(driver); is_generating(driver); get_last_model_text_length(driver); get_answer_text_length(driver); get_answer_preview(driver); get_live_activity(driver); get_answer_stream(driver); _extract_last_answer_once(driver); extract_last_answer(driver); _strip_turn_chrome(text: str); extract_last_answer_robust(driver, retries=3, delay=1.5); wait_for_new_answer(driver, initial_model_count, timeout=900, quiet_period=2.5, hard_quiet_period=45.0, poll_interval=0.25, post_quiet_grace=6.0, progress_cb=None); send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None)
- константы: JS_COUNT_MODEL_TURNS, JS_EXTRACT_LAST_ANSWER, JS_EXTRACT_RAW_FALLBACK, JS_GET_ANSWER_PREVIEW, JS_GET_ANSWER_STREAM, JS_GET_ANSWER_TEXT_LENGTH, JS_GET_LAST_MODEL_TEXT_LENGTH, JS_GET_LIVE_ACTIVITY, JS_IS_GENERATING, PARSER, _CHROME_SELECTORS, _JS_FIND_INPUT, _JS_INSERT, _JS_IS_THOUGHT, _JS_USER_TURN_COUNT, _THOUGHT_SELECTORS

### python/parsers/arena_parser.py — 56 КБ
- докстринг: Arena AI parser: trusted input and network-only answer reading.
- классы: ArenaChatMonitor(BaseNetMonitor) — 29 методов; ArenaParser(BaseSiteParser) — 34 методов
- функции: decode_arena_stream_lines(text); decode_arena_stream_partial(raw_bytes); send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None)
- константы: PARSER

### python/parsers/deepseek_parser.py — 15 КБ
- докстринг: Парсер сайта DeepSeek (chat.deepseek.com). Наследник общего менеджера парсинга (parser_base.BaseSiteParser). Интерфейс модуля тот же, что у ai_parser (Google AI Studio): send_message_and_get_response(…
- классы: _DeliveryUncertainError(RuntimeError) — 0 методов; DeepSeekParser(BaseSiteParser) — 14 методов
- функции: count_answers(driver); answer_len(driver); answer_preview(driver); answer_stream(driver); is_generating(driver); _extract_answer_once(driver); extract_answer(driver); wait_for_new_answer(driver, initial_count, timeout=900, quiet_period=4.0, hard_quiet_period=45.0, poll_interval=0.3, post_quiet_grace=6.0, progress_cb=None); send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None)
- константы: ANSWER_SEL, JS_ANSWER_LEN, JS_ANSWER_PREVIEW, JS_ANSWER_STREAM, JS_COUNT_ANSWERS, JS_EXTRACT, JS_FIND_INPUT, JS_IS_GENERATING, JS_SET_INPUT, PARSER, _BLOCKS_JS

### python/parsers/kimi_parser.py — 25 КБ
- докстринг: Kimi (www.kimi.com) parser - v87.1 pilot. Unlike qwen/deepseek/ai_parser, this parser does NOT read the answer from the DOM. Instead it reads the model's answer directly from the network: kimi.com ans…
- классы: KimiChatMonitor(BaseNetMonitor) — 8 методов; KimiParser(BaseSiteParser) — 14 методов
- функции: split_text_and_action(full_text); count_answers(driver); answer_len(driver); answer_stream(driver); is_generating(driver); extract_answer(driver); wait_for_new_answer(driver, initial_count, timeout=900, quiet_period=4.0, hard_quiet_period=45.0, poll_interval=0.3, post_quiet_grace=6.0, progress_cb=None); send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None)
- константы: JS_FIND_INPUT, JS_FIND_SEND_BUTTON, JS_SET_INPUT, PARSER, _AGENT_ACTION_FENCE_RE, _DONE_MARKER_RE

### python/parsers/parser_base.py — 194 КБ
- докстринг: Менеджер парсинга: общая логика для ВСЕХ сайтов-нейросетей. BaseSiteParser реализует общий конвейер целиком: переключение на вкладку сайта -> вставка промпта -> отправка -> ожидание нового ответа (ста…
- классы: ParserCancelled(Exception) — 0 методов; BaseSiteParser() — 42 методов
- функции: _has_done_marker(text); _strip_done_marker(text); _safe_execute(driver, script, retries=5, delay=0.2, default=None); build_composed_answer_js(blocks_js, blocks_fn, code_block_selector); build_copy_click_js(blocks_js, blocks_fn, code_block_selector, copy_button_selector); missing_ref_bodies(action_raw, text); answer_transfer_incomplete(action_raw, text); score_answer_variant(full_text); select_best_answer_variant(variants); height_says_incomplete(text, block_height_px, px_per_line=PX_PER_LINE_DEFAULT, min_gap_lines=3.0, tolerance=1.25); read_composed_answer(driver, composed_js, log_tag='[parser_base]', copy_click_js=None); read_answer_stable(driver, composed_js, log_tag='[parser_base]', copy_click_js=None, attempts=4, delay=2.0); _try_merge_multi_action_blocks(raw_blocks); split_net_text_and_action(full_text); extract_answer_settled(driver, extract_fn, is_generating_fn=None, log_tag=u'[parser_base]', attempts=4, delay=2.0, max_wait=240.0, post_gen_tries=8, poll=2.5, net_fallback_fn=None); _escape_bbcode_py(text: str)
- константы: DONE_MARKER, PX_PER_LINE_DEFAULT, _ACTION_SYNONYMS, _ACTION_WRAPPERS, _ANY_LABEL_RE, _COMPOSED_ANSWER_TEMPLATE_JS, _COPY_CAPTURE_READ_JS, _COPY_CLICK_TEMPLATE_JS, _COPY_INTERCEPT_RESTORE_JS, _CORPUS_MAX_FILES, _DEST_SYNONYMS, _DONE_MARKER_RE, _FENCE_BODY_RE, _KNOWN_ACTIONS, _MISSING_COMMA_KEY_RE, _MONACO_HELPERS_JS

### python/parsers/qwen_parser.py — 36 КБ
- докстринг: Парсер сайта Qwen (chat.qwen.ai) — v73: боевые селекторы с реальной страницы. Интерфейс модуля тот же, что у ai_parser/deepseek_parser: send_message_and_get_response(driver, prompt, ...) -> {"text", "…
- классы: QwenParser(BaseSiteParser) — 20 методов
- функции: count_answers(driver); answer_len(driver); answer_stream(driver); answer_preview(driver); block_height(driver); is_generating(driver); _action_raw_from_text(text); extract_answer(driver, net_fallback_fn=None, net_finished_fn=None); wait_for_new_answer(driver, initial_count, timeout=900, quiet_period=4.0, hard_quiet_period=45.0, poll_interval=0.3, post_quiet_grace=6.0, progress_cb=None); send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None)
- константы: JS_ANSWER_LEN, JS_ANSWER_TEXT, JS_BLOCK_HEIGHT, JS_CLICK_PREFER_FIRST_RESPONSE, JS_CLICK_REGENERATE, JS_CLICK_SEND, JS_COMPOSED_ANSWER, JS_COPY_CLICK, JS_COUNT_ANSWERS, JS_DISPATCH_ENTER, JS_DUAL_CHOICE_BUTTON_COUNT, JS_FIND_INPUT, JS_IS_GENERATING, JS_SET_INPUT, PARSER, _BLOCKS_JS

### python/parsers/text_sanitize.py — 3 КБ
- докстринг: v86.2: очистка текста, пришедшего из веб-DOM (ответы нейросетей). Зачем: сайты (обнаружено на qwen) подмешивают в код невидимые символы: неразрывные пробелы U+00A0 (&nbsp; в HTML), нулевые байты, zero…
- функции: sanitize_llm_text(text)
- константы: _RX_JUNK, _RX_NEWLINES, _RX_SPACES

## python/server

### python/server/agent_prompts.py — 44 КБ
- докстринг: Инструкция для модели (PRIMING_TEMPLATE) и общие константы движка. Вынесено из main.py: чистые данные, без зависимостей.
- константы: API_CONTEXT_WINDOW, API_HISTORY_BUDGET, API_MAX_TOKENS, CODE_EXTS, MAX_ACTION_FIX_RETRIES, MAX_BATCH_FILES, MAX_CONTENT_PARTS, MAX_PLAN_PARTS, MAX_PLAN_STEPS, MAX_PLAN_TOTAL_STEPS, PER_FILE_CHAR_LIMIT, PRIME_COMPACT_THRESHOLD, PRIME_TREE_MAX_ENTRIES, PRIMING_TEMPLATE, PROMPT_HASH, TOTAL_CHAR_BUDGET

### python/server/api_history.py — 23 КБ
- докстринг: История диалога для API-режима: то, что модель помнит о разговоре. ЗАЧЕМ ОТДЕЛЬНОЕ ХРАНИЛИЩЕ. В браузерном режиме контекст живёт на самом сайте: вкладка помнит весь диалог, и агенту достаточно напечат…
- классы: ApiHistoryError(Exception) — 0 методов
- функции: _lock(base_dir, chat_id); _locked_history(func); _safe_id(chat_id); history_dir(base_dir); history_path(base_dir, chat_id); _empty(); _load(base_dir, chat_id); _save(base_dir, chat_id, data); estimate_tokens(text); _messages_tokens(messages); append(base_dir, chat_id, role, content, kind=''); append_exchange(base_dir, chat_id, user_text, assistant_text, user_kind=KIND_PROMPT, usage=None); _enforce_hard_cap(data); clear(base_dir, chat_id); delete(base_dir, chat_id); load_messages(base_dir, chat_id)
- константы: KEEP_RECENT, KIND_ANSWER, KIND_NOTE, KIND_PROMPT, KIND_TOOL_RESULT, MAX_MESSAGES, ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_USER, _COLLAPSE_NOTE, _CUT_MARK, _DIR_NAME, _MIN_COLLAPSE_CHARS, _TRIM_NOTE

### python/server/chat_routes.py — 76 КБ
- докстринг: Маршруты стартового экрана и чатов: список сайтов, список чатов, создание нового чата на выбранном сайте, открытие сохранённого чата (с переходом браузера на его страницу), переименование и удаление. …
- функции: _busy_error(); _navigate(driver, url); _check_chat_page(driver, url, wait=6.0); sites_list(); api_providers(); _catalog_payload(); _api_settings_payload(extra=None); api_settings_set(); _fetch_models(pid, connect_timeout=None); _catalog_extra_ids(); _catalog_needs_models(); _refresh_catalog(force); _enrich(pid, records); _models_index(); api_models_refresh(); api_models_scan()
- константы: SCAN_TIMEOUT

### python/server/chat_store.py — 11 КБ
- докстринг: Хранилище чатов агента. Каждый чат привязан к странице AI Studio (URL) и хранит: - название (авто из первого сообщения, можно переименовать), - сохранённый диалог (транскрипт) для восстановления в пан…
- классы: ChatStoreError(IOError) — 0 методов
- функции: _lock(base_dir); _path(base_dir); _load(base_dir); _save(base_dir, chats); title_from_prompt(prompt); list_chats(base_dir, current_prompt_hash=None); find_chat(base_dir, chat_id); find_chat_by_url(base_dir, url); create_chat(base_dir, url='', title=DEFAULT_TITLE, primed=False); update_chat(base_dir, chat_id, **fields); touch_chat(base_dir, chat_id, url=None, primed=None); touch_file_read(base_dir, chat_id, path); append_transcript(base_dir, chat_id, role, text); append_transcript_entries(base_dir, chat_id, entries); delete_chat(base_dir, chat_id)
- константы: DEFAULT_TITLE, LEGACY_DEFAULT_TITLES, MAX_TRANSCRIPT, _FILE_NAME, _LOCKS, _LOCKS_GUARD

### python/server/dashboard.py — 10 КБ
- докстринг: v80: дашборд сервера. - install() зеркалит stdout/stderr в кольцевой журнал (консоль работает как раньше). - DASHBOARD_HTML — страница http://127.0.0.1:5000/dashboard: секторы со статистикой (сервер /…
- классы: _Tee(object) — 4 методов
- функции: _redact(line); install(); get_lines(limit=None); uptime_text()
- константы: DASHBOARD_HTML, MAX_LINES, STARTED

### python/server/editor_context.py — 14 КБ
- докстринг: Validation and compact formatting for one-turn Godot editor snapshots.
- функции: _text(value, limit=500); _path(value); _positive_int(value); _format_code(value, limit); _scene_block(value); _selection_block(value); _script_block(value); _script_context_requested(user_prompt); snapshot_for_prompt(user_prompt, snapshot); _diagnostics_block(value); _run_block(value); normalize_editor_snapshot(value); format_editor_snapshot(value, max_chars=DEFAULT_MAX_CHARS); attach_to_prompt(user_prompt, snapshot, max_chars=DEFAULT_MAX_CHARS); user_prompt_without_context(prompt)
- константы: DEFAULT_MAX_CHARS, HARD_MAX_CHARS, SCHEMA_VERSION, _END, _START, _USER

### python/server/log_reader.py — 14 КБ
- функции: _log_path(user_data_dir); _state_path(state_dir); _load_sent_fingerprint(state_dir); save_sent_fingerprint(state_dir, fingerprint); _code_context(project_root, res_path, line_no); list_input_actions(project_root); collect_errors(user_data_dir, project_root, state_dir); build_summary(report); _file_of(err); format_log_report(report)
- константы: CONTEXT_LINES, MAX_ERRORS, _ERROR_PREFIXES, _INPUT_ACTION_RE, _LOCATION_RE, _SKIP_PREFIXES, _STATE_FILENAME

### python/server/md_to_bbcode.py — 10 КБ
- докстринг: Markdown -> BBCode для панели агента. ЗАЧЕМ. Панель рисует ответы через RichTextLabel с bbcode_enabled, и браузерные парсеры отдают ей именно BBCode: они конвертируют HTML страницы сайта прямо в JS-эк…
- функции: escape(text); _inline(text); _code_block(lang, lines); to_bbcode(text)
- константы: ACTION_PLACEHOLDER, CODE_BODY, CODE_HEADER, DEFAULT_CODE_LANG, HEADING_FMT, HR_LINE, _BRACKETS_RE, _FENCE_RE, _HEADING_RE, _HR_RE, _INLINE_RE, _OL_RE, _QUOTE_RE, _UL_RE

### python/server/port_guard.py — 7 КБ
- докстринг: Защита порта :5000 от «призрачных» сокетов (Windows). Как появляется призрак (найдено 13.10.2026 на реальном случае): 1. werkzeug при app.run() делает слушающий сокет НАСЛЕДУЕМЫМ (serving.py: srv.sock…
- функции: probe_port(port=5000, host=_HOST, timeout=2.0); kill_orphan_chromedrivers(timeout=25.0); recover_ghost_port(port=5000, host=_HOST, log=print)
- константы: _HOST, _PS_KILL_ORPHANS

### python/server/rate_limit.py — 11 КБ
- докстринг: v104.12: детект лимита запросов и расписание спящего режима. Последний из четырёх гардрейлов: сайты бесплатных чатов ограничивают частоту запросов (HTTP 429, баннеры «Высокая нагрузка», просьбы подожд…
- функции: reason_from_text(text, action=None); reason_from_status(status); kind_from_status(status); schedule_for(kind); sleep_seconds(attempt, retry_after=None, kind=KIND_LIMIT)
- константы: KIND_LIMIT, KIND_OUTAGE, MARKERS, MAX_HONORED_RETRY_AFTER, MAX_TEXT_LEN_FOR_MARKERS, OUTAGE_JITTER, OUTAGE_SLEEPS, SLEEPS, TRANSPORT

### python/server/server_auth.py — 12 КБ
- докстринг: Проверка того, что запрос пришёл именно от панели этого проекта. ЧТО ЭТО РЕАЛЬНО ДАЁТ И ЧЕГО НЕ ДАЁТ. Токен лежит в файле, который читается тем же пользователем, что запускает Godot. Значит программа,…
- функции: reset(); bound_dir(); token_path(user_data_dir); read_token(user_data_dir); _same_dir(a, b); check(path, header_token, user_data_dir); install(app, jsonify, body_limits=None)
- константы: HEADER, OPEN_PATHS, TOKEN_FILE

### python/server/server_state.py — 39 КБ
- докстринг: Состояние сессии сервера + общие помощники. Здесь живёт единое STATE, держатель драйвера браузера, привязка чатов, флаг primed и живой прогресс. Вынесено из main.py, чтобы и основные маршруты, и chat_…
- классы: SessionContextError(ValueError) — 0 методов
- функции: claim_runtime_request(data); reset_runtime_turn(status=None, increment=False); bind_runtime_check(data); claim_runtime_check(data, allow_unbound=False); _claim_runtime_result(data, pending_key, allow_unbound=False); begin_exchange(); end_exchange(); exchange_active(); try_begin_turn_exchange(reset_cancel=True); try_begin_navigation(); clear_request_activity(_error=None); begin_turn_transcript(chat_id); commit_turn_transcript(); ensure_turn_agent_response(text); discard_turn_transcript(); set_driver(d)
- константы: STATE

## python/tests

### python/tests/_fake_selenium.py — 3 КБ
- докстринг: Заглушки selenium для оффлайн-тестов (общий помощник, не тест). Импортировать ДО parser_base/kimi_parser/qwen_parser.
- функции: install()

### python/tests/_probe_doh_win10049.py — 3 КБ
- докстринг: Проба: воспроизвести WinError 10049 «свежим» кодом и кодом из собранного EXE.
- функции: load_frozen(name); probe(tag, doh, oc)
- константы: D, PYZ

### python/tests/repro_check_blocking.py — 3 КБ
- докстринг: Синтетический репро (этап 1): `check` игнорирует blocking — ложное «clean». Сценарий: валидный .gd, --validation required, Godot недоступен. Ожидание по контракту: НЕ «clean» и НЕ rc=0 (write apply в …
- функции: run(argv); main()
- константы: HERE, PY

### python/tests/repro_check_truncated.py — 6 КБ
- докстринг: Синтетический репро: `check` молча усекает файл до 200 000 символов. Сценарий: `.gd` ~629 КБ с заведомым синтаксическим мусором В ХВОСТЕ (за пределом 200 000 символов). Ожидание по контракту: дефект н…
- функции: run(argv); _big_with_tail_defect(near=BIG_LIMIT); main()
- константы: BIG_LIMIT, HERE, MAX_SECONDS, PY, TAIL_DEFECT

### python/tests/repro_check_unchecked.py — 7 КБ
- докстринг: Синтетический репро (этап 4): `check` рапортует «clean» о непроверяемых файлах. В `_check_one_path` ветки проверки есть только для .gd/.tscn/.py/.json/.cfg и headless-типов. Для .md, .png, project.god…
- функции: run(argv); main()
- константы: HERE, PY

### python/tests/repro_node_rename_double_intercept.py — 8 КБ
- докстринг: Прямое воспроизведение ЗАДАЧИ 3: два переименования подряд перехватом. Сценарий живого редактора (без Godot, через настоящие маршруты Flask): #1 человек переименовал узел PlayerPanel -> ActorPanel (F2…
- функции: check(name, condition, detail=''); post(client, route, payload); rename(client, new_name, previous_name); main_flow()
- константы: SCENE, SCENE_RES, SCRIPT, SCRIPT_RES

### python/tests/repro_plan_cwd.py — 6 КБ
- докстринг: Синтетический репро (этап 3): `plan_id` зависит от рабочей директории. Причина: `_plan_digest` считает `os.path.realpath(policy["addon_dir"] or "")`, а `os.path.realpath("")` возвращает ТЕКУЩИЙ катало…
- функции: run_in(cwd, argv); plan_of(output); main()
- константы: HERE, PY

### python/tests/repro_plan_gc.py — 7 КБ
- докстринг: Синтетический репро (этап 6): осиротевшие квитанции планов не убираются. `_claim_plan_receipt` переименовывает `<plan>.json` в `<plan>.json.applying-<pid>`. При штатном apply файл удаляется в конце, н…
- функции: run(argv); main()
- константы: HERE, PY

### python/tests/repro_return_codes.py — 11 КБ
- докстринг: Синтетический репро (этап 5): коды возврата и режимы доступа не согласованы. Подпроблемы по MCP_ALPHA_AUDIT_PLAN.md: 5a — инфраструктурные отказы отдаются как 2 (not-found) вместо 3 (error); 5b — ошиб…
- функции: run(argv); first_line(text); make_project(root); main()
- константы: AGENT_REL, HERE, PY, SCENE_BODY

### python/tests/run_integration_regressions.py — 6 КБ
- докстринг: Run offline integration suites in separate processes, then optional real Godot tests.
- функции: main()
- константы: SUITES

### python/tests/synthetic_card_bench.py — 5 КБ
- докстринг: Синтетический полигон FUNC CARD: базовый класс + N наследников. Цель: проверить поведение глубокой карточки `func:имя` на большом графе (сотни наследников, десятки вызовов, переопределения, dynamic-ст…
- функции: gen(n_sub: int=120); query(query_text: str)
- константы: BASE_GD, ROOT, SUB, SUB_CALLER, SUB_DYNAMIC, SUB_OVERRIDE

### python/tests/test_access_policy_flow.py — 17 КБ
- докстринг: Security-policy regressions for the main HTTP/write boundary.
- классы: AccessPolicyFlowTests(unittest.TestCase) — 15 методов

### python/tests/test_access_policy_state.py — 6 КБ
- докстринг: Strict state parsing for independent add-on/self-edit capabilities.
- классы: AccessPolicyStateTests(unittest.TestCase) — 8 методов

### python/tests/test_agent_bridge.py — 117 КБ
- докстринг: Тесты альфа-моста agent_bridge.py (MCP v0). Контракт моста, который здесь закрепляется: * код возврата 0 — успех, данные в stdout; * код возврата 2 — «запрошенного не существует» / обоснованный отказ …
- классы: AgentBridgeTests(unittest.TestCase) — 146 методов
- функции: run_bridge(argv)
- константы: _SIG_CLASSES, _TOOLS

### python/tests/test_agent_entry_context_menu.py — 15 КБ
- докстринг: Синтетические тесты Шага 2 плана UNIFIED_ENTRY_PLAN: ContextMenu. Что проверяется --------------- 1) Статика: `SceneTreeMenu` наследует `EditorContextMenuPlugin`, реализует `_popup_menu(paths: PackedS…
- классы: StaticChecks() — 3 методов
- функции: build_harness(); live_check(addon: Path, executable: str, temp_parent); main()
- константы: FATAL_ENGINE_LINES, HARNESS, REQUIRED_SLOTS, SENTINEL, SHUTDOWN_NOISE

### python/tests/test_agent_entry_integrations.py — 15 КБ
- докстринг: Синтетические тесты Шага 1 плана UNIFIED_ENTRY_PLAN: EditorSignals. Что проверяется --------------- 1) Статика: `agent_integration_signals.gd` существует, наследует RefCounted, принимает EditorPlugin …
- классы: StaticChecks() — 3 методов
- функции: build_harness(); live_check(addon: Path, executable: str, temp_parent); main()
- константы: EDITOR_PLUGIN_SIGNALS, HANDLER_FOR, HARNESS, SENTINEL, SHUTDOWN_NOISE

### python/tests/test_agent_entry_tool_menu.py — 17 КБ
- докстринг: Синтетические тесты Шага 3 плана UNIFIED_ENTRY_PLAN: ToolMenu. Что проверяется --------------- 1) Статика: меню собрано как подменю через `add_tool_submenu_item`, снимается через `remove_tool_menu_ite…
- классы: StaticChecks() — 6 методов
- функции: add_item_ids(text); live_check(addon: Path, executable: str, temp_parent); main()
- константы: FATAL_ENGINE_LINES, HARNESS, PANEL_METHODS, SENTINEL, SHUTDOWN_NOISE

### python/tests/test_agent_server_client.py — 12 КБ
- докстринг: Синтетические тесты Шага 4 плана UNIFIED_ENTRY_PLAN: AgentServer. Что проверяется --------------- 1) Статика: `const HOST` объявлен РОВНО ОДИН РАЗ во всём аддоне и живёт в `agent_server.gd`. Раньше он…
- классы: StaticChecks() — 4 методов
- функции: live_check(addon: Path, executable: str, temp_parent); main()
- константы: FATAL_ENGINE_LINES, HARNESS, SENTINEL, SHUTDOWN_NOISE

### python/tests/test_aistudio_send_acceptance.py — 5 КБ
- докстринг: AI Studio acceptance signals; no browser or model requests.
- классы: AiStudioAcceptanceTests(unittest.TestCase) — 10 методов

### python/tests/test_answer_judge.py — 16 КБ
- функции: _answer(action); _project(); test_exact_read_file_beats_broad_librarian(); test_librarian_beats_nonexistent_read_file(); test_gather_context_is_high_value_read_action(); test_runtime_inspection_is_bounded_read_action(); test_runtime_check_is_deterministic_bounded_action(); test_impossible_patch_is_blocking(); test_rename_symbol_uses_safe_dry_run(); test_edit_scene_uses_structural_schema_validation(); test_project_settings_uses_structural_schema_validation(); test_resource_uses_structural_schema_validation(); test_transaction_uses_atomic_overlay_validation(); test_patch_judge_matches_runtime_crlf_normalization(); test_project_command_compiles_then_uses_primitive_judge(); test_broken_gdscript_is_blocking()

### python/tests/test_anthropic_compat.py — 10 КБ
- классы: Handler(BaseHTTPRequestHandler) — 2 методов
- функции: check(name, cond, detail=None)
- константы: CFG

### python/tests/test_api_backend.py — 54 КБ
- классы: Handler(BaseHTTPRequestHandler) — 3 методов
- функции: check(name, cond); sse(obj); _sse_text(text, finish='stop', usage=True, reasoning=False); _chunks_for(text, finish='stop'); backend(rec=None); cancel_soon(*_a)
- константы: ALL_REQUESTS, AUTH_SEEN, BASE, CALLS, CUT_AT, LAST_REQUEST, MODE, MODEL_ANSWER, PART1, PART2, PART2_OVERLAP, PORT, REC, RK1, RK2, ROT_REC

### python/tests/test_api_end_to_end.py — 31 КБ
- классы: Handler(BaseHTTPRequestHandler) — 2 методов
- функции: check(name, cond, detail=None); post(path, body=None)
- константы: ANSWER, BASE_BODY, CFG, CID, ENTRY_ID, HEADERS, OTHER_PATH, PLAYER_BEFORE, PLAYER_PATH, PORT, PROJ, SECOND_ID, SEEN, TOKEN, UDD, _BUDGET_REAL

### python/tests/test_api_history.py — 14 КБ
- функции: check(name, cond, detail=None); budget_used(req)
- константы: BASE, BIG, CID, CID2, CID3, CID4, CID5, RAW_ANSWER

### python/tests/test_api_history_failures.py — 11 КБ
- докстринг: Fault injection for API history transactions and accepted backend replies.
- классы: HistoryFailures(unittest.TestCase) — 13 методов

### python/tests/test_api_route_persistence.py — 13 КБ
- докстринг: Real Flask requests with disk faults at API chat commit boundaries.
- классы: ApiRoutePersistenceTests(unittest.TestCase) — 20 методов

### python/tests/test_api_routes.py — 52 КБ
- классы: Handler(BaseHTTPRequestHandler) — 4 методов
- функции: check(name, cond); post(path, body=None); _guard_getaddrinfo(host, *a, **kw); _guard_outside(host, *a, **kw)
- константы: CATALOG_PATH, CFG, FAKE_CATALOG, LOCAL, PORT, UDD, _K_A, _K_B, _REAL_CATALOG_URL

### python/tests/test_api_secrets_and_limits.py — 17 КБ
- функции: check(name, cond, detail=None)
- константы: CFG, K1, K2, K3, KEY, NEW_KEY, PROXY_PASS

### python/tests/test_api_transport.py — 19 КБ
- классы: Handler(BaseHTTPRequestHandler) — 6 методов
- функции: check(name, cond); sse(obj); delta(content=None, reasoning=None, finish=None, usage=None, model='m/test'); call(path, **kw); cancel_after_two(); count(t, is_r); _accept_and_hang()
- константы: BASE, CFG, ERRORS, LAST, MSG, OK_STREAM, PORT

### python/tests/test_arch_gate.py — 9 КБ
- докстринг: Тесты архитектурного гейта в мосте (agent_bridge, режим agent-dev). Контракт: * новый .py агента с именем функции ядра — отказ (rc=2, «дубль из ядра»); * новый .py в зоне потребителя с уникальным имен…
- классы: ArchGateTests(unittest.TestCase) — 18 методов
- функции: run_bridge(argv)
- константы: AGENT, MAP, _TOOLS

### python/tests/test_arch_map.py — 16 КБ
- докстринг: Тесты карты архитектуры (arch_map.py): зоны, имена, вердикты, аудит. Проверяемый контракт: * зоны сегментные: `*.gd` не ловит вложенные файлы, `**` ловит всё; * вердикт нового файла честный: дубль име…
- классы: Fixture(unittest.TestCase) — 3 методов; ZoneMatchingTests(Fixture) — 3 методов; PublicNamesTests(unittest.TestCase) — 2 методов; CheckNewFileTests(Fixture) — 14 методов; AuditTests(Fixture) — 4 методов; CleanlinessTests(Fixture) — 5 методов; ShippedMapTests(unittest.TestCase) — 4 методов
- константы: ADDON, LIMITS, MINI_MAP

### python/tests/test_arena_parser.py — 30 КБ
- классы: _CDP() — 2 методов
- функции: _apply_capture(raw=CAPTURE); test_exact_capture_text(); test_monitor_matches_first_and_followup_endpoints(); test_module_response_carries_battle_choice_summary(); test_battle_collects_two_separate_post_bodies_as_a_and_b(); test_battle_hides_done_until_second_post_arrives(); test_battle_does_not_judge_or_fallback_before_stream_finishes(); test_battle_does_not_judge_when_only_one_branch_has_finished(); test_battle_falls_back_to_finished_single_post_with_a0_and_a1(); test_direct_and_battle_sites_share_parser_but_have_distinct_urls(); test_json_string_decoding(); test_battle_b0_is_variant_b_and_bd_finishes(); test_arbitrary_utf8_splits(); test_final_tail_without_newline(); test_additional_stream_is_not_mixed(); test_dual_response_selects_valid_agent_action()
- константы: CAPTURE

### python/tests/test_asset_refactor.py — 29 КБ
- докстринг: Unit tests for asset and companion .import file refactoring: - Automatic detection and movement of companion .import files - Updating source_file inside .import while preserving Godot 4 UID - Cascade …
- классы: AssetRefactorTests(unittest.TestCase) — 13 методов
- константы: SAMPLE_IMPORT_TEMPLATE

### python/tests/test_asset_refactor_live.py — 12 КБ
- классы: TestAssetRefactorLive(unittest.TestCase) — 4 методов
- функции: find_godot_executable()
- константы: SENTINEL

### python/tests/test_browser_send_acceptance.py — 9 КБ
- докстринг: Offline full-pipeline regressions for late insertion and send acceptance.
- классы: _AcceptanceParser(_FakeRegenParser) — 16 методов; BrowserSendAcceptanceTests(unittest.TestCase) — 14 методов

### python/tests/test_browser_target_binding.py — 4 КБ
- докстринг: Local debugger discovery and AI Studio page ownership, without a browser.
- классы: BrowserTargetTests(unittest.TestCase) — 5 методов

### python/tests/test_browser_turn_cancel.py — 4 КБ
- докстринг: Cancellation is terminal across internal repair/retry calls, not user turns.
- классы: TurnCancellationTests(unittest.TestCase) — 4 методов

### python/tests/test_browser_wait_safety.py — 10 КБ
- докстринг: Offline deadline and send-boundary regressions; run as a standalone suite.
- классы: _Clock() — 3 методов; _WaitParser(_FakeRegenParser) — 8 методов; _SendParser(_FakeRegenParser) — 6 методов; BrowserWaitSafetyTests(unittest.TestCase) — 18 методов

### python/tests/test_catalog.py — 43 КБ
- классы: Handler(BaseHTTPRequestHandler) — 2 методов
- функции: check(name, cond, detail=None); hits()
- константы: CFG, FAKE, PORT, REAL_URL

### python/tests/test_chat_pending_cleanup.py — 1 КБ
- классы: ChatPendingCleanupTests(unittest.TestCase) — 1 методов
- константы: PYTHON_DIR

### python/tests/test_chat_site_restore.py — 2 КБ
- классы: Driver() — 0 методов
- функции: test_restore_battle_chat_preserves_site_id_after_restart()

### python/tests/test_chat_state_isolation.py — 8 КБ
- функции: test_notes_and_turns_are_chat_scoped(); test_concurrent_transcript_writes_are_not_lost(); test_atomic_save_failure_preserves_previous_json(); test_transcript_trim_keeps_whole_messages(); test_buffered_turn_is_committed_or_discarded_as_one_unit(); test_corrupt_store_fails_closed(); test_turn_and_navigation_admission_are_exclusive(); test_transcript_failure_does_not_leave_partial_turn()
- константы: PYTHON_DIR

### python/tests/test_chats_list_live.py — 4 КБ
- докстринг: Живой тест: /chats/list не возвращает ошибку «браузер занят» для своего проекта во время генерации.
- классы: ChatsListLiveTests(unittest.TestCase) — 5 методов

### python/tests/test_check_action_disclosure.py — 8 КБ
- докстринг: Синтетика: check_action (MCP-судья) обязан РАСКРЫВАТЬ недоказанные ссылки. Дыра, найденная замером на живом коде. `check_action` — локальный судья, который спрашивает «это действие безопасно?». Он зва…
- классы: JudgeDisclosure(unittest.TestCase) — 11 методов
- функции: _answer(action); _make_project(prefix, arena=UNPROVEN)
- константы: CLEAN, PLAYER, TYPED, UNPROVEN

### python/tests/test_client_refactor_flow.py — 10 КБ
- классы: TestClientRefactorFlow(unittest.TestCase) — 6 методов

### python/tests/test_deepseek_no_double_send.py — 10 КБ
- докстринг: Offline DeepSeek delivery regressions through the real base send pipeline.
- классы: Clock() — 3 методов; Element() — 2 методов; Driver() — 2 методов; DeepSeekDeliveryTests(unittest.TestCase) — 18 методов

### python/tests/test_doh.py — 15 КБ
- классы: Handler(BaseHTTPRequestHandler) — 2 методов
- функции: check(name, cond, detail=None); _read_qname(data, i=12); _build_response(query, ip, ttl=60); _fallback_probe(host, port, family=0, type=0, proto=0, flags=0)
- константы: ANSWERS, CFG, DOH_URL, PORT, SEEN

### python/tests/test_editor_context.py — 5 КБ
- функции: check(name, cond, detail=None)

### python/tests/test_external_move_sync.py — 10 КБ
- докстринг: Step-2 audit regression tests: sync_references_after_external_move must keep the project consistent after FileSystemDock moves and its rollback must return the moved file/directory to the original loc…
- классы: ExternalMoveSync(unittest.TestCase) — 13 методов; DirectoryRelocationOffsets(unittest.TestCase) — 2 методов

### python/tests/test_file_refactor.py — 13 КБ
- докстринг: Unit tests for file_refactor: references search, rename transaction, and rollback.
- классы: FileRefactorTests(unittest.TestCase) — 6 методов

### python/tests/test_file_refactor_flow.py — 7 КБ
- докстринг: Integration test for file refactor Flask routes, chat action, confirmation, and rollback.
- классы: FileRefactorFlowTests(unittest.TestCase) — 5 методов

### python/tests/test_file_refactor_live.py — 12 КБ
- докстринг: Live engine verification of Safe File Rename using real Godot 4 executable.
- классы: TestFileRefactorLive(unittest.TestCase) — 5 методов
- функции: find_godot_executable()

### python/tests/test_find_symbol_usages.py — 7 КБ
- докстринг: Синтетические тесты п.4.1: read-only шаг «найти использования». Модель вынуждена угадывать locator для rename_symbol, потому что отдельного поиска использований не существует. Здесь он появляется: оди…
- классы: FindUsages(unittest.TestCase) — 15 методов
- константы: SCRIPT

### python/tests/test_find_usages_reason.py — 11 КБ
- докстринг: Синтетика: read-поверхности обязаны называть ПРИЧИНУ недоказанности. Замер (дыра №6). Прошлая серия этапов закрыла раскрытие в пяти местах: check_action, мост write preview/apply, подтверждение панели…
- классы: ProbableCarriesReason(unittest.TestCase) — 6 методов; AnalyzeAndFormatCarryReason(unittest.TestCase) — 8 методов
- функции: _project(prefix, files); _class_action(**extra); _variable_action(**extra)
- константы: CLEAN, PLAYER, TYPED, UNIT, UNPROVEN, UNPROVEN_RECEIVER

### python/tests/test_function_card.py — 16 КБ
- докстринг: Тесты глубокой карточки функции (godot_tools/function_card.py). План: docs/function_card_plan.md (S2–S4). Проверяются на синтетическом мини-проекте ВСЕ секции карточки: тело, символы по группам (члены…
- классы: FunctionCardTest(unittest.TestCase) — 8 методов; FunctionCardEdgeTest(unittest.TestCase) — 3 методов; FunctionCardInheritsTest(unittest.TestCase) — 8 методов; FunctionCardBridgeTest(unittest.TestCase) — 4 методов; FunctionCardLibrarianTest(unittest.TestCase) — 3 методов
- функции: _write(root, rel, text); _run_bridge(argv); _make_project()
- константы: BASE_GD, CTX_GD, GRUNT_GD, HERO_GD, IN_BASE_GD, IN_DUP_A_GD, IN_DUP_B_GD, IN_DUP_CHILD_GD, IN_INNER_AFTER_GD, IN_INNER_ONLY_GD, IN_LEAF_GD, IN_MID_GD, IN_REL_GD, OGRE_GD, SCORE_GD, _TOOLS

### python/tests/test_gather_context.py — 7 КБ
- функции: _write(root, rel, text); _project(); test_validation_and_parser_normalization(); test_exact_symbol_scene_dependencies_and_settings(); test_ambiguous_symbol_is_not_guessed(); test_budget_and_no_mutation(); test_policy_forbidden_explicit_symbol_is_masked(); test_project_settings_go_through_policy_read_boundary(); run_all()

### python/tests/test_gdscript_move_fixes.py — 5 КБ
- докстринг: Step-4 audit regression checks for the editor-side GDScript (agent_panel.gd). Без запуска Godot здесь возможны только статические проверки исходников — по образцу test_gdscript_wiring.py. Полная вериф…
- функции: check(name, cond, detail=None); read(path); func_src(src, func_name)
- константы: ADDON, PANEL

### python/tests/test_gdscript_wiring.py — 41 КБ
- классы: GDScriptWiringTests(unittest.TestCase) — 1 методов
- функции: check(name, cond, detail=None); read(path); dict_block(name); keys_of(block); entries_of(block); read_panel(); _func_spans(text, names)
- константы: ADDON, ALLOWED, API_SIGNALS, EXPECTED_CHECK_COUNT, GD_FILES, LOCALE, _CYR, _FMT_RE, _UI_PROPS

### python/tests/test_godot_agent_mcp.py — 30 КБ
- докстринг: Тесты MCP-сервера Godot Agent (обёртка над agent_bridge.py). Контракт, который здесь закрепляется: * сервер — тонкая обёртка: проверки доступа не дублируются, всё решает agent_bridge и его capability-…
- классы: McpServerTests(unittest.TestCase) — 40 методов; McpMainTransportTests(unittest.TestCase) — 9 методов
- константы: _TOOLS

### python/tests/test_godot_executor_live.py — 5 КБ
- докстринг: Run real executor regressions in a disposable, plugin-free Godot editor project. Usage from godot_agent: python -B python/tests/test_godot_executor_live.py --godot EXE Only top-level addon .gd/.tscn f…
- функции: main()
- константы: CASES, SENTINEL

### python/tests/test_godot_headless_validation.py — 11 КБ
- классы: HeadlessValidationTests(unittest.TestCase) — 12 методов
- константы: FAKE_GODOT, PYTHON_DIR

### python/tests/test_godot_live.py — 4 КБ
- докстринг: Compile the actual addon scripts in an isolated project using real Godot 4. Usage: python -B tests/test_godot_live.py --godot C:/tools/godot.exe No editor plugin, project autoload or user game is star…
- функции: main()
- константы: HARNESS

### python/tests/test_headless_validator_live.py — 5 КБ
- докстринг: Exercise the production baseline/candidate validator with an explicit real Godot.
- классы: LiveValidatorTests(unittest.TestCase) — 8 методов

### python/tests/test_high_level_actions.py — 6 КБ
- функции: write(root, rel, text); project(); test_scene_component_compiles_in_safe_order(); test_settings_rename_and_atomic_compilers(); test_schema_parser_refs_and_no_writes()

### python/tests/test_high_level_flow.py — 4 КБ
- функции: write(root, rel, text); payload(response)

### python/tests/test_history_journal_safety.py — 14 КБ
- докстринг: Journal persistence, transaction serialization, and rollback identity safety.
- классы: HistoryJournalSafety(unittest.TestCase) — 17 методов

### python/tests/test_http_boundary_safety.py — 7 КБ
- докстринг: Real Flask requests: pre-parse limits/auth and reset/admission isolation.
- классы: HttpBoundarySafetyTests(unittest.TestCase) — 9 методов

### python/tests/test_insert_plan_choice.py — 5 КБ
- классы: FakeDriver(object) — 1 методов; FakeEl(object) — 1 методов; NoPasteSite(parser_base.BaseSiteParser) — 4 методов; PasteSite(NoPasteSite) — 1 методов
- функции: check(name, cond)

### python/tests/test_kimi_stream_fallback.py — 4 КБ
- классы: FakeDriver(object) — 1 методов; EmptyDriver(object) — 1 методов
- функции: check(name, cond); make_monitor()

### python/tests/test_librarian.py — 107 КБ
- докстринг: v105: офлайн-тесты Библиотекаря (ask_librarian): слои ответа, бюджет, подтокены snake_case, микро-обновление индекса, исключение addons/.
- функции: _write(root, rel, content); _make_project(); test_subtokens_find_snake_case(); test_answer_layers_and_budget(); test_update_entries_micro_refresh(); test_note_files_changed_res_paths(); test_update_entries_without_index(); test_synonyms_expand_search(); test_weighted_ranking(); test_typo_hint(); test_callers_layer(); test_autoloads_layer(); test_signal_wiring_layer(); test_vars_and_consts_indexed(); test_shared_brain_project_isolation(); test_bom_first_line_indexed()
- константы: BIG_GD, CARD_GD, GM_GD, NESTED_FSM_GD, ORC_GD, PLAYER_GD, PLAYER_TSCN, PROJECT_GODOT, STATS_GD

### python/tests/test_locale_format.py — 9 КБ
- докстринг: Связка «словарь переводов ↔ места форматирования» в GDScript-панели. Зачем этот тест. Строка вида panel._view.add_system(panel._t("log_auto_ok") % log_info) в рантайме падает с «not all arguments conv…
- классы: LocaleFormatTest(unittest.TestCase) — 8 методов
- функции: parse_locale(path=LOCALE_PATH); placeholders(value); gd_files(); _skip_string(text, i); format_arg(text, pos); count_args(arg)
- константы: ADDON_DIR, LOCALE_PATH, PRELOADED_SCRIPTS, _CLOSE, _DICT_START, _ENTRY, _OPEN, _REF, _SITE, _SKIP_DIRS, _VERB

### python/tests/test_log_report_batch.py — 7 КБ
- функции: check(name, cond, detail=None); err(msg, loc='', count=1, context='')
- константы: REPORT

### python/tests/test_md_to_bbcode.py — 10 КБ
- функции: check(name, cond)

### python/tests/test_megaprompt_once.py — 2 КБ
- функции: check(name, cond)

### python/tests/test_minilich_status_purity.py — 7 КБ
- докстринг: Синтетические тесты: опрос статуса mini-lich НЕ должен запускать обучение. Баг (репорт: «после нажатия „Обновить справочник API Godot“ в логах сервера началось обучение нейросети»): minilich.status() …
- классы: _Fixture(unittest.TestCase) — 2 методов; StatusDoesNotStartTraining(_Fixture) — 5 методов

### python/tests/test_mirror_js_fallback.py — 4 КБ
- классы: FakeEl(object) — 1 методов; QwenLikeParser(parser_base.BaseSiteParser) — 6 методов; TypingWorksParser(QwenLikeParser) — 1 методов; AllBrokenParser(QwenLikeParser) — 1 методов
- функции: check(name, cond)

### python/tests/test_mirror_soft_newline.py — 4 КБ
- классы: FakeEl(object) — 2 методов; MirrorParser(parser_base.BaseSiteParser) — 4 методов
- функции: check(name, cond)
- константы: MULTILINE

### python/tests/test_move_dir_safety.py — 25 КБ
- докстринг: Step-1 audit regression tests: directory self-nesting, companion files on directory moves, case-only renames on Windows, and os.link fallbacks. Every test here encodes the EXPECTED behaviour after the…
- классы: _ProjectFixture(unittest.TestCase) — 2 методов; DirectorySelfNesting(_ProjectFixture) — 5 методов; DirectoryMoveCompanions(_ProjectFixture) — 2 методов; CaseOnlyRenameWindows(_ProjectFixture) — 4 методов; DirectoryCaseOnlyRenameWindows(_ProjectFixture) — 9 методов; HardlinkFallback(_ProjectFixture) — 5 методов; CaseOnlyDirComponentRenameWindows(_ProjectFixture) — 5 методов

### python/tests/test_move_race_and_agent.py — 6 КБ
- докстринг: Step-3 audit regression tests: parallel external move sync must not fail with StaleFileRefactorError (audit 1.4), and the agent's move_file plan step must update references like a safe rename (audit 2…
- классы: ParallelExternalMoveSync(unittest.TestCase) — 3 методов; AgentMoveFileUpdatesReferences(unittest.TestCase) — 4 методов

### python/tests/test_move_safety.py — 21 КБ
- докстринг: Real temporary-project moves with injected filesystem failures; no Godot process.
- классы: MoveSafety(unittest.TestCase) — 29 методов

### python/tests/test_net_monitor_lifecycle.py — 14 КБ
- докстринг: Offline request-order and terminal-state regressions for BaseNetMonitor.
- классы: FakeCDP() — 4 методов; AppendMonitor(BaseNetMonitor) — 10 методов; ObservedSetupEvent() — 3 методов; LifecycleTests(unittest.TestCase) — 23 методов
- константы: URL

### python/tests/test_node_refactor.py — 18 КБ
- докстринг: Unit tests for node_refactor: scene node rename, animation tracks, connections, and GDScript updates.
- классы: NodeRefactorTests(unittest.TestCase) — 10 методов

### python/tests/test_node_refactor_flow.py — 14 КБ
- докстринг: Integration test for node refactor Flask routes, chat action, confirmation, and rollback.
- классы: NodeRefactorFlowTests(unittest.TestCase) — 8 методов

### python/tests/test_node_refactor_live.py — 11 КБ
- докстринг: Live engine verification of Safe Node Rename using real Godot 4 executable.
- классы: TestNodeRefactorLive(unittest.TestCase) — 5 методов
- функции: find_godot_executable()

### python/tests/test_node_rename_intercept.py — 12 КБ
- докстринг: Синтетические проверки ЗАДАЧИ 3: перехват переименования узла человеком. Автоматически эту задачу целиком не проверить — окончательное слово за живым редактором (test_remaining_work_steps.py --godot).…
- классы: StaticChecks() — 4 методов
- функции: main()

### python/tests/test_panel_short_channel.py — 4 КБ
- докстринг: Синтетический тест подэтапа 4.4: панель не создаёт HTTPRequest. Короткие запросы панели (живой ввод, опрос прогресса, остановка чата, автосинхронизация переименований) раньше держали на себе четыре от…
- классы: StaticChecks() — 3 методов
- функции: panel_source(addon: Path); main()

### python/tests/test_paste_attachment.py — 8 КБ
- классы: FakeEl(object) — 3 методов; FakeDriver(object) — 2 методов; FakeSite(parser_base.BaseSiteParser) — 11 методов; KimiDrv(object) — 1 методов; KimiDrvBroken(object) — 1 методов
- функции: check(name, cond)

### python/tests/test_paste_slow_guard.py — 4 КБ
- классы: SlowFieldParser(parser_base.BaseSiteParser) — 3 методов
- функции: check(name, cond)
- константы: BIG

### python/tests/test_path_policy_safety.py — 18 КБ
- докстринг: Protected paths and Windows aliases must not bypass action boundaries.
- классы: PathPolicySafety(unittest.TestCase) — 13 методов

### python/tests/test_port_guard.py — 6 КБ
- функции: check(name, cond, detail=None); free_port(); listening_socket(port, serve_reply=False)
- константы: HOST

### python/tests/test_probable_access.py — 12 КБ
- докстринг: Этап 3: доступ к режиму probable — он реализован, но недостижим. Замер. `MODES = ("strict", "probable")` объявлено, `probable` обрабатывается в `prepare_rename`, но НИКТО его не выставляет: ни панель,…
- классы: ProbableSemanticsUnchanged(unittest.TestCase) — 7 методов; ModeReachesAction(unittest.TestCase) — 2 методов; PanelCanChooseMode(unittest.TestCase) — 5 методов; ConfirmationExplainsRisk(unittest.TestCase) — 2 методов
- функции: _project(prefix, files); _action(**extra)
- константы: DYNAMIC, PLAYER, TYPED, UNPROVEN

### python/tests/test_project_settings_actions.py — 5 КБ
- функции: write(root, rel, text=''); fixture(); agent_dir(root); raises(callback, expected); test_full_schema_digest_and_prepare(); test_invalid_events_fields_and_ranges_are_rejected(); test_addon_and_sequence_policy_are_conservative(); run_all()

### python/tests/test_project_settings_flow.py — 7 КБ
- функции: write(root, rel, text); payload(response)

### python/tests/test_provider_catalog.py — 51 КБ
- функции: check(name, cond)
- константы: CFG, CP, FAKE_API, LIVE_OR, RAW

### python/tests/test_pyinstaller_spec.py — 10 КБ
- функции: check(name, cond, detail=None); read_any(path)
- константы: BAT, PY, SPEC

### python/tests/test_qwen_dual_response.py — 6 КБ
- классы: _FakeCDP(object) — 4 методов
- функции: _created(rid, index); _delta(rid, content, status='typing', phase='answer'); test_dual_interleaved_shows_only_first(); test_second_variant_first_then_primary_wins(); test_old_format_without_response_id(); test_thoughts_follow_primary()
- константы: _R1, _R2

### python/tests/test_qwen_no_double_send.py — 8 КБ
- классы: FakeMon(object) — 2 методов; FakeDriver(object) — 2 методов; FakeEl(object) — 0 методов
- функции: check(name, cond); _boom()

### python/tests/test_rate_limit_sleep.py — 9 КБ
- классы: FakeCdp(object) — 2 методов; Mon(BaseNetMonitor) — 5 методов; P(parser_base.BaseSiteParser) — 1 методов; FakeMonPop(object) — 1 методов
- функции: check(name, cond)

### python/tests/test_release_prepare.py — 27 КБ
- функции: check(name, cond, detail=None); level_of(*subjects); git(root, *args); commit(subject, body=''); release_now(tag); is_version_newer(current_ver, remote_ver); level_of(*subjects)
- константы: ADDON, CFG, COMMITS, OLD_CL, REAL_VERSION, _TOOLS

### python/tests/test_remaining_work_steps.py — 31 КБ
- докстринг: Синтетические тесты остатка плана «Единая точка входа» (задачи 1-5). Здесь проверки, которые не выполнит ни компилятор Godot, ни существующие 109 проверок test_gdscript_wiring.py: каждая задача требуе…
- классы: Suite() — 2 методов; Task1StaticChecks(Suite) — 2 методов; ParseAllScriptsChecks(Suite) — 2 методов; Task2UnifiedFinalizeChecks(Suite) — 2 методов; Task3TargetedRefreshChecks(Suite) — 2 методов; Task4MutationGateChecks(Suite) — 2 методов; Task5EntryPointChecks(Suite) — 2 методов
- функции: strip_comments(text); function_body(text, name); panel_source(addon: Path); run_live(godot: Path); main()
- константы: ADDON, SENTINEL

### python/tests/test_rename_analyze_split.py — 7 КБ
- докстринг: Синтетические тесты п.4.2: разделение поиска и применения. Анализ и запись были слиты в prepare_rename — отсюда «всё или ничего»: одна непроверенная ссылка где угодно убивала многофайловую транзакцию.…
- классы: AnalyzeAndApply(unittest.TestCase) — 14 методов
- константы: PLAYER

### python/tests/test_rename_apply_report.py — 9 КБ
- докстринг: Синтетика: после переименования модель должна знать, ЧТО именно изменилось. Замер (Этап C). После применения модель получает ответ: [Система]: Символ Player безопасно переименован в Avatar (3 файл(ов)…
- классы: ApplyReport(unittest.TestCase) — 12 методов
- функции: _history_storage(); set_storage(store)
- константы: CLEAN, PLAYER, TYPED, UNPROVEN

### python/tests/test_rename_class_and_file.py — 13 КБ
- докстринг: Синтетические тесты п.3.5: class_name + переименование файла и .uid одной транзакцией. Раньше это были два независимых действия (rename_symbol, потом rename_file), между которыми проект оставался в пр…
- классы: ClassNameAndFile(unittest.TestCase) — 19 методов
- функции: _patch_internal(name, replacement); _restore_patched(patched)

### python/tests/test_rename_class_name_strings.py — 13 КБ
- докстринг: Этап 5: строки, которые ДОКАЗУЕМО содержат имя класса. Проблема. `ClassDB.instantiate("Player")` после переименования класса в Avatar гарантированно роняет проект в рантайме: имя класса в строке остал…
- классы: ClassNameStringIsRenamed(unittest.TestCase) — 5 методов; NonClassStringsUntouched(unittest.TestCase) — 8 методов
- функции: _project(files, prefix='stage5_'); _action(**extra); _read(root, rel)
- константы: MIXED, PLAYER, SPAWNER

### python/tests/test_rename_const.py — 12 КБ
- докстринг: Синтетические тесты п.3.1: переименование констант (const). KINDS не содержал const, поэтому любая константа проекта была неприкосновенна для rename_symbol. Здесь проверяем, что const переименовываетс…
- классы: ConstRename(unittest.TestCase) — 19 методов
- константы: UNIT

### python/tests/test_rename_const_exclude_last_usage.py — 7 КБ
- докстринг: Снятие галочек со ВСЕХ ссылок: ядро отказывает, файл не меняется. Симптом (red). Если пользователь снял галочки со всех мест использования, а объявление осталось отмеченным, `prepare_rename` всё равно…
- классы: LastUsageExcludedRenameRefused(unittest.TestCase) — 5 методов
- функции: make_project(prefix)
- константы: ACTION, DECLARATION_LINE, HERE, PY, UNIT, USAGE_LINE

### python/tests/test_rename_const_same_file.py — 7 КБ
- докстринг: Переименование const, объявление и использования которого в ОДНОМ файле. Бывший repro_rename_const_same_file.py. Репро перенесён в трекаемый набор регрессий (run_integration_regressions.py): здесь про…
- классы: SameFileConstRename(unittest.TestCase) — 6 методов
- функции: make_project(prefix)
- константы: ACTION, DECLARATION_LINE, EXCLUDED_LINE, HERE, OTHER_USAGE_LINE, PY, UNIT

### python/tests/test_rename_enum.py — 9 КБ
- докстринг: Синтетические тесты п.3.2: enum и его members. Парсер вообще не знал про enum: и сам тип, и его members не попадали в объявления, поэтому переименовать их было нельзя. Плюс сообщение об ошибке «По dec…
- классы: EnumRename(unittest.TestCase) — 17 методов
- константы: UNIT

### python/tests/test_rename_index_completeness.py — 12 КБ
- докстринг: Этап 4: полнота семантического индекса — сужение отказа с доказательством. План предупреждал: отказ может быть осознанным («не знаем весь проект — не обещаем ничего»), поэтому сузить его можно только …
- классы: UnrelatedBrokenFileDoesNotBlock(unittest.TestCase) — 5 методов; BrokenFileInsideHierarchyStillBlocks(unittest.TestCase) — 3 методов; BrokenFileMentioningSymbolNeedsDecision(unittest.TestCase) — 2 методов; PartialParseIsNotSilentlyTrusted(unittest.TestCase) — 1 методов; CleanProjectUnaffected(unittest.TestCase) — 3 методов
- функции: _project(files, prefix='stage4_'); _clean(**extra); _action(**extra)
- константы: ARENA, BASE, BROKEN_BUT_USABLE, BROKEN_IN_HIERARCHY, MIDDLE, TYPED

### python/tests/test_rename_local_variables.py — 6 КБ
- докстринг: Синтетические тесты п.3.4: локальные переменные внутри функций. Раньше отказ шёл сразу: «Переименование локальных переменных внутри функций пока не поддерживается безопасно». Теперь поддерживается, но…
- классы: LocalVariables(unittest.TestCase) — 14 методов
- константы: SCRIPT

### python/tests/test_rename_name_collisions.py — 7 КБ
- докстринг: Синтетические тесты п.1.4: коллизии нового имени с ClassDB и autoload. Баг: _collision смотрел только объявления в .gd. Проверено пробы: Hero -> Sprite2D (класс движка) и Hero -> GameState (имя autolo…
- классы: NameCollisions(unittest.TestCase) — 13 методов
- константы: CLASSDB

### python/tests/test_rename_nested_members.py — 6 КБ
- докстринг: Синтетические тесты п.3.3: члены вложенных классов. Раньше члены вложенных классов отклонялись outright: «Переименование членов вложенных классов пока не поддерживается безопасно». Правило должно быть…
- классы: NestedClassMembers(unittest.TestCase) — 13 методов
- константы: SCRIPT

### python/tests/test_rename_policy_default.py — 16 КБ
- докстринг: Синтетика: дефолт «переименовывать недоказанные ссылки» не может разъезжаться. Требование, которое зафиксировано этим файлом: * Серверное состояние ДОЛЖНО иметь rename_unverified=None — «решение не пр…
- классы: RenamePolicyUnit(unittest.TestCase) — 8 методов; RenamePolicySource(unittest.TestCase) — 3 методов; RenamePolicyIntake(unittest.TestCase) — 5 методов; RenamePolicyEndToEnd(unittest.TestCase) — 10 методов
- функции: _history_storage(); _action(**extra)
- константы: PLAYER, SERVER, TYPED, UNPROVEN

### python/tests/test_rename_refusal_granularity.py — 30 КБ
- докстринг: Синтетика Этапа 1 «Гранулярность отказа» — вариант (Б), флаг allow_unverified. Требование, которое зафиксировано этим файлом: * `allow_unverified` НЕ в действии (дефолт движка) -> поведение прежнее: н…
- классы: GranularityBase(unittest.TestCase) — 23 методов; FlagTypeStrictness(unittest.TestCase) — 6 методов; HighLevelPath(unittest.TestCase) — 3 методов; PanelSettingDefault(unittest.TestCase) — 5 методов; ExcludeEntryKind(unittest.TestCase) — 8 методов
- константы: DECLARATION, DYNAMIC, PLAYER, SHADOW, SHADOW_OF_CLASS, SUBCLASS, TYPED, UNPROVEN, UNPROVEN_SCORE

### python/tests/test_rename_refusal_kinds.py — 6 КБ
- докстринг: Синтетические тесты п.4.4: типизированные отказы rename_symbol. Отказы сводились к одному RenameError с одним текстом, поэтому и человек, и модель не могли понять, что делать: исправить locator, выбра…
- классы: RefusalKinds(unittest.TestCase) — 12 методов

### python/tests/test_rename_refusal_levels.py — 10 КБ
- докстринг: Синтетические тесты п.2.4: гранулярность отказа (strict/probable/dynamic). Баг: одна непроверенная ссылка где угодно убивала многофайловую транзакцию целиком. Нужен режим, где пользователь осознанно п…
- классы: RefusalGranularity(unittest.TestCase) — 18 методов
- константы: PLAYER

### python/tests/test_rename_scene_connections.py — 12 КБ
- докстринг: Синтетические тесты п.1.2: связи сцен [connection] при rename_symbol. Баг: _collect_scene_property_edits вызывался только для kind == "variable" и правил только строки-свойства. [connection signal="di…
- классы: SceneConnections(unittest.TestCase) — 15 методов
- константы: SCRIPT_WITH_SIGNAL

### python/tests/test_rename_scene_instances.py — 11 КБ
- докстринг: Синтетические тесты п.1.3: свойства в ИНСТАНЦИРУЮЩИХ сценах. Баг: поиск секций шёл только по ext_resource нужного скрипта, поэтому в родительской сцене, где узел — это instance=ExtResource("player.tsc…
- классы: InstancedScenes(unittest.TestCase) — 12 методов
- константы: PLAYER_SCENE, PLAYER_SCRIPT

### python/tests/test_rename_shadowing.py — 7 КБ
- докстринг: Синтетические тесты п.2.3: одноимённые объявления в других файлах. Баг: const Player = preload("res://player.gd") в ЛЮБОМ файле проекта блокировал переименование class_name Player. Для class_name _col…
- классы: ShadowingDeclarations(unittest.TestCase) — 16 методов
- константы: PLAYER

### python/tests/test_rename_string_guard.py — 10 КБ
- докстринг: Синтетические тесты п.2.2: строковый guard различает dynamic-ссылки и текст. Баг: любая строка, равная имени, блокировала переименование. print("Player") и ClassDB.instantiate("Player") давали одинако…
- классы: StringGuard(unittest.TestCase) — 20 методов
- константы: PLAYER

### python/tests/test_rename_symbol.py — 12 КБ
- функции: _patch_internal(name, replacement); _restore_patched(patched); _write(root, rel, text); _read(root, rel); _project(); _action(kind='function', line=5, old='take_damage', new='apply_damage'); test_prepare_apply_and_compound_rollback(); test_stale_hash_writes_nothing(); test_dynamic_and_unknown_references_are_blocking(); test_unqualified_call_in_nested_class_is_not_ours(); test_mid_write_failure_restores_all_files(); test_class_name_and_signal_renames(); test_schema_collision_and_comments_are_safe(); run_all()

### python/tests/test_rename_symbol_flow.py — 4 КБ
- функции: write(root, rel, text); read(root, rel); payload(response)

### python/tests/test_rename_symbol_overrides.py — 12 КБ
- докстринг: Синтетические тесты п.1.1: переименование функции в иерархии наследования. Баг: _find_subclasses вызывался только для kind == "variable". Для функции вызовы в подклассах обновлялись, а сами объявления…
- классы: OverrideHierarchy(unittest.TestCase) — 16 методов
- константы: BASE_SCRIPT, BASE_WITH_SIGNAL

### python/tests/test_rename_transitive_hierarchy.py — 16 КБ
- докстринг: Этап 2: транзитивное наследование КАК ДОКАЗАТЕЛЬСТВО — регресс-барьер. История этапа важнее самого кода. План формулировал цель «self.x() во внуке должен распознаваться» и предполагал, что не распозна…
- классы: TransitiveHierarchy(unittest.TestCase) — 21 методов
- константы: ARENA, BASE, GRANDCHILD_CALLS, GRANDCHILD_OVERRIDE, GRANDCHILD_SHADOW, MIDDLE

### python/tests/test_rename_typed_collections.py — 6 КБ
- докстринг: Синтетические тесты п.2.1: типизированные коллекции Godot 4. Баг: контекст type определялся только по prev in (":", "->", "extends", "as", "is"). В типизированных коллекциях имя класса стоит в квадрат…
- классы: TypedCollections(unittest.TestCase) — 18 методов
- константы: PLAYER

### python/tests/test_rename_usages_checklist.py — 13 КБ
- докстринг: Синтетические тесты п.4.3: список мест с галочками вместо текстовой ошибки. Вместо «найдено N неоднозначностей» панель получает сам список мест с уровнями уверенности и может снять галочки — сервер пр…
- классы: UsagesChecklist(unittest.TestCase) — 18 методов
- функции: history_storage(); set_storage(store)
- константы: ARENA, PLAYER

### python/tests/test_resource_action_flow.py — 9 КБ
- функции: write(root, rel, text); payload(response)

### python/tests/test_resource_actions.py — 8 КБ
- функции: write(root, rel, text='resource'); expect_error(root, action, fragment); fixture(); agent_dir(root); test_full_schema_digest_and_public_payload(); test_schema_limits_paths_and_addon_policy(); test_parser_alias_and_read_only_prepare(); run_all()

### python/tests/test_rollback_by_entry.py — 14 КБ
- классы: RollbackByEntryTests(unittest.TestCase) — 1 методов
- функции: check(name, cond, detail=None); write(rel, text); read(rel); apply_patch(rel, search, replace, chat_id='c1', chat_title='Чат 1', chain_id=None); apply_create(rel, content, chat_id='c1', chat_title='Чат 1', chain_id=None); apply_batch(paths, replacements, chat_id='c1', chat_title='Чат 1')
- константы: EXPECTED_CHECK_COUNT, PROJ, STORE, _PREVIOUS_STORAGE_OVERRIDE

### python/tests/test_runtime_check_flow.py — 7 КБ
- функции: payload(response)

### python/tests/test_runtime_checks.py — 5 КБ
- функции: expect_error(fn, text)

### python/tests/test_runtime_debug.py — 3 КБ
- функции: expect_error(fn, text)

### python/tests/test_runtime_debug_flow.py — 6 КБ
- функции: payload(response)

### python/tests/test_runtime_ownership_live.py — 5 КБ
- докстринг: Dedicated Godot 4.6.1 ownership-refusal and screenshot regressions. Run: python -B python/tests/test_runtime_ownership_live.py --godot EXE --temp-parent DIR Only disposable projects are opened. No gam…
- функции: main()
- константы: SENTINEL

### python/tests/test_runtime_result_http.py — 16 КБ
- докстринг: Runtime result retries through auth, admission, and actual Flask dispatch.
- классы: RuntimeResultHTTPTests(unittest.TestCase) — 15 методов

### python/tests/test_scan_policy_cost.py — 9 КБ
- докстринг: Обход проекта не открывает handle на каждую запись файловой системы. Регрессия 0.8.11: фильтр доступа классифицировал каждую запись несколько раз, и каждый раз через ``os.path.realpath`` (на Windows —…
- классы: ScanPolicyContextParity(unittest.TestCase) — 4 методов; ScanPolicyReparsePoints(unittest.TestCase) — 4 методов
- функции: _write(root, rel, text); _make_project(root, files=120); _make_junction(link, target)

### python/tests/test_scene_action_flow.py — 15 КБ
- функции: write(root, rel, text); payload(response)

### python/tests/test_scene_actions.py — 8 КБ
- функции: write(root, rel, text=''); raises(action, text); fixture(); agent_dir(root); test_full_schema_and_digest_are_deterministic(); test_paths_variants_and_unknown_fields_are_rejected(); test_sequence_and_addon_policy_are_conservative(); test_create_scene_schema_requires_absent_target_and_existing_script(); run_all()

### python/tests/test_search_quality.py — 46 КБ
- докстринг: L2: харнесс качества поиска Библиотекаря (recall@8 / MRR@8). Зачем. Правки L3-L6 (IDF/BM25, структурный тай-брейк, лимит символов, добор MAP) обязаны **улучшать** поиск, а не «казаться лучше». Харнесс…
- классы: MetricsDefinitionTest(unittest.TestCase) — 3 методов; SyntheticRankingTest(unittest.TestCase) — 5 методов; OversizedFileTest(unittest.TestCase) — 4 методов; StructuralTieBreakTest(unittest.TestCase) — 7 методов; MapRerankOrderTest(unittest.TestCase) — 2 методов; PhraseKeysTest(unittest.TestCase) — 5 методов; PathJoinBonusTest(unittest.TestCase) — 3 методов; MapPhraseBonusTest(unittest.TestCase) — 3 методов
- функции: metrics(expected, ranked, k=K); _mean(rows, key); rank_index(root, query, k=K); rank_map(root, query, k=K); load_golden(path=GOLDEN_PATH); _matches(root, golden); find_project(golden, hint_path=None); evaluate(root, golden, rank); summarize(rows); format_report(title, root, golden, rows, stale, misses=8); _write(root, rel, text); main(argv=None); _run_unittest()
- константы: BIG_DECLS, GOLDEN_PATH, K, MAP_PHRASE_SCENE, MAP_PHRASE_SCRIPT, PATH_JOIN_BODY, SYNTH_BOSS, SYNTH_UI, THRESHOLDS, TIE_BOSS_SCENE, TIE_BOSS_SCRIPT, TIE_ENEMY_BASE, TIE_PHRASE_OWNER, TIE_PHRASE_WORD, VARIANTS, _HERE

### python/tests/test_semantic_index.py — 4 КБ
- функции: _write(root, rel, text); test_parser_exact_ranges_and_ignored_text(); test_index_hash_incremental_and_queries(); test_duplicate_owners_remain_distinct(); run_all()

### python/tests/test_server_auth.py — 7 КБ
- функции: check(name, cond, detail=None); post(path, body=None, token=None)
- константы: CFG, TOKEN_A, TOKEN_B, UDD_A, UDD_B, UDD_OLD

### python/tests/test_split_gd.py — 29 КБ
- докстринг: Тесты «пилы» для .gd (split_gd.py): инвентарь, скан ссылок, план, apply. Проверяемый контракт: * file_inventory: extends/class_name/header_end, константы (в т.ч. многострочные и с прилегающим коммента…
- классы: Fixture(unittest.TestCase) — 8 методов; ScanTests(Fixture) — 5 методов; InventoryTests(Fixture) — 4 методов; SuggestGroupsTests(Fixture) — 3 методов; PlanTests(Fixture) — 14 методов; ApplyTests(Fixture) — 9 методов
- константы: ANNOTATED, API_CACHE, DEMO, GROUPS, INVENTORY_TEXT

### python/tests/test_split_gd_flow.py — 6 КБ
- докстринг: Интеграционный тест Flask-роутов «пилы» .gd: scan -> plan -> apply. Контракт, который здесь закрепляется: * scan и plan НИЧЕГО не пишут на диск (plan только кладёт prepared в STATE); * apply пишет мод…
- классы: SplitGdFlowTests(unittest.TestCase) — 8 методов
- константы: DONOR, DONOR_RES, MODULE_RES

### python/tests/test_split_refactor.py — 22 КБ
- докстринг: Тесты «пилы» (split_refactor.py): скан ссылок, инвентарь, план, фасадный apply. Проверяемый контракт: * scan_refs видит импорты (в т.ч. `import x as alias`), строковые упоминания, доки и эвристику «чт…
- классы: Fixture(unittest.TestCase) — 3 методов; ScanTests(Fixture) — 4 методов; InventoryTests(Fixture) — 3 методов; PlanTests(Fixture) — 11 методов; ApplyTests(Fixture) — 8 методов
- константы: DECORATED, DEMO, GROUPS, INVENTORY_TEXT, MINI_MAP

### python/tests/test_string_reference_criterion.py — 10 КБ
- докстринг: Критерий готовности: print("ClassName") не блокирует переименование класса и не переименовывается, а ClassDB.instantiate("ClassName") переименовывается ВМЕСТЕ с классом, потому что по контракту Godot …
- классы: StringReferenceCriterion(unittest.TestCase) — 12 методов
- константы: PLAYER

### python/tests/test_transaction_actions.py — 10 КБ
- функции: write(root, rel, text); read(root, rel); project(); receipt(prepared); test_overlay_sequence_apply_and_full_rollback(); test_move_then_patch_and_stale_receipt(); test_crlf_source_matches_headless_receipt(); test_schema_parser_and_atomic_failure_restore(); test_already_satisfied_transaction_needs_no_validation_or_history()

### python/tests/test_transaction_flow.py — 6 КБ
- функции: write(root, rel, text); read(root, rel); payload(response)

### python/tests/test_tree_excludes_addon.py — 2 КБ
- докстринг: Project scans use canonical policy identities, not mutable global names.
- функции: _make_project(root, wrapper='Godot_agent', inner='godot_agent'); test_agent_name_is_never_added_to_global_exclusions(); test_project_scanner_uses_current_project_policy_identity()

### python/tests/test_updater.py — 15 КБ
- классы: MockGitHubHandler(BaseHTTPRequestHandler) — 2 методов
- функции: check(name, cond, detail=None); parse_semver(v_str); is_version_newer(current_ver, remote_ver); make_test_zip(entries); is_runtime_path(rel); simulate_extraction(zip_bytes, target_dir)
- константы: RUNTIME_DIRS

### python/tests/test_updater_bbcode_live.py — 8 КБ
- докстринг: Живой headless-тест agent_updater.gd: Markdown -> BBCode для панели. Запуск: python -B godot_agent/python/tests/test_updater_bbcode_live.py [--godot EXE] ЗАЧЕМ. test_updater_live.py закрывает сетевую …
- функции: build_script(); run_godot(executable: str, project_dir: Path); collect(output: str); main()
- константы: CASES, FORBIDDEN, SENTINEL

### python/tests/test_updater_live.py — 10 КБ
- докстринг: Real headless Godot test for agent_updater.gd with a mock GitHub HTTP server. Usage: python -B godot_agent/python/tests/test_updater_live.py [--godot EXE]
- классы: MockGitHubHandler(BaseHTTPRequestHandler) — 3 методов
- функции: make_test_zip(entries); main()
- константы: RUNNER_GDSCRIPT, SENTINEL

### python/tests/test_usage_checklist_honesty.py — 7 КБ
- докстринг: Синтетика: чеклист мест не должен обещать то, что не произойдёт. Замер (Этап B). `analyze_rename` — read-only анализ, он не знает ни про allow_unverified, ни про mode. `_usage_checklist` строил галочк…
- классы: ChecklistHonesty(unittest.TestCase) — 8 методов
- функции: _project(prefix, arena=UNPROVEN); _action(**extra)
- константы: CLEAN, PLAYER, TYPED, UNPROVEN

### python/tests/test_v105_attachment_note.py — 5 КБ
- классы: _El(object) — 2 методов; _P(parser_base.BaseSiteParser) — 3 методов; _PEmpty(_P) — 0 методов; _PMulti(_P) — 0 методов
- функции: check(name, cond)

### python/tests/test_v105_net_answer_ready.py — 7 КБ
- классы: _Mon(object) — 6 методов; _BrokenMon(object) — 1 методов
- функции: check(name, cond); _ai(mon, before); _ki(mon, before)
- константы: _AP, _KP

### python/tests/test_v105_spoof_per_site.py — 7 КБ
- классы: _Drv(object) — 1 методов; _P(parser_base.BaseSiteParser) — 1 методов; _POff(_P) — 0 методов; _POn(_P) — 0 методов; _BadDrv(object) — 1 методов; _FakeEl(object) — 1 методов; _QwenLike(parser_base.BaseSiteParser) — 6 методов; _Strict(_QwenLike) — 0 методов
- функции: check(name, cond)

### python/tests/test_v87_1_kimi_cdp.py — 27 КБ
- классы: JavascriptException(Exception) — 0 методов; StaleElementReferenceException(Exception) — 0 методов; WebDriverException(Exception) — 0 методов; Keys() — 0 методов; _FakeCDP() — 1 методов; _FakeElement() — 0 методов; _FakeDriverConfirmSent() — 1 методов; _FakeCDPReadLoopDeadlockCheck() — 4 методов
- функции: test_connect_frame_roundtrip(); test_connect_frame_multi_and_truncated(); test_block_assembly_matches_real_capture(); test_split_text_and_action(); test_split_text_and_action_no_fence(); test_confirm_sent_forwards_element_not_swallowed_by_retries(); test_on_loading_finished_does_not_deadlock_the_read_loop(); test_on_loading_finished_recovers_from_bad_frame_decode(); test_on_loading_finished_resets_generating_when_no_completion_seen(); test_on_loading_finished_failure_does_not_hang_generating_forever(); test_stale_request_body_does_not_clobber_new_request(); _start_stream_request(monitor, req_id='req-1'); test_decode_connect_frames_partial_keeps_tail(); test_streaming_body_captured_live(); test_generating_resets_when_stream_truncated_at_generating(); test_read_loop_survives_socket_silence()

### python/tests/test_v87_9_regen.py — 10 КБ
- классы: _Keys(object) — 0 методов; WebDriverException(Exception) — 0 методов; JavascriptException(WebDriverException) — 0 методов; StaleElementReferenceException(WebDriverException) — 0 методов; NoSuchWindowException(WebDriverException) — 0 методов; TimeoutException(WebDriverException) — 0 методов; _FakeDriver(object) — 1 методов; _FakeRegenParser(BaseSiteParser) — 11 методов
- функции: test_regen_after_timeout(); test_regen_after_empty_answer(); test_no_regen_keeps_old_timeout_behavior(); test_mismatched_composer_is_never_submitted(); test_composer_whitespace_is_semantic(); test_stale_composer_replacement_is_never_submitted(); _run_all()

### python/tests/test_v88_0_aistudio.py — 13 КБ
- классы: _FakeCDP() — 4 методов
- функции: _thought_chunk(text); _answer_chunk(text); _final_chunk(); _start_request(mon, req_id='req-1'); _feed(mon, req_id, data); _wait_not_generating(mon, timeout=5.0); _collect(events); test_full_body_parses_completely(); test_partial_decoder_survives_any_split(); test_no_false_finish_marker(); test_thought_not_mixed_into_answer(); test_monitor_streams_live_and_finishes(); test_monitor_gzip_stream_no_duplicates(); test_truncated_stream_resets_generating(); test_net_fallback_splits_action(); test_insert_verify_matches()
- константы: ANS_1, ANS_2, BODY, EXPECT_ANSWER, MIME, THOUGHT_1, URL, _NET_FULL_SAMPLE

### python/tests/test_v88_11_live_input.py — 10 КБ
- классы: _FakeParser(object) — 2 методов; _FakeEl(object) — 3 методов; _FakeDriver(object) — 2 методов; _MirrorProbe(parser_base.BaseSiteParser) — 7 методов
- функции: _install_selenium_stub(); _mk(parser=None, driver='drv', busy=False, prefer_url=None); test_applies_text(); test_stale_seq_skipped(); test_same_text_rechecks_actual_composer(); test_busy_skipped(); test_no_browser_skipped(); test_parser_error_no_raise(); test_no_input_field_not_cached(); test_bad_seq_and_none_text(); test_base_mirror_input_types_with_keys_not_insert(); test_base_mirror_input_backspace_on_delete(); test_same_text_restored_after_external_clear_without_duplicate_keys(); test_base_mirror_input_no_field_fast_fail(); test_exchange_flag(); _run_all()

### python/tests/test_v88_12_net_confirm.py — 10 КБ
- классы: _FakeTime(object) — 3 методов; _StuckSite(parser_base.BaseSiteParser) — 10 методов
- функции: _install_selenium_stub(); _with_fake_time(fn); test_incident_replay_net_confirmed(); test_presend_baseline_unsticks_without_net(); test_stale_answer_still_rejected(); test_net_confirm_requires_balanced_json(); test_qwen_net_answer_ready_gates(); _run_all()
- константы: NEW_ANSWER

### python/tests/test_v88_13_multi_action.py — 9 КБ
- функции: _install_selenium_stub(); _check(name, cond, detail=''); _block(path, search, replace, summary); test_three_separate_blocks_merge_into_plan(); test_single_block_unchanged(); test_one_bad_block_falls_back_to_last(); test_nested_plan_block_not_merged(); test_dom_path_merges_fenceless_blocks(); test_dom_path_single_block_still_supports_refs_tail(); _run_all()
- константы: _FAILS

### python/tests/test_v88_16_paste_fix.py — 7 КБ
- классы: JavascriptException(Exception) — 0 методов; StaleElementReferenceException(Exception) — 0 методов; WebDriverException(Exception) — 0 методов; Keys(object) — 0 методов; FakeDriver(object) — 5 методов; FakeEl(object) — 4 методов; P(parser_base.BaseSiteParser) — 2 методов
- функции: run_case(name, st, prompt, expect_mode, expect_field=True)
- константы: BKSP, CTRL

### python/tests/test_v88_6_qwen_net.py — 12 КБ
- классы: _FakeCDP(object) — 3 методов
- функции: _install_selenium_stub(); _sse(obj); _build_sse_text(); test_sse_full_decode_and_apply(); test_sse_partial_chunks(); test_ignores_service_events(); test_net_text_splits_action(); test_fs_resave_not_reported(); test_fs_old_format_snapshot_compat(); test_fs_generated_uid_sidecars_are_silent(); _run_all()
- константы: _ANSWER_CHUNKS, _EXPECTED, _THOUGHT_1, _THOUGHT_2

### python/tests/test_v88_7_input_wait.py — 5 КБ
- классы: _FakeDriver(object) — 1 методов; _LateInputParser(BaseSiteParser) — 2 методов
- функции: _install_selenium_stub(); test_input_appears_late_is_found(); test_input_immediate_no_extra_wait(); test_input_never_appears_raises_with_diagnostics(); test_find_input_exception_treated_as_absent(); test_qwen_find_input_js_has_shadow_walk(); _run_all()

### python/tests/test_v88_8_net_first.py — 11 КБ
- классы: _FakeCdp(object) — 1 методов; _FakeMonitor(object) — 6 методов; _NoDomDriver(object) — 1 методов; _StaticDomDriver(object) — 1 методов; _FakeCdpFull(object) — 4 методов
- функции: _install_selenium_stub(); _fresh_parser(mon, before); test_net_first_skips_dom(); test_net_first_requires_new_post(); test_net_first_requires_finished(); test_net_first_incomplete_action_falls_back(); test_live_stream_prefers_net(); test_live_stream_stale_falls_back_to_dom(); test_live_stream_empty_net_falls_back_to_dom(); test_stale_window_live_shows_no_old_text(); test_stale_window_extract_falls_back_to_dom(); test_monitor_buffer_binds_to_post(); test_module_loop_gate_accepts_net_done(); _run_all()
- константы: _NET_TEXT

### python/tests/test_variable_refactor.py — 10 КБ
- классы: TestVariableRefactor(unittest.TestCase) — 12 методов

### python/tests/test_variable_refactor_live.py — 6 КБ
- классы: TestVariableRefactorLive(unittest.TestCase) — 4 методов
- функции: find_godot_executable()
- константы: SENTINEL

### python/tests/test_write_recovery_safety.py — 4 КБ
- докстринг: Fault injection for disk writes and editor transaction recovery.
- классы: WriteRecoverySafety(unittest.TestCase) — 4 методов

## python/tests/data

### python/tests/data/search_golden_yandex_game_dev.json — 20 КБ

## python/tests/fixtures

### python/tests/fixtures/context_menu_callback_live.gd — 5 КБ
- extends: SceneTree
- функции: check, _report, _init

### python/tests/fixtures/context_menu_e2e_live.gd — 5 КБ
- extends: SceneTree
- функции: check, _report, _load_first, _init

### python/tests/fixtures/executor_live.gd — 31 КБ
- extends: SceneTree
- функции: _initialize, _run, _editor_state, check, success, done, write_bytes, _replace_probe, _scene, _settings, resource_roundtrip, _resource_property, _theme, _sprite_frames, _animation, _tileset, _resource_safety

### python/tests/fixtures/executor_receiver.gd — 0 КБ
- extends: Node2D
- функции: on_timeout

### python/tests/fixtures/executor_resource_faults.gd — 3 КБ
- extends: "res://addons/godot_agent/agent_resource_executor.gd"
- функции: _save_temporary_resource, _replace_resource_file, _file_hash, _validate_saved_resource, _write

### python/tests/fixtures/mutation_gate_live.gd — 6 КБ
- extends: SceneTree
- функции: _initialize, _check, _run, _finish

### python/tests/fixtures/scene_reload_guard_live.gd — 6 КБ
- extends: SceneTree
- функции: _initialize, _check, _run

### python/tests/fixtures/script_tab_sync_live.gd — 16 КБ
- extends: SceneTree
- функции: check, _norm, _key, _report, _load_first, _write, _read, _seed, _script_for, _map_clean_editors, _editor_owner, _init

### python/tests/fixtures/test_scene_auto_close_live.gd — 5 КБ
- extends: SceneTree
- функции: check, _initialize, run_live_test

## python/tools

### python/tools/agent_bridge.py — 139 КБ
- докстринг: agent_bridge.py — «альфа MCP» (v0): командный мост между внешней нейросетью и плагином Godot_agent. ЗАЧЕМ. Нейросеть, запущенная снаружи редактора (Cline, Cursor, руки человека), должна получать АКТУА…
- классы: BridgeRefused(ValueError) — 0 методов; BridgeUsage(BridgeRefused) — 0 методов; BridgeInfra(BridgeRefused) — 0 методов
- функции: _say(kind, msg); _finish(rc, msg); _out(text); _find_project_root(start); _project_name(root); _appdata_base(); _user_data_dir(root); _read_token(user_data_dir); _discover_bridge_agent_dir(project_root); _access_policy(opts, project_root, warn=None); _policy_warning_writer(stream_name='stdout'); _access_kwargs(policy); _configure_history_storage(opts, project_root); _addon_dir(); _addon_arg(opts); _http_post(opts, path, payload)
- константы: ACCESS_MODES, CHECK_HEADLESS_EXTENSIONS, CHECK_LINT_MAX_CHARS, CHECK_TEXT_EXTENSIONS, DEFAULT_ACCESS, MAX_REQUEST_BYTES, PLAN_TTL_SECONDS, PROTECTED_AGENT_PARTS, RC_ERROR, RC_NOT_FOUND, RC_OK, RC_USAGE, SEARCH_MAX_ALTERNATIVES, WRITE_EXTENSIONS, _BRIDGE_FOOTER, _COMMANDS

### python/tools/arch_audit.py — 5 КБ
- докстринг: arch_audit.py — сводка архитектуры агента по docs/architecture_map.json. Зачем. Гейт моста (agent_bridge, режим agent-dev) видит только НОВЫЕ файлы; уже накопленные дубли имён он не замечает. Этот скр…
- функции: _print_section(title, rows); main(argv=None)
- константы: MAX_ROWS, RC_ERROR, RC_FINDINGS, RC_OK, _HERE, _PYTHON_DIR

### python/tools/arena_battle_analyzer.py — 12 КБ
- докстринг: Passive Arena Battle network analyzer. Run from ``python/`` while the agent browser is open, then send one message manually in Arena Battle. The analyzer never types, clicks, navigates, or sends reque…
- функции: clean_url(url); report_event(kind, session_id, data); save_report_locked(); stream_summary(raw); configure_session(session_id, info); on_attached(params, _parent_session); on_request(params, session_id); on_response(params, session_id); enable_stream(session_id, request_id); on_data(params, session_id); on_loading_finished(params, session_id); finish_request(session_id, request_id); on_detached(params, _parent_session); connect(); main()
- константы: OUT_FILE, TARGET_MARKER, _HERE

### python/tools/arena_capture.py — 11 КБ
- докстринг: Одноразовый скрипт захвата данных arena.ai для написания парсера. Что делает: 1. Подключается к браузеру агента (Chrome с --remote-debugging-port=9222, профиль %LOCALAPPDATA%\Godot_AI_Profile). 2. Нах…
- функции: log(msg); save_payload(request_id, post_data); decode_sse_chunk(raw_bytes); on_data_received(params); on_loading_finished(params); on_response_received(params); on_request_will_be_sent(params); capture_dom(driver); main()
- константы: CHAT_URL_SUBSTR, DOM_FILE, OUT_DIR, PAYLOAD_FILE, STREAM_FILE, TARGET_URL_SUBSTR, _HERE

### python/tools/audit_aistudio_live.py — 12 КБ
- докстринг: Opt-in AI Studio audit. Uses account quota, an isolated project, and own server. No project files are sent. Chrome uses the normal saved browser profile. Never retries a chat POST. Evidence is stored …
- функции: main()
- константы: HTTP, ROOT

### python/tools/capture_arena_first.py — 8 КБ
- докстринг: Passive first-message Arena diagnostic. Attaches at browser level before a new Arena target is created. It records all Arena POST/response bodies from every attached page target, so it can diagnose th…
- функции: safe_payload(value); log(message); save_records_locked(); record_event(session_id, kind, params, extra=None); on_attached(params, _parent_session); configure_session(session_id, info); on_request(params, session_id); on_response(params, session_id); fetch_body(session_id, request_id); on_loading_finished(params, session_id); on_detached(params, _parent_session); main()
- константы: OUT_DIR, OUT_FILE, TARGET, _HERE

### python/tools/capture_site.py — 12 КБ
- докстринг: Универсальный скрипт захвата сетевого трафика + DOM для НАПИСАНИЯ парсера. Использование: python tools/capture_site.py --site-addr arena.ai --target post-to-evaluation --prefix arena python tools/capt…
- функции: log(msg); sanitize_post(data); detect_decoder(head_bytes); try_decode_text(raw, kind); on_request_will_be_sent(params); on_response_received(params); on_data_received(params); _fetch_body_and_save(req_id); on_loading_finished(params); capture_dom(); main()
- константы: ARGS, CDP, DRIVER, OUT_DIR, _HERE

### python/tools/godot_agent_mcp.py — 32 КБ
- докстринг: MCP-сервер Godot Agent — тонкая обёртка над agent_bridge.py. Сервер НЕ дублирует логику доступа: каждый tool собирает CLI-аргументы и вызывает agent_bridge.main(), а тот решает всё сам (capability-pol…
- классы: _Profile(object) — 3 методов
- функции: _run_bridge(profile, argv); _clip(text, limit=MAX_TEXT); _tool_result(code, text); _request_file(payload); build_server(profile='user', root=None, udd=None, name=None); main(argv=None)
- константы: MAX_ARG_TEXT, MAX_MATCHES, MAX_NAMES, MAX_PATHS, MAX_TEXT, PROFILES, TAIL_KEEP, TRANSPORTS, _DEV_INSTRUCTIONS, _ERROR_CODES, _REFACTOR_RULE, _REQUEST_PREFIX, _SERVER, _SPLIT_TOOL_HINT, _USER_INSTRUCTIONS

### python/tools/make_search_golden.py — 13 КБ
- докстринг: Генератор golden-set для замера качества поиска Библиотекаря (пункт L2). Запуск (на полигоне): python -B -X utf8 godot_agent/python/tools/make_search_golden.py ^ --project D:\vajno\Godot\yandex-game-d…
- функции: _scan(root); _read(root, rel); _decls(root, rels); _words(name); _kind_of(files, kind); _unique(decls, kind, min_len=6, public_only=True); _lost_to_cap(root, rels, decls); build(root); main(argv=None)
- константы: CAP_BASELINE, DEFAULT_OUT, GENERIC, INTENT, LIMITS, _DECL_KINDS, _HERE, _PY

### python/tools/MCP_ALPHA.md — 35 КБ

### python/tools/release_prepare.py — 28 КБ
- докстринг: release_prepare.py - версия и changelog релиза по истории коммитов. ЗАЧЕМ. Релиз Godot Agent собирается вручную: bump в plugin.cfg, текст "что нового", тег, архив для загрузки. Каждый пункт можно забы…
- классы: Commit(object) — 5 методов
- функции: parse_log(raw); read_commits(repo_root, since=None, until=None, limit=None); _git(repo_root, args); _template(table, lang, *args); group_commits(commits, lang='ru'); render_notes(version, previous_version, commits, lang='ru', repo_url=REPO_URL, today=None); _tag(version); render_changelog_section(version, commits, lang='ru', repo_url=REPO_URL, today=None); prepend_changelog(existing, section); read_plugin_version(text); bump_plugin_cfg(text, version); parse_version(text); format_version(parts); bump_version(current, level); resolve_bump_level(commits, override='auto'); list_tags(repo_root)
- константы: BREAKING_RE, BUMP_ORDER, CATEGORIES, CATEGORY_LEVELS, CATEGORY_TYPES, COMPARE_TEMPLATES, CONVENTIONAL_RE, EMPTY_TEMPLATES, FS, HEADING_TEMPLATES, LOG_FORMAT, PREVIOUS_TEMPLATES, REPO_URL, RS, SEMVER_RE, SKIP_MARKERS

### python/tools/verify_aistudio_capture.py — 1 КБ
- докстринг: Проверка захвата AI Studio: декодирует aistudio_2_stream.raw как настоящий парсер.
- константы: _HERE

### python/tools/verify_monitor.py — 3 КБ
- докстринг: Полная проверка: прогон aistudio_2_stream.raw через настоящий AiStudioChatMonitor.
- классы: DummyCDP() — 5 методов
- функции: main()
- константы: CHAT_URL, _HERE

