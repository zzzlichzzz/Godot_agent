# SEC-03: строго ограниченный non-listening probe

## Статус

Отдельный ремонт стража, разрешён пользователем 2026-11-03 после B-1 STOP.
Этап6: проверено, ожидает независимой приёмки. Не механика из44 строк; старые168 тестов и их
судьбы не меняются. B-1 остаётся STOP до независимой приёмки этого ремонта.

## Цель и граница

Исправить false-positive `check_listener`: bind без listen не создаёт
слушателя. Разрешены только `tools/security_audit.py` (классификация SEC-03),
новый `tests/py/security/test_sec03_nonlistening_probe.py`, этот лист,
уточнение SEC-03 в invariants и CRLF ab-append WORKLOG. Другие чеки/гейты,
browser facade/native/corpus,44-таблицы/44reports, контракты и B-2/B-3 frozen.
Новый baseline отдельного ремонта совпал с запечатанным B-1 STOP tree;
прошлый B-1 baseline и досье не переснимаются/не изменяются.

## Спецификация

- Не вводить directory/file-wide allowlist. Исключается только один regex-match
  `.bind(`, доказанный AST, в точном `python/substrate/llm/browser/facade.py`.
- Прямой `ReadOnlyBrowser.__init__` содержит ровно один канонический try:
  `with socket.socket() as probe`, затем только
  `probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)` и
  `probe.bind(('127.0.0.1', 9222))`; except OSError поднимает существующий
  RuntimeError9222 с cause. Нет else/finally, иных действий внутри with.
- Только прямой unaliased `import socket`; socket/probe не переопределяются,
  не захватываются аргументом/импортом/определением, не используются вне блока.
  Динамическая reflection/rebinding поверхность не получает исключение.
- Parse failure, иной адрес/порт/options/контекст, alias/escape/лишний bind →
  прежний SEC-03 отказ. Все `.listen`, `.run`, HTTPServer и другие `.bind`
  (включая совпадения в комментариях/строках) проверяются как прежде.
- HTTP channel location+host правила и прочие SEC-01…SEC-20 не изменяются.
  Это статический классификатор, не Python sandbox и не новая сетевая роль.

## Проверки

Red до guard patch; green новых+старых security; actual-file мутация
исключения и точный restore/green; два security_audit с одинаковым ok/0;
lint_arch/check_limits/gen_contract --check неизменны. Native transport и
фасад100LF/SHA6abe81d…b0b98 frozen; Chrome/Selenium больше не запускать.
selfcheck неприменим: нет ModuleSpec/ToolSpec, контрактный вердикт — реальный
security_audit JSON + focused/full pytest, не фиктивный substrate module.
Отчёты наружу: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/sec03-fix-20261103/`.
SHA256-final.json последний, независимую приёмку делает другой аудитор.

## Следующее действие

Независимый аудитор принимает или отклоняет отдельный SEC-03 ремонт; до этого B-1/live STOP.

Red:58 collected/executed,55pass/3expectedfail,0errors/skips; падают только
канонический LF/CRLF probe и фактический замороженный B-1 фасад. Все55
негативных и прежних HTTP-location/host сценариев уже прошли на старом стражe.
Первый green58/58; дополнительные context/binding пины:71collected/executed,
61pass/10expectedfail,0errors/skips до context patch. Новый helper также не
разрешает decorators/bases/metaclass/type_params и except/match bindings.

## Машинный результат

- Green71/71, collected=executed,0failures/errors/skips.
- Actual-file mutation-projection:68pass/3expectedfail; restore byte-exact и
  green71/71. Mutation-binding:64pass/7expectedfail; restore byte-exact и
  green71/71. Обе через copyfile, без скрытых переключателей в production.
- Окончательный guard318CRLF/0bareLF, SHA256
  `d4679c4c18bb219d5099fef56f49d82261bc0a41c8e962a8cac86ddc6ba92467`.
  После patch восстановлена собственная EOL-дрифтовка; исходные250CRLF и
  все bytes вне ast-import/new-helper/SEC-03 match-selection доказанно точны.
- lint_arch/check_limits/gen_contract --check → ok/0. Два одинаковых
  security_audit → `{"status":"ok","detail":"нарушений нет"}`, exit0.
- Full security239collected/executed,237pass/2прежних Windows symlink skips,
  0failures/errors. B-1+D28 regression93/93,0failures/errors/skips.
- Собственный inert corpus71case, двойной replay71/71 каждый, результаты
  одинаковы; snippet data не исполняется, сокеты/Chrome не создаются.
- Первый внешний battery остановился на corpus import без ROOT в sys.path
  уже после green гейтов/pytest; исходные артефакты сохранены. Fresh-name
  resume_sec03.py повторил всю батарею успешно; production не менялся.
- Boundary:44reports/86UID,4не-pyc fixture-cache sentinel файла точны,
  project.godot/native/B-1 файлы и все bytes вне ремонта frozen. pyc0,
  production cache0;44-таблицы и принятый D28 checker не менялись.
- WORKLOG только binary ab+CRLF, точный prefix693023B из B-1 STOP сохранён;
  `SHA256-final.json` последний во внешнем досье.

Не принят/не ported. Browser stage5 STOP и незавершённая живая батарея остаются;
этот guard repair не доказывает eventual target disappearance или live3/3.
