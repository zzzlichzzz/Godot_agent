# -*- coding: utf-8 -*-
"""Проверка захвата AI Studio: декодирует aistudio_2_stream.raw как настоящий парсер."""
import sys
import pathlib

# Пути как в capture_site.py — поднимаемся на уровень выше (python/)
_HERE = pathlib.Path(__file__).resolve().parent.parent
for _d in (_HERE, _HERE / "browser", _HERE / "parsers", _HERE / "godot_tools", _HERE / "server"):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import ai_studio_net

raw_file = _HERE.parent.parent / "временно" / "aistudio_2_stream.raw"
if not raw_file.exists():
    print("Файл не найден:", raw_file)
    sys.exit(1)

raw = raw_file.read_bytes()
text = ai_studio_net._bytes_to_text_prefix(raw)
objs = ai_studio_net._decode_chunks_from_start(text)

answer = ""
for obj in objs:
    for t, is_thought in ai_studio_net.extract_parts(obj):
        if not is_thought:
            answer += t

print("=== ОТВЕТ (только ответ, без мыслей) ===")
print(answer)
print("\n=== Длина:", len(answer), "символов ===")

# Сравним с тем, что на экране (пользователь вручную проверит)
# Если ответ совпал — считыватель работает.