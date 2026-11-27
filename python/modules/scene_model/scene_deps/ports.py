"""Existing fs structurally supplies these consumer-owned narrow seams."""
from typing import Protocol,Sequence,runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self,rel_path:str)->bytes: ...


@runtime_checkable
class ProjectFiles(RawReader,Protocol):
    def list_files(self)->Sequence[str]: ...
