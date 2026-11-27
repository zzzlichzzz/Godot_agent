# tools/gen_contract.py - генерация contract/*.json из дескрипторов модулей (R-05).
# Использование: python tools/gen_contract.py [--check] [--write]
# Источник правды - ToolSpec в modules/<область>/<фича>/tools.py (ADR-0006);
# contract/capabilities/*.json - сгенерированный артефакт. --check ничего не пишет:
# расхождение артефакта и дескриптора - провал сборки.
# Контракт проверки: последняя строка - JSON {"status": ..., "detail": ...}.

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONTRACT = ROOT / "contract" / "capabilities"
TEMPLATE = "_template.json"


def verdict(status, detail):
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))
    return {"ok": 0, "fail": 1}.get(status, 1)


def rendered():
    """{имя файла: текст} - то, что должно лежать в contract/capabilities/."""
    from python.runtime.module_loader import discover
    from python.protocol.registry import target_alias

    loaded, failed = discover()
    for error in failed:
        if not error['reason'].endswith('нет MODULE (R-05)'):
            raise ValueError('%s: %s' % (error['module'], error['reason']))
    files = {}
    owners = {}
    targets = {item.spec.id for item in loaded if target_alias(item.spec.id, item.spec.provides_tools)}
    targets.update(t.name for item in loaded for t in item.tools)
    for item in loaded:
        unknown = set(item.spec.contributes_to) - targets
        if unknown:
            raise ValueError('%s: unknown contribution target %s' % (item.spec.id, sorted(unknown)))
        capability = (item.spec.capabilities[0] if item.spec.capabilities
                      else item.spec.id)
        for tool in item.tools:
            if tool.name in owners:
                raise ValueError('duplicate tool_name %s: %s, %s' % (tool.name, owners[tool.name], item.spec.id))
            owners[tool.name] = item.spec.id
            payload = tool.contract(item.spec.id, capability)
            files["%s.json" % tool.name] = json.dumps(
                payload, ensure_ascii=False, indent=2) + "\n"
    return files


#: Маркер обработчика примитива в GDScript (R-14). Сверка идёт по нему, а не по
#: договорённости «мы помним, что обработчики есть».
VERB_MARKER = re.compile(r"\s*#\s*verb:\s*([a-z_]+)\s*$")
#: Долг: обработчики появятся вместе с GDScript-сервером (лист механики, PROGRESS).
PENDING = "pending-editor-bridge"


def editor_handlers(root):
    """Имена обработчиков, объявленных маркером `# verb: <name>` в `editor/`."""
    handlers = set()
    editor = root / "editor"
    if not editor.is_dir():
        return handlers
    for source in sorted(editor.rglob("*.gd")):
        text = source.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            marker = VERB_MARKER.match(line)
            if marker:
                handlers.add(marker.group(1))
    return handlers


def schema_problems(item):
    """`result_schema` примитива: объект и тот же набор полей, что в `result`.

    Список имён (`result`) не фиксирует форму элемента: `open_scenes[...]` в части B
    опирается на `revision`/`dirty`, поэтому схема обязательна, а переименование
    поля в ней — смена контракта (бамп `verbs_version`, ADR-0007).
    """
    name = item.get("name")
    schema = item.get("result_schema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return ["editor_verbs.json: %r без result_schema объектного типа" % (name,)]
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return ["editor_verbs.json: %r: result_schema без properties" % (name,)]
    problems = []
    from python.kernel.schema import unknown_schema_types

    # Опечатка в типе (`"date"`) — провал здесь, а не мягкий отказ в вызове
    # инструмента: `validate` считает неизвестный тип невалидным значением.
    problems.extend(unknown_schema_types(schema, "%s.result_schema" % (name,)))
    declared = set(properties)
    listed = set(item.get("result") or ())
    if declared != listed:
        problems.append("editor_verbs.json: %r: поля result_schema %s != result %s"
                        % (name, sorted(declared), sorted(listed)))
    stray = sorted(set(schema.get("required") or ()) - declared)
    if stray:
        problems.append("editor_verbs.json: %r: required вне properties: %s"
                        % (name, ", ".join(stray)))
    return problems


def check_editor_verbs(root):
    """Словарь примитивов: версия, политика, схемы, effects/thread, обработчики.

    Возвращает `(problems, note)`: `problems` — расхождения контракта, `note` —
    разрешённый долг, который обязан быть виден в вердикте. Сверка с кодом идёт по
    маркеру `# verb:`: без маркеров пропуск возможен только при явном `_handlers`,
    и снимается сам, как только появился первый маркер (иначе забытый обработчик,
    опечатка или лишний обработчик проходили бы зелёными).
    """
    path = root / "contract" / "editor_verbs.json"
    if not path.exists():
        return ["contract/editor_verbs.json: нет файла"], ""
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    version = data.get("verbs_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        problems.append("editor_verbs.json: нет verbs_version (целое >= 1)")
    if not str(data.get("_change_policy") or "").strip():
        problems.append("editor_verbs.json: нет _change_policy (правило бампа версии)")
    verbs = data.get("verbs") or []
    names = [item.get("name") for item in verbs]
    if len(set(names)) != len(names):
        problems.append("editor_verbs.json: повтор имени примитива")
    for item in verbs:
        if item.get("effects") not in ("read", "write"):
            problems.append("editor_verbs.json: %r без effects" % (item.get("name"),))
        if item.get("thread") not in ("main", "worker"):
            problems.append("editor_verbs.json: %r без thread" % (item.get("name"),))
        problems.extend(schema_problems(item))
    handlers = editor_handlers(root)
    if not handlers:
        if data.get("_handlers") == PENDING:
            # Долг разрешён, но не спрятан: пропуск обязан быть виден в `detail`.
            return problems, "мост: 0 обработчиков из %d, ожидаются" % len(names)
        if verbs:
            problems.append("editor: нет ни одного обработчика (# verb:)")
        return problems, ""
    if "_handlers" in data:
        # Мёртвый выключатель обязан удаляться, а не жить дальше: иначе он снова
        # выключит сверку при следующей правке словаря.
        problems.append("editor_verbs.json: снимите _handlers: обработчики уже есть")
    missing = sorted(set(names) - handlers)
    extra = sorted(handlers - set(names))
    if missing:
        problems.append("нет обработчика: %s" % ", ".join(missing))
    if extra:
        problems.append("обработчик вне словаря: %s" % ", ".join(extra))
    return problems, ""


def artifact_type_problems(folder=None):
    """Неизвестные типы в схемах записанных артефактов: опечатка = провал.

    `contract/capabilities/*.json` — генерируемый артефакт, но его схемы читают
    клиенты и `protocol/validation.py`, поэтому опечатка в `type` (`"date"`)
    обязана ловиться здесь, а не превращаться в отказ на первом вызове.
    """
    from python.kernel.schema import unknown_schema_types

    problems = []
    folder = CONTRACT if folder is None else Path(folder)
    for path in sorted(folder.glob("*.json")):
        if path.name == TEMPLATE:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # битый артефакт ловится сравнением с дескриптором
        if not isinstance(data, dict):
            continue
        for field in ("input_schema", "result_schema"):
            schema = data.get(field)
            if isinstance(schema, dict):
                problems.extend("%s: %s" % (path.name, item)
                                for item in unknown_schema_types(schema, field))
    return problems


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    options = parser.parse_args(argv[1:])
    try:
        files = rendered()
    except ValueError as exc:
        return verdict('fail', str(exc))
    if not files:
        return verdict("fail", "ни одного ToolSpec не найдено (модули не загрузились)")
    problems, debt = check_editor_verbs(ROOT)
    if problems:
        return verdict("fail", "; ".join(problems))
    CONTRACT.mkdir(parents=True, exist_ok=True)
    stale, missing, written = [], [], []
    for name, text in sorted(files.items()):
        path = CONTRACT / name
        if options.write:
            path.write_text(text, encoding="utf-8", newline="\n")
            written.append(name)
            continue
        if not path.exists():
            missing.append(name)
        elif path.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            stale.append(name)
    if options.write:
        return verdict("ok", "записано: %s" % ", ".join(written))
    extra = [path.name for path in sorted(CONTRACT.glob("*.json"))
             if path.name != TEMPLATE and path.name not in files]
    problems = []
    if missing:
        problems.append("нет артефакта: %s" % ", ".join(missing))
    if stale:
        problems.append("устарел: %s" % ", ".join(stale))
    if extra:
        problems.append("лишний артефакт: %s" % ", ".join(extra))
    problems.extend(artifact_type_problems())
    if problems:
        return verdict("fail", "; ".join(problems))
    tail = " (%s)" % debt if debt else ""
    return verdict("ok", "артефактов %d, расхождений нет%s" % (len(files), tail))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
