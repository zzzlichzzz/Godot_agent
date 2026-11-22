# Долг-срез: закрытие мутационных долгов SEC-03 и B-2 (дёшево, механика)

Класс сложности: **простой** (модель — средняя/дешёвая). Это не новая механика:
закрываются два задокументированных мутационных долга. Роль портера — та же
(WORKLOG, границы, свои прогоны). Вердикт: «долги 1–2 закрыты», не ported/accepted.

## §0 — пересчитать самим (не верить списку)

- `project.godot` 335 B, SHA `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
- `docs/WORKLOG.md` ≈ 721 728 B, SHA начинается с `95b8a2c79b170cca` (если префикс
  ушёл вперёд — найдите фактический и укажите в §0 досье).
- `docs/parity.md` LF, ≈194 строки, SHA начинается с `5d1cec37`.
- reports/selfcheck = 44 json; .uid = 86; .pyc = 0; 4 fixture-сентинела в
  `fixtures/projects/corpus/editing/**/__pycache__/` (ref.gd, ref.gd+ref.gd.uid,
  ref.py) — НЕ трогать.
- Гейты: lint_arch ok/0 (573 файла), check_limits ok/2 (2 прежних warning:
  split_py 11, editing 8400), gen_contract --check 28/0, security_audit ok/0.
- Python 3.14.6; прогоны `python -B -X utf8`, pytest `no:cacheprovider`,
  basetemp/JUnit наружу, `--import-mode=importlib`.

## Долг 1 — SEC-03: reflection-фильтр без независимого мутационного покрытия

Контекст (аудиторская приёмка сессии 78): guard `_exclusive_probe_bind_start`
(`tools/security_audit.py`, SHA начинается `c59e4faf`) возвращает None, если в
файле facade вне канонического candidate-блока встречается `ast.Name` с id из
набора `{"globals","locals","vars","setattr","delattr","__import__","__builtins__"}`
(строка вида `node.id in {"globals", ...}`). Мутация этого набора в `set()`
выживает на текущем тест-наборе: все существующие кейсы дублируются другими
фильтрами. Репро аудитора доказало, что фильтр — единственная отсечка для
поверхности с динамически собранным именем.

Задача:
1. В `tests/py/security/test_sec03_nonlistening_probe.py` добавить ОДИН кейс
   `test_reflection_built_name_is_the_only_deny`: тот же каркас, что у
   существующих кейсов (tmp_path + monkeypatch ROOT/PY/LISTEN_ALLOWED), файл
   `substrate/llm/browser/facade.py`, внутри `__init__` ДО канонического probe:
   `globals()['soc' + 'ket'] = fake_socket_impl`. Утверждение: `denied(...)`
   (тот же helper, что у соседей).
2. Прогон до мутации: новый кейс зелёный, весь файл зелёный (73+1).
3. Мутация на актуальном guard (копия файла на бэкап, копи-файл):
   `in {"globals", "locals", "vars", "setattr", "delattr", "__import__", "__builtins__"}`
   → `in set()`. Ожидание: НОВЫЙ кейс красный (и только он по смыслу; допустимо
   1–2 соседних, перечислить), restore byte-exact → файл снова зелёный.
4. Записать в лист `docs/porting/browser-sec19.md`? НЕТ — в
   `docs/porting/browser-sec19.md` D30-заметка не касается; запись долга — в
   хвост `docs/porting/browser-sec19.md` НЕ добавлять. Использовать
   `docs/WORKLOG.md` (append CRLF) и append в лист сек 03 — `docs/porting/browser.md`
   НЕ трогать; короткий append в `docs/porting/browser-sec19.md` разрешён
   (раздел «Долг закрыт»), потому что фильтр принадлежит D30-семейству. Иначе —
   только WORKLOG. Выбор зафиксируйте в вердикте.

## Долг 2 — B-2: pop_http_error «однократно» без независимого кейса

Мутация аудита приёмки B-2: удалить сброс `self._last_http_error = None` из
`pop_http_error` (`python/substrate/llm/browser/net_monitor.py`, byte-exact
native 24206 B / SHA `54167afbb87d9a9bf862df0a74c5a7bd24bb129661968682201c329d4297866b`)
— выжил: корпус не отличает «ошибка сброшена» от «ошибка осталась».

Задача:
1. В `tests/py/browser/test_browser_b2_net_monitor.py` добавить кейс
   `test_pop_http_error_is_one_shot`: через существующие helpers
   (make_monitor/apply_step/snapshot) выполнить сценарий: request → ответ с HTTP
   ошибкой (как в корпусном кейсе pop_http_error) → `wait_done` →
   `snapshot().pop_http_error()` возвращает ненулевую ошибку РОВНО один раз,
   повторный `snapshot().pop_http_error()` — None (сброс сработал).
2. Прогон до мутации: новый кейс зелёный, файл зелёный (16+1).
3. Та же мутация аудита (удаление сброса из pop_http_error) → новый кейс
   красный; restore byte-exact (SHA net_monitor должен вернуться в
   54167afbb87d…) → файл зелёный.
4. Append «Долг закрыт» в `docs/porting/browser-b2.md`.

## Границы

Менять/создавать: два тест-файла, `docs/WORKLOG.md` (append CRLF,
`ab`-драйвером), два листа (короткие append «долг закрыт»), досье
`%TEMP%\opencode\c8_audit\debt-cases-<дата>\` (tree-снимки до/после, SHA-печать
последним). ЗАПРЕЩЕНО: production (`net_monitor.py`, `security_audit.py`, фасад,
transport), корпус, контракт, parity, PROGRESS, таблица 44, гейты, native,
прочие листы. Сентинелы фикстур не трогать. Chrome/Selenium/профили не запускать.

## Порядок

1. §0 пересчёт → tree-снимок до.
2. Долг 1: красный кейс → (мутация) → зелёный → restore.
3. Долг 2: красный кейс → (мутация) → зелёный → restore.
4. Гейты ×4 повторно + focused прогон обоих файлов; full security не требуется
   (тесты не трогают production), но security_audit ×2 ok/0 подтвердить.
5. WORKLOG append (префикс из §0, tail чисто CRLF), SHA-печать досье последней.
6. Вердикт: «долги 1–2 закрыты» + числа (tests totals, mutation reds, restore SHA).

## Стоп-условия

- Мутация не красит новый кейс → стоп, не «подгонять тест под мутацию».
- Гейт ok→fail → стоп. SHA net_monitor/guard после restore ≠ исходному → стоп.
- Оказалось, что reflection-фильтр уже покрыт (новый кейс зелёный и у мутанта) →
  стоп и честный вердикт «долг не воспроизводится».
