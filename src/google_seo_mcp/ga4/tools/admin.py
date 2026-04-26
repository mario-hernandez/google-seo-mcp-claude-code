"""Admin API tools — list properties, accounts, custom dims, etc."""
from __future__ import annotations

from ...auth import get_admin_client, normalize_property
from ...guardrails import with_meta


def list_properties() -> dict:
    """List every GA4 account + property the authenticated user has access to.

    Returns a flat structure with account name, property id, display name, time zone,
    currency, and create time.
    """
    admin = get_admin_client()
    out = []
    for summary in admin.list_account_summaries():
        for ps in summary.property_summaries:
            out.append({
                "account": summary.account,
                "account_display_name": summary.display_name,
                "property": ps.property,
                "property_display_name": ps.display_name,
                "property_type": ps.property_type.name if ps.property_type is not None else None,
            })
    return with_meta(out, source="admin.account_summaries.list", property="*")


def get_property_details(property_id: int | str) -> dict:
    """Fetch detailed metadata for one GA4 property: timezone, currency, industry, etc."""
    admin = get_admin_client()
    pid = normalize_property(property_id)
    p = admin.get_property(name=pid)
    return with_meta(
        {
            "name": p.name,
            "display_name": p.display_name,
            "industry_category": p.industry_category.name if p.industry_category is not None else None,
            "time_zone": p.time_zone,
            "currency_code": p.currency_code,
            "create_time": p.create_time.isoformat() if p.create_time else None,
            "update_time": p.update_time.isoformat() if p.update_time else None,
            "service_level": p.service_level.name if p.service_level is not None else None,
            "account": p.account,
        },
        source="admin.properties.get",
        property=pid,
    )
