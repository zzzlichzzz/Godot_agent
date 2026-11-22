"""Фича verification.gd_lint: синтаксис и подозрительные места .gd."""

# Explicit public pure-text service; runtime binds C.6's consumer-owned callable.
from .domain.core import lint_gdscript

__all__ = ('lint_gdscript',)
