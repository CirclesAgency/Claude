"""
CRM sync abstraction layer.

Defines the interface all CRM adapters must implement.
Add HubSpot, Apollo, Instantly, Smartlead adapters by subclassing BaseCrmAdapter.
"""
from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.lead import LeadPacket


class CrmSyncResult:
    def __init__(self, success: bool, record_id: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.record_id = record_id
        self.error = error

    def __repr__(self):
        return f"CrmSyncResult(success={self.success}, record_id={self.record_id})"


class BaseCrmAdapter(ABC):
    """All CRM adapters must implement this interface."""

    @abstractmethod
    def sync_lead(self, lead: LeadPacket) -> CrmSyncResult:
        """Push a single lead to the CRM. Returns a CrmSyncResult."""
        ...

    def sync_leads(self, leads: list[LeadPacket]) -> list[CrmSyncResult]:
        """Sync a list of leads. Default implementation calls sync_lead in a loop."""
        return [self.sync_lead(lead) for lead in leads]

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""
        ...
