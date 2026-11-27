"""Фича scene_model.node_rename: предпросмотр переименования узла с правкой скриптов."""

# C.7 public facade: the accepted implementation/settings remain unchanged.
from .domain import diff_preview

preview_diff = diff_preview.preview

__all__ = ['preview_diff']
