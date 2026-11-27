"""Donor doc."""
from __future__ import annotations
import math as m
from pathlib import Path as P
STATE = {}
VALUE = 3
# sticky
def fn():
    return m.sqrt(VALUE)
async def _private():
    return P("x")
class Public:
    pass
__all__ = ["fn", "OLD"]
