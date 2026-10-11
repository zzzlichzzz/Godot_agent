# -*- coding: utf-8 -*-
"""Скан папки n8n/ на строки, похожие на секреты (ключи, токены, пароли).

Зачем. Снимки схемы и скрипты этой папки коммитятся в публичный
репозиторий. n8n хранит ключи в таблице credentials и в workflow-экспорт
их не отдаёт, но подстраховка обязательна: сканер ловит типовые форматы
ключей провайдеров и присвоения секретов, чтобы ключ не уехал в git.

Запуск (из папки n8n):
    python -B scripts/check_no_secrets.py               # вся папка n8n/
    python -B scripts/check_no_secrets.py schemas/template_v2_core_4_channels.json

Коды возврата: 0 — чисто (предупреждения не считаются), 1 — найдены
совпадения форматов ключей (ОШИБКА).
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.normpath(os.path.join(HERE, ".."))

# Форматы ключей провайдеров (OpenAI/DeepSeek/OpenRouter/Groq/Google/Slack/
# GitHub) и присвоения секретов в коде. Каждое совпадение — ошибка.
KEY_PATTERNS = (
    ("ключ провайдера (sk-.../gsk_/xox...)", re.compile(
        r"(?i)\b(?:sk|gsk|xox[bpoa]|gh[pousr])[_\-][A-Za-z0-9_\-]{12,}")),
    ("ключ Google (AIza...)", re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}")),
    ("заголовок Bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("JWT (eyJ...)", re.compile(
        r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}")),
    ("присвоение секрета", re.compile(
        r"(?i)\b(?:api[_-]?key|apikey|secret|password|passwd)\b\s*[:=]\s*"
        r"[\"'][^\"'\s]{12,}[\"']")),
)

# Длинные непрозрачные строки — не ошибка, но повод для глаз: вдруг ключ
# незнакомого провайдера. SHA-256 и UUID — штатные значения схемы.
OPAQUE_PATTERN = re.compile(r"[A-Za-z0-9_\-]{48,}")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
UUIDISH = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

SKIP_DIRS = {".git", "__pycache__"}
TEXT_EXT = {".py", ".json", ".md", ".txt", ".cmd", ".ps1", ".js", ".gd"}


def mask(text):
    """Показать подозрительную строку, не раскрывая её целиком."""
    if len(text) <= 12:
        return text
    return text[:4] + "..." + text[-4:] + " (%d симв.)" % len(text)


def iter_files(targets):
    for target in targets:
        if os.path.isfile(target):
            yield target
            continue
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if os.path.splitext(name)[1].lower() in TEXT_EXT:
                    yield os.path.join(root, name)


def scan_file(path):
    errors, warnings = [], []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        return ["%s: не читается (%s)" % (path, exc)], []
    for num, line in enumerate(lines, 1):
        for label, rx in KEY_PATTERNS:
            for hit in rx.finditer(line):
                errors.append("%s:%d  %s: %s" % (
                    path, num, label, mask(hit.group(0))))
        for hit in OPAQUE_PATTERN.finditer(line):
            value = hit.group(0)
            if HEX64.match(value) or UUIDISH.match(value.lower()):
                continue
            warnings.append("%s:%d  длинная строка: %s" % (
                path, num, mask(value)))
    return errors, warnings


def main(argv=None):
    targets = argv if argv else [DEFAULT_ROOT]
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    errors, warnings = [], []
    for path in iter_files(targets):
        found_errors, found_warnings = scan_file(path)
        errors.extend(found_errors)
        warnings.extend(found_warnings)
    for line in warnings:
        print("ПРЕДУПРЕЖДЕНИЕ  %s" % line)
    for line in errors:
        print("ОШИБКА          %s" % line)
    print("Итог: ошибок %d, предупреждений %d" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
