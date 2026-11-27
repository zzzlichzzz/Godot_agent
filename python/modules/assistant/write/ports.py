"""Consumer-owned preparation port; native executor never granted write authority."""
from typing import Protocol
class NativePrepare(Protocol):
    def prepare(self,action:dict,*,allow_addons:bool=False,allow_self_edit:bool=False)->dict: ...
