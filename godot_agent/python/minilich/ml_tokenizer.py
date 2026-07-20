# -*- coding: utf-8 -*-
"""Токенизатор mini-lich: крошечный фиксированный словарь под синтаксис .tscn.

Никакого обучения словаря не требуется: словарь собран заранее — служебные
токены, частые ключевые слова формата .tscn и байтовый fallback (256 байт
UTF-8), поэтому токенизатор понимает ЛЮБОЙ текст без <unk> и без потерь.
Кодирование — жадное сопоставление самой длинной подстроки-ключевого слова,
остальное уходит в байты. Декодирование всегда обратимо.

Зачем так: mini-lich — узкоспециализированная модель поддержки, ей не нужен
словарь на 50k токенов как у больших LLM. Маленький словарь = маленькие
матрицы эмбеддингов = крошечный размер модели на диске.
"""

SPECIALS = ("<pad>", "<bos>", "<eos>", "<sep>", "<think>", "</think>", "<fix>", "<ctx>")

KEYWORDS = (
    "[gd_scene ", "[node ", "[ext_resource ", "[sub_resource ", "[connection ",
    "load_steps=", "format=3", "type=\"", "name=\"", "parent=\"", "instance=",
    "ExtResource(\"", "SubResource(\"", "Vector2(", "Vector3(", "Transform3D(",
    "Color(", "PackedScene", "StandardMaterial3D", "PlaneMesh", "BoxMesh",
    "SphereMesh", "MeshInstance3D", "DirectionalLight3D", "Node3D", "Node2D",
    "CharacterBody3D", "Camera3D", "CollisionShape3D", "WorldEnvironment",
    "Environment", "path=\"res://", "id=\"", "uid=\"uid://", ".tscn", ".gd",
    "script = ", "mesh = ", "transform = ", "position = ", "environment = ",
    "surface_material_override/", "albedo_color = ",
    "unique_id=", "res://", "scenes/", "scripts/",
)


class MiniLichTokenizer:
    """Фиксированный словарь: спец-токены + ключевые слова .tscn + 256 байт."""

    def __init__(self):
        self._tokens = list(SPECIALS) + list(KEYWORDS)
        self._byte_base = len(self._tokens)
        self.vocab_size = self._byte_base + 256
        self._id = {tok: i for i, tok in enumerate(self._tokens)}
        # Ключевые слова, отсортированные по длине — для жадного сопоставления.
        self._kw_sorted = sorted(KEYWORDS, key=len, reverse=True)

    # -- служебные токены -------------------------------------------------
    def special(self, name):
        """id служебного токена по имени, например special("<fix>")."""
        return self._id[name]

    @property
    def pad_id(self):
        return self._id["<pad>"]

    @property
    def eos_id(self):
        return self._id["<eos>"]

    # -- кодирование -------------------------------------------------------
    def encode(self, text):
        """Текст -> список id (без BOS/EOS — их добавляет вызывающий код)."""
        ids = []
        i = 0
        n = len(text)
        while i < n:
            matched = None
            for kw in self._kw_sorted:
                if text.startswith(kw, i):
                    matched = kw
                    break
            if matched is not None:
                ids.append(self._id[matched])
                i += len(matched)
                continue
            for b in text[i].encode("utf-8"):
                ids.append(self._byte_base + b)
            i += 1
        return ids

    # -- декодирование ------------------------------------------------------
    def decode(self, ids, skip_specials=True):
        """Список id -> текст. Служебные токены по умолчанию пропускаются."""
        out = []
        byte_buf = bytearray()

        def flush():
            if byte_buf:
                out.append(byte_buf.decode("utf-8", errors="replace"))
                byte_buf.clear()

        for tid in ids:
            tid = int(tid)
            if tid < 0 or tid >= self.vocab_size:
                continue
            if tid >= self._byte_base:
                byte_buf.append(tid - self._byte_base)
                continue
            flush()
            tok = self._tokens[tid]
            if tid < len(SPECIALS):
                if not skip_specials:
                    out.append(tok)
                continue
            out.append(tok)
        flush()
        return "".join(out)
