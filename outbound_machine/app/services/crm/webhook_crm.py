"""
Generic webhook CRM adapter.

Posts lead data as JSON to a configured webhook URL.
Compatible with Zapier, Make, n8n, or any custom endpoint.
Can be used to push to HubSpot, Apollo, Instantly, Smartlead via Zapier.
"""
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from app.config.settings import settings
from app.schemas.lead import LeadPacket
from app.services.crm.base_crm import BaseCrmAdapter, CrmSyncResult

logger = logging.getLogger(__name__)


class WebhookCrmAdapter(BaseCrmAdapter):
    """
    Sends lead packets as POST requests to a webhook URL.
    Configure via CRM_WEBHOOK_URL and CRM_WEBHOOK_SECRET env vars.
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        secret: Optional[str] = None,
        extra_headers: Optional[dict] = None,
    ):
        self.webhook_url = webhook_url or settings.crm_webhook_url
        self.secret = secret or settings.crm_webhook_secret
        self.extra_headers = extra_headers or settings.crm_webhook_headers or {}

    @property
    def name(self) -> str:
        return "webhook"

    def sync_lead(self, lead: LeadPacket) -> CrmSyncResult:
        if not self.webhook_url:
            return CrmSyncResult(
                success=False,
                error="CRM_WEBHOOK_URL not configured",
            )
        if not settings.enable_webhook_sync:
            logger.info("Webhook sync disabled — skipping lead: %s", lead.domain)
            return CrmSyncResult(success=False, error="Webhook sync disabled via ENABLE_WEBHOOK_SYNC")

        payload = self._build_payload(lead)
        headers = {
            "Content-Type": "application/json",
            "X-Outbound-Machine": "1",
            **self.extra_headers,
        }
        if self.secret:
            headers["X-Webhook-Secret"] = self.secret

        try:
            resp = httpx.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            record_id = None
            try:
                response_json = resp.json()
                record_id = str(response_json.get("id") or response_json.get("record_id", ""))
            except Exception:
                pass

            logger.info("CRM sync successful: %s → record_id=%s", lead.domain, record_id)
            return CrmSyncResult(success=True, record_id=record_id)

        except httpx.HTTPStatusError as e:
            error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error("CRM webhook failed for %s: %s", lead.domain, error)
            return CrmSyncResult(success=False, error=error)
        except Exception as e:
            logger.error("CRM webhook error for %s: %s", lead.domain, e)
            return CrmSyncResult(success=False, error=str(e))

    def _build_payload(self, lead: LeadPacket) -> dict:
        """Serialise a LeadPacket to a flat-ish JSON payload for webhook consumption."""
        return {
            "brand_name": lead.brand_name,
            "domain": lead.domain,
            "source": lead.source,
            "vertical": lead.vertical,
            "shopify_detected": lead.shopify_detected,
            "shopify_confidence": lead.shopify_confidence,
            "estimated_sku_range": lead.estimated_sku_range,
            "lead_score": lead.lead_score,
            "lead_segment": lead.lead_segment,
            "mock_opportunity": lead.mock_opportunity,
            "commercial_pain_hypothesis": lead.commercial_pain_hypothesis,
            "imagery_audit_summary": lead.imagery_audit_summary,
            "contact_email": lead.contact_email,
            "contact_name": lead.contact_name,
            "personalised_email_subject": lead.personalised_email_subject,
            "personalised_email_body": lead.personalised_email_body,
            "loom_script": lead.loom_script,
            "review_status": lead.review_status,
            "product_sample_count": lead.product_sample_count,
            "synced_at": datetime.utcnow().isoformat(),
        }
