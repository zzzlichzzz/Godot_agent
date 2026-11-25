# ADR-0093: HTTP Chat Prompt Envelope, Fail-Closed Panel Policy, and Scene UID Alignment

- **Status**: Accepted (2026-11-25)
- **Extends**: ADR-0090, ADR-0091, ADR-0092

## Context
Live editor testing with Godot 4.6.3 and DeepSeek (`godot_agent_server.exe`) surfaced four compounding defects:
1. Existing profiles with `"1"` in `user://godot_agent_policy.txt` caused `agent_panel_part1.gd` (`_load_policy_settings`) to initialize `_allow_addons = true` and inject `"allow_addons": true` into every POST request (`_policy_body` / `_policy_json`). Meanwhile, `python/channels/http/auth.py` (ADR-0091) stripped UI policy metadata only on 14 `_CONTROL_POSTS` routes, rejecting `/chat/live_input` (`BUG-009`), `/chat`, `/chat/stop`, `/server/shutdown`, `/chat/rollback/preview`, and `/minilich/*` with `403 HTTP cannot elevate startup policy`. Moreover, `agent_panel_part4.gd` kept HTTP elevation checkboxes enabled even though the rebuilt HTTP server intentionally enforces `allow_addons=False, allow_self_edit=False` (`SEC-HTTP-CONTROL`).
2. `python/channels/http/routes_chat.py` read `body.get('message', body.get('text', ''))` on `POST /chat`, ignoring the `'prompt'` field sent by `agent_panel_part1.gd:_send_chat_raw`, causing Godot panel sends to fail with `400 (аргументы).text: короче 1 символов`. `GET /chat/progress` also omitted `'active'` expected by `agent_panel_part3.gd`.
3. `python/runtime/panel_services.py:live_input` inspected only `gateway._record` (populated lazily on the first `/chat` turn) rather than falling back to `gateway._selection()`, so live typing immediately after `/chats/new` for DeepSeek or API chats resolved `'qwen'` instead of the selected site/API record.
4. Seven `.tscn` scenes in `editor/native/` (`UserMessageCard.tscn`, `AgentMessageCard.tscn`, `DiffPreviewCard.tscn`, `PlanChecklistCard.tscn`, `PlanStepItem.tscn`, `ToolCallCard.tscn`, `agent_panel.tscn`) had stale script `uid://` attributes mismatching their `.gd.uid` files, triggering Godot 4.6 engine warnings on load.

## Decision
1. **Preserve Strict ADR-0091 Auth Envelope (`python/channels/http/auth.py`)**: Keep `_CONTROL_POSTS` unchanged (14 exact control-plane routes) so all project/action routes (`/chat`, `/chat/live_input`, `/chat/stop`, `/server/shutdown`, `/minilich/*`, `/init`, `/tools/call`, `/project/*`, lookalikes) continue rejecting any HTTP `allow_addons=True`/`allow_self_edit=True` elevation attempt with `403` (`SEC-TF`, `SEC-HTTP-CONTROL`).
2. **HTTP Chat Adapter & Live Mirror (`routes_chat.py`, `panel_services.py`)**:
   - Accept `'prompt'` alongside `'message'`/`'text'` on `/chat` (preferring explicit `'message'`, then `'prompt'`, then `'text'`).
   - Include `active=session.busy` alongside `ok`, `busy`, `pending_confirmation` on `GET /chat/progress`.
   - Resolve active record in `PanelServices.live_input` from `gateway._record` or `gateway._selection()`, return `None` site for `kind == 'api'`, and unwrap `getattr(module, 'PARSER', module)` so `LiveInputMirror` receives the `BaseSiteParser` instance exposing `mirror_input`.
3. **Fail-Closed Godot Panel Policy (`D116`) & Scene UIDs**:
   - In `editor/native/agent_panel_part1.gd`, initialize `_allow_addons = false` and `_allow_self_edit = false` fail-closed regardless of legacy `user://godot_agent_policy.txt`, and prevent Settings toggles from setting HTTP elevation flags (`_allow_addons_check` and `_allow_self_edit_check` disabled in `agent_panel_part4.gd`, RU/EN tooltips updated in `agent_locale.gd`).
   - Record exact inverse-verified input hashes for `agent_panel_part1.gd`, `agent_panel_part4.gd`, and `agent_locale.gd` under `D116` (`tests/py/panel_tf/source_inputs.py`, `tests/conftest.py`) without altering extraction goldens.
   - Align script `uid://` references in all 7 `editor/native/*.tscn` scenes to their `.gd.uid` sidecars.

## Consequences
- Users with existing `godot_agent_policy.txt = "1"` can create DeepSeek/API chats, mirror live input, send chat prompts, inspect progress, and shut down cleanly without spurious `403`/`400` failures, while HTTP policy escalation stays strictly closed (`SEC-HTTP-CONTROL`).
- Godot loads all native dock and card scenes with zero UID warnings.
