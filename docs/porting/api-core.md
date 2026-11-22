# API-ядро LLM — рабочий лист

Мандат: `_start-prompt.api-core.md`, SHA fe569426c8e74e8da7bc1b89855ff83c01412a2ba0b9c4c3d665f3c4ca2ff1c4.
Дата: 2026-11-05. Приёмка — независимый аудит, не собственное объявление accepted.
Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/api-core-20261105/.

## Этап 1 — baseline и спецификация ДО кода

§0-recount.json/tree-before.json/closure.json: 4120 файлов, 855 каталогов;
44 canonical reports, 86 UID, 0 pyc, 4 fixture-сентинела; native целиком unchanged.
Новые чужие записи README/WORKLOG и зарегистрированный промпт сохранены;
baseline снята с текущих байтов, не со старых размеров из мандата.
Стабы API 145/145/151 B заменяются только byte-exact native файлами.
11 источников/полные SHA/EOL/AST imports записаны в closure.json и orig-native/.
PROGRESS, остальные parity-строки, contracts, browser facade/transport,
runtime_owner/server_state, прежние эталоны и 44 reports остаются frozen.

### D35 — классовый предел API-verbatim

Только python/substrate/llm/api/** получает FILE_MAX 3400 по образцу D32.
Browser 600/parser 3400/default 400/entry 150 и все area/module caps неизменны.
Нужны тесты положительных и отрицательных границ ДО production-правки;
ровно прежние split_py 11/editing 8400 warning, без новых исключений по файлу.

### D36 — дополнительная DNS-зависимость, решение пользователя

Пересчёт нашёл import doh внутри api_keys.set_dns (1318) и apply_dns_settings
(1344), а не при импорте модуля. Пользователь явно выбрал «Отложить DNS»:
перенести только разрешённые 11 файлов byte-exact, без doh/фиктивного модуля,
оставить эти две функции deferred, не заявлять полноту DNS-приёмки.
Ни внешняя сеть, ни реальные ключи, ни расширение production-мандата не разрешены.
Нативные импорты/функции не исправляются; honest missing dependency тестируется.
Дальнейшая DNS/DoH-работа — отдельный мандат после основного переноса.

### Контракт связки и безопасность

D33 расширяется 11 API aliases только по явному импорту runtime_bindings.
Alias is canonical module; register идемпотентен, чужой alias запрещён;
откат удаляет только новые aliases, существующие сохраняются по identity.
Никаких sys.path/meta_path/PathHook, production-profile/bootstrap регистрации.
Секреты в тестах только синтетические; GODOT_AGENT_CONFIG_DIR установлен
ДО загрузки API в external sandbox; chat_store/api_history paths только sandbox.
Обращение к пользовательским ключам запрещено. DNS/внешние socket targets
блокируются тестовым guard; сетевые данные только fake responses/127.0.0.1.
Корпус фиксирует native inputs/results/errors/side-effects/pins/provenance;
старые тесты — источник кейсов, не копируем/не запускаем их код.
Проверки охватывают SSE/error/UTF8 chunks, Anthropic events, ключи/cooldown,
model cache, catalog enrichment, Markdown, rate-limit, chat/history/budget/lock.
Agent prompts — hash/budget coupling, без смены текста и агентных политик.

### Вердикт и границы

API-core — substrate reference slice, не работающая интеграция HTTP/API-backend.
assistant.history/model_choice не становятся функциональными MODULE/ToolSpec
от одной копии substrate: ported возможен только по доказанному объёму;
не изменять статус из-за копирования, не создавать fake tools/selfcheck reports.
Двойной native/ported корпус, focused ×2, frozen browser regressions, full non-live,
≥2 новых killing mutations + ≥1 reference, exact SHA/EOL restore, четыре гейта.
При red/gate regression/restore mismatch — STOP и сохранение первого evidence.
Текущий вердикт: not_implemented (production ещё не изменён).
Следующее действие: baseline gates/регрессии; снять native корпус в sandbox;
написать новые binding/limits/security/corpus тесты ДО изменения production.

## Продолжение 2026-11-05 — корпус и red

Fresh resume-before: 4128 файлов/856 каталогов; с исходного tree-before
добавлены только этот лист и семь новых test/support-файлов предыдущего чата.
Изменённых/удалённых файлов 0/0; native целиком byte-exact, reports44/UID86/pyc0.
Собственные baseline gates: layers583/0, limits583/2 прежних warning,
contract28/0, securityok/0. Эталонный corpus210: native дважды, все ответы равны;
синтетические ключи/sandbox, fake streams, без внешней сети и пользовательских путей.
До production: collect=executed251, failed239/passed12; JUnit и первые ошибки
сохранены в resume-api-red. D35/D36 и spec-before-code остаются в силе.
Следующее действие: byte-exact11, узкие D35/alias правки, затем green251 и гейты;
при регрессии гейта STOP, не поднимать стадии/ported.


## Продолжение — byte-exact и D37, 2026-11-05

11 файлов скопированы copyfile: 378258 B, все SHA/LF/CRLF равны native.
D35 API cap3400 и 11 aliases добавлены; register implementation не изменён.
Первый green251/251; layers591/0, limits591/2, contract28/0.
SEC-06 затем дал STOP: 120 совпадений только с одним известным синтетическим
Authorization тестового транспорта (не реальный ключ); первое evidence сохранено.
Actual module selfcheck model_choice/history: fail из-за SEC-06, кроме того
MODULE/unit/corpus not_implemented; все44 canonical восстановлены copyfile.

### D37 — разрешённое пользователем маскирование нового наблюдателя

Пользователь явно разрешил только Authorization value -> <redacted>, без
изменения production/security_audit, с архивом первого корпуса и native ×2.
Два новых behavior-пина red2 -> green2; имя/наличие заголовка не удалены.
Native210 ×2 снова равны: изменены только разрешённые Authorization значения
и metadata нормализации; input bytes и другие наблюдения сохранены.
Первый recapture setup ошибочно прочитал input как строку; corpus не изменён,
evidence сохранено, исправлен только внешний runner (input.path), повтор210 ×2.
Focused collect=executed253/253; gates591/0, limits2 прежних, contract28/0,
securityok/0. Досье: d37-authorization-red, d37-recapture-r2, d37-api-green-1,
d37-gates-1. Предшествующий лист восстановлен byte-exact; новые suffix CRLF.
Текущий вердикт: reference-срез реализован, полный регресс/мутации ещё впереди;
assistant модули остаются skeleton, никакой приёмки/ported не назначалось.
Следующее действие: killing mutations на D35/новом alias/reference Markdown,
double focused/full non-live/frozen browser, actual blocked selfcheck и final seal.


## Финал сданного reference-среза — не независимая приёмка

11 immutable native файлов / 378258 B byte-exact; оригинальные импорты/EOL
сохранены. D35: class3400 только API, entry/area caps и два старых warning прежние.
D36: DNS/DoH deferred. D37: Authorization-only маскирование нового наблюдателя.
Corpus210 native ×2 и port ×2 совпали; 11 source byte-pins входят в focused253.
Собственные тесты: limits13 + binding7 + security12 + corpus221 =253.
Полный non-live ×2: collect=executed5874/unique IDs once, passed5872/skipped2,
failures/errors0; два genuine legacy symlink WinError1314 skip, не новые skip.
Оба списка IDs равны, все253 новых IDs входят в full; JUnit SHA — final-metrics.
Замороженный фокус ×2: runtime141 + SEC-03 72 + B-2 17 =230passed каждый.
Пять killing mutations, red counts2/1/1/1/1, после каждой copyfile/SHA/EOL
exact restore и green repeat: D35 boundary, API alias, Markdown bold, SSE DONE
(api-042), key cooldown (api-124). Последние две проверены behavioral corpus,
не source byte-pin. Все сданные reference bytes снова равны native.
Финальные гейты: layers591/0, limits591/2 прежних, contract28/0, securityok/0.

Actual selfcheck assistant.model_choice и assistant.history: blocked/exit2.
module/unit/corpus = not_implemented (нет MODULE/модульных тестов/корпуса);
layers/limits/contract/security = ok. Полные assistant-модули НЕ ported:
это reference substrate, не работающая HTTP/API/backend интеграция.
Fresh selfcheck JSON/логи архивированы внешне; все44 canonical reports exact.
PROGRESS, parity, contract, прежние тесты/эталоны и native не изменены.
tests-map только append API coverage; старые судьбы/владельцы/168строк сохранены.
Новой живой сети/Chrome/Godot не запускали; перенос offline bounded, не live-приёмка.

Deferred: chat_routes/Flask ADR, api_backend после context.runtime_snapshot,
server_state/history_manager, локальные backend/editor-context/minilich, DNS/DoH.
Следующее действие: независимый аудитор проверяет этот лист, final-metrics,
final-seal и SHA256-final во внешнем api-core-20261105; не повышать ported
до отдельного разрешения на MODULE/HTTP/API-backend интеграцию.
## Независимая приёмка аудита — 2026-11-05, сессия 78

Вердикт: **reference-срез принят**; полные assistant-модули НЕ ported (честно).
Независимые проверки аудитора:
- Печать досье api-core-20261105 пересчитана: repository 4347/4347, evidence 12923/12923, 0 bad; репо == tree-after (4347/4347).
- Граница: ровно 8 изменённых (3 замены стабов байтами native, runtime_bindings, check_limits, README/WORKLOG/tests-map) + 227 добавленных (8 api-файлов, corpus 210+manifest, 5 тестов, api-core.md), удалённых 0.
- Пины: 11/11 файлов byte-exact vs native (SHA и побайтово), импорты/EOL сохранены.
- Прогоны: full non-live 5872 pass / 2 legacy skip ×2 (IDs равны), focused 253×2, frozen 230×2 (browser 141 + SEC-03 72 + B-2 17).
- Мутации M1–M5: red 2/1/1/1/1 → green 0 после byte-exact restore, exit 0.
- Гейты: lint_arch 591/0, limits ok/2 (те же 2 legacy), contract 28/0, security ok/0.
- SEC-06 инцидент: честный STOP сохранён; все 120 совпадений = фиксированный синтетический Authorization тестового транспорта; D37 (Authorization-only маскирование нового наблюдателя) одобрен пользователем, recapture ×2 чист, predecessor лист восстановлен byte-exact.
- Гигиена: reports 44, .uid 86, .pyc 0, 4 сентинела fixtures — покрыты печатью.
Отклонение принято: parity L87/L88 остались skeleton — правильнее промпта:
substrate-reference ≠ работающие assistant-модули (MODULE/integration not_implemented,
selfcheck blocked/exit 2), повышение статуса — после отдельных мандатов.
D35 (классовый лимит API 3400), D36 (DNS/DoH deferred), D37 (маскирование) — приняты.
