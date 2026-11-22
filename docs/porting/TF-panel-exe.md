# T-F — панель, локальный exe, observer

Мандат: [_start-prompt.TF-panel-exe.md](_start-prompt.TF-panel-exe.md).
Рабочая копия: `agent-rebuild/addons/godot_agent`; установленная копия и
замороженные источники только читаются. Независимая приёмка не заявляется.

## Цель и источники

- 27 недостающих маршрутов, постоянная защита 51 URL замороженной панели.
- `main.py` из `agent-backups/20261122/godot_agent_native_original/godot_agent/python/`
  — источник payload/ответов/порядка, не production-код.
- `agent_panel_part1.gd:925` отправляет `approved`, иногда `exclude` и semantic
  proof, но НЕ `plan_id/digest`; требуется привязка к immutable server pending.
- `agent_server_link.gd:489–580` запускает exe БЕЗ аргументов; приоритетный
  путь onedir; выбран его точный onefile fallback
  `python/dist/godot_agent_server.exe`, native порт 5000 (D95).
- `agent_server.gd:183` создаёт токен панели в project user-data; native
  `server_auth.py` читает/связывает его, не создаёт (уточнение текста мандата).
- Observer: разрешено только исправление `extends` rebuild-only обёртки.

## Ограничения

ProjectAuth, Host/Origin, startup policy, WAL/explicit confirmation сохраняются.
Никакой внешней сети, живых ключей/провайдеров, NN/DoH/n8n. Frozen `.gd` и
принятые Python references неизменны. Досье T-A/T-B не восстанавливать.
История D01–D89: `../deviations.md`; новые D90+ по пути мандата:
`deviations.md` (этот путь ранее отсутствовал — дефект документации раскрыт).

## Состояние

Этап 7, исполнительский checkpoint; независимая приёмка не заявляется.

- Observer D90: live RED → same ID GREEN ×2; Godot4.6.3 check-only ×2.
- 27 новых routes / 51 frozen URLs; native card/confirm/auth/digest/WAL
  RED91/116 → same ordered116 GREEN ×2; bootstrap RED7 → GREEN7 ×2;
  positive services7 ×2; cross-plan stale/reject RED2 → GREEN2 ×2.
- D97 hardlink5 + D98 input-only revision4: RED9 → same IDs GREEN ×2,
  прежний observer differential ID GREEN ×2. Старые tests/manifests и все
  бизнес-goldens неизменны; source revision допускает только extends delta.
- Final state full: **8425 passed +2 historic WinError1314 skips ×2**,
  ordered T-E/T-F IDs и setup/call/teardown exact. Gates4 ×2 и genuine
  selfchecks7 ×2 `ok` с complete accepted K1c offline hook.
- Final submitted-code auth/digest/direct-effect mutants3 killed; exact
  bytes/SHA/EOL restored. Offline exe build5/R6 full socket cycles ×2 и
  zero-arg5000 smoke; real WAL/physical rollback/auth, cache hardlink403,
  normal external cache200, shutdown200, retained Win32 child и launcher0,
  owned endpoint removed, token exact; production source membership/pins exact.
- Installed/native unchanged, T-E fixture pins exact; measured extra UID171
  сохранены byte-exact вне проекта и удалены. Единственная `.gd` delta — D90.
  WORKLOG prefix1082333/6c32e0b79a2e88f7 подтверждён; optional recovery не было.

Не закрыты issued runtime/editor execution, protected split apply и automatic
post-move sync (D92/D93); NN F0. Нет live-provider/browser паритета или
расширения stealth. Возможны AV/SmartScreen предупреждения об unsigned exe.

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/tf-20261122/`.
Заключительная публикация выполняется seal LAST, затем только sibling ZIP и
`tf-20261122-postseal/publication.json`. Фактический seal/ZIP/bad0 статус берётся
из этого внешнего receipt, не дописывается в запечатанное досье (D99).

Упаковка остановилась до seal на365 owned diagnostic junctions. Первый retry
остановился до detach из-за extended-prefix comparison; script/snapshot сохранены.
D100: свежий `final/dossier-links-retry-01/` фиксирует raw NTFS buffers и identities;
разрешено удалять только measured link entries, не цели и не обычные файлы.
Выполнено:365 link entries detached, links_remaining=0; все исходные ordinary
bytes/SHA/EOL, directory membership и target identities сохранены. Старые final
manifests/checkpoint сохранены byte-exact перед обновлением; production не менялся.

Следующее действие: независимый аудитор проверяет пакет/ограничения D90–D100
и внешний publication receipt; он отдельно решает о приёмке и installed git copy.
До передачи исполнитель обновляет final identity/checkpoint, выполняет seal LAST
и sibling ZIP; их фактический статус берётся только из publication receipt.
