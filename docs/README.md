# docs

| Файл | Что внутри |
|---|---|
| `PORTING.md` | Цикл переноса механики: корпус → спецификация → тесты → код → живая проверка, DoD |
| `PROGRESS.md` | Этап каждой механики (`0…7`), следующее действие, дата — точка продолжения работы |
| `porting/` | Рабочие листы механик (`<module_id>.md`), шаблон `_template.md`, стартовый промпт `_start-prompt.md` для новой сессии |
| `tests-map.md` | Судьба каждого старого теста (168 файлов): `corpus` / `ported` / `replaced` / `dropped` / `deferred` |
| `architecture.md` | Слои, правило зависимостей, путь вызова, воронка записи, два процесса, модули, ошибки, состояние, тесты, карта папок |
| `mapping.md` | Старый файл → новый модуль: что реально делает по коду, делить или нет, где дубли |
| `inventory.md` | Машинная карта старого плагина (315 файлов): докстринги, классы, функции, импорты |
| `parity.md` | 44 модуля: возможность → модуль → старый код → статус; порядок переноса |
| `WORKLOG.md` | Журнал: что сделано, инциденты, где остановились, промпт для нового чата |
| `NOTES.md` | Наблюдения по старому коду, решения вне ADR, открытые вопросы, риски, идеи |
| `deviations.md` | Осознанные отличия от старого поведения (пока пусто) |
| `adr/0001-moduli-v-papke-plagina.md` | Почему модули и почему внутри папки плагина |
| `adr/0002-dva-processa.md` | Почему GDScript — руки, а Python — голова |
| `adr/0003-kompoziciya-i-porty.md` | Композиция: кто связывает модуль с адаптером, что получает `setup` |
| `adr/0004-vladelcy-i-vklady.md` | Владельцы инструментов и вклады: `provides_tools` / `contributes_to` |
| `adr/0005-tranzakcionnyj-protokol.md` | WAL, квитанции, recovery, stale-check, идемпотентность |
| `adr/0006-kontrakt-istochnik-i-artefakt.md` | `ToolSpec` — источник, `contract/` — артефакт, три разных имени |
| `security/threat-model.md` | Активы, акторы, поверхности атаки, принятые ограничения (R-20) |
| `security/invariants.md` | SEC-01…SEC-20: обещание + способ проверки |
| `security/browser-stealth.md` | Почему браузерная ветка не прячется сильнее: факты старого кода и запреты (R-21) |

Читать в этом порядке: `../RULES.md` → `architecture.md` → `WORKLOG.md` →
`mapping.md` → `parity.md` → `NOTES.md`.


## J1: публичный `judge` (2026-11-15)

`assistant.judge` перенесён и проверен; independent audit pending. Tool `judge` принимает `{"full_text":"...===DONE==="}`, возвращает score/acceptable/vote_eligible, findings/evidence, opaque parsed action и семь structural scores. Только чтение: ничего не применяет. State хранится вне проекта в профиле; raw parser samples не сохраняются.

Проверка: `python tools/selfcheck.py assistant.judge --json`; проба: `python tools/probe.py judge --args-file <owned-answer.json> --project <project>`.

Final: selfcheck ok/exit0×2, corpus74×2/0diff, full7921passed×2 + только2 historical WinError1314 gaps, 14killed/0survivors. Лист: docs/porting/answer-judge.md; ADR0020; final dossier: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-B-20261115/ . NN/browser/editor apply/live — отдельно, не объявлены готовыми.
