"""Compatibility exports; generic WAL has exactly one pure reader (ADR-0080)."""
from python.kernel.wal_log import (CONFIRM_TTL,STATES,state_of,plan_of,entry_id_of,
                                  next_index,receipts_of,committed_entry,is_expired)
