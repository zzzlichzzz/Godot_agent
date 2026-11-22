# modules/code_intel/shared/symbol_index.py - индекс символов по файлам проекта.
"""S2 поиска использований: проект -> разбор каждого `.gd` (R-02, R-11).

Эталон строил снимок через `minilich/ml_project_index.semantic_snapshot`:
кэш на диске, `numpy`, обучение. Сюда перенесён только СМЫСЛ снимка — «файлы,
sha256 и семантические факты»; кэша нет, индекс собирается на каждый вызов
(дорого — это долг в `PROGRESS.md`, а не повод строить кэш внутри среза).

Обход идёт через порт `fs` (не `os.walk`), права — через `PathPolicy`.
Разбор — `formats/gdscript`, единственный парсер `.gd` в агенте.
"""

import hashlib

from python.formats import gdscript

#: Индексируются только скрипты: сцены и данные разбирает другой формат.
SCRIPT_EXT = ".gd"
RES_PREFIX = "res://"


def build(fs, policy):
    """Индекс проекта: `{"files": [...], "skipped": [...]}`.

    Элемент файла: `path` (`res://`), `rel`, `sha256`, `text`, `declarations`,
    `references`, `strings`, `parent_path`, `parent_class`. Объявления
    получают `path` и `sha256` файла — по ним locator находит единственное
    совпадение, не зная про индекс.
    """
    files, skipped = [], []
    for rel in fs.list_files():
        if not str(rel).lower().endswith(SCRIPT_EXT):
            continue
        if policy is not None and policy.deny_reason(rel):
            skipped.append(rel)
            continue
        try:
            text = fs.read_text(rel)
        except OSError:
            # Нечитаемый файл — не повод валить поиск: он честно в `skipped`.
            skipped.append(rel)
            continue
        files.append(_entry(rel, text))
    return {"files": files, "skipped": skipped}


def _entry(rel, text):
    path = RES_PREFIX + rel
    semantic = gdscript.parse(text, path)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    parent_path, parent_class = gdscript.script_parent(text, path)
    declarations = [dict(item, path=path, sha256=digest)
                    for item in semantic["declarations"]]
    return {
        "path": path,
        "rel": rel,
        "sha256": digest,
        "text": text,
        "declarations": declarations,
        "references": semantic["references"],
        "strings": semantic["strings"],
        "parent_path": parent_path,
        "parent_class": parent_class,
    }


def declarations(index):
    """Все объявления проекта одним списком (по нему ищет locator)."""
    found = []
    for entry in index["files"]:
        found.extend(entry["declarations"])
    return found


def entry_for(index, path):
    """Запись файла по `res://`-пути или None."""
    return next((item for item in index["files"] if item["path"] == path), None)


def class_name_for(entry):
    """Имя `class_name` файла, если оно ровно одно (иначе None)."""
    names = [item["name"] for item in entry["declarations"]
             if item["kind"] == "class_name"]
    return names[0] if len(names) == 1 else None


def subclasses(index, target_path, target_class):
    """Файлы, наследующие `target_path` или `target_class` (транзитивно).

    Эталон ради `extends` читал каждый файл заново; здесь факт `extends` уже
    снят при сборке индекса, поэтому иерархия считается по данным.
    """
    class_of = {item["path"]: class_name_for(item) for item in index["files"]}
    found = set()
    queue = [target_path]
    target_classes = {target_class} if target_class else set()
    while queue:
        current = queue.pop(0)
        if class_of.get(current):
            target_classes.add(class_of[current])
        for entry in index["files"]:
            child = entry["path"]
            if child in found or child == target_path:
                continue
            if (entry["parent_path"] == current
                    or (entry["parent_class"] and entry["parent_class"] in target_classes)):
                found.add(child)
                queue.append(child)
    return found
