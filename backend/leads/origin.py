"""
Where a lead came from, in one shape whatever brought them, so one report can compare them (instagram_plan.md, phase 2). All of it comes from strangers or from a page's
address: only known keys are kept, as short plain text, and the dashboard shows them as text, never as links.
"""
import re
from typing import Optional

LONG = 300
TRACKED = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "gbraid", "wbraid", "fbclid")
AD = ("campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name", "form_id", "form_name", "platform")
KEYS = ("channel", *TRACKED, *AD, "landing_page", "referrer", "ctwa_clid", "headline", "ad_text", "ad_url", "ref", "rule")  # rule: the comment rule that answered
CHANNELS = ("website", "google_ads", "meta_ads", "whatsapp_ad", "instagram_ad", "instagram_link", "instagram_comment", "import")
PAGE = (*TRACKED, "landing_page", "referrer")  # what a page's address and the site before can say


def clean(values) -> Optional[dict]:
    """Known keys only, as short plain text (no control characters). None when nothing is left."""
    if not isinstance(values, dict):
        return None
    out = {}
    for key in KEYS:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            continue
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()[:LONG]
        if text and text != "0":  # Google sends 0 for ids a form doesn't have
            out[key] = text
    if out.get("channel") not in CHANNELS:
        out.pop("channel", None)
    return out or None


AD_CHANNELS = ("google_ads", "meta_ads", "whatsapp_ad", "instagram_ad")
AD_CLICKS = ("gclid", "gbraid", "wbraid", "ctwa_clid", "ad_id")  # not fbclid: Facebook adds it to every link people open from Facebook, ads or not
PAID = ("cpc", "ppc", "paid", "paid_social", "paidsocial", "paid-social", "paid_search", "paidsearch", "cpm", "display")


def from_ad(origin) -> bool:
    """Whether an ad brought them: an ad's own channel, an ad's click id, or the page's tags saying paid (a journey for "any ad")."""
    if not isinstance(origin, dict):
        return False
    if origin.get("channel") in AD_CHANNELS or any(origin.get(k) for k in AD_CLICKS):
        return True
    return str(origin.get("utm_medium") or "").strip().lower() in PAID


def from_widget(given) -> Optional[dict]:
    """What the embed saw on the business's site. Anyone can post to the chat, so only a page's own tags are taken: never an ad's words or ids."""
    if not isinstance(given, dict):
        return None
    return clean({**{k: v for k, v in given.items() if k in PAGE}, "channel": "website"})


def from_fields(fields: dict, channel: str) -> Optional[dict]:
    """A form's or Zapier's fields: the page's own tags, or the ad's."""
    return clean({**fields, "channel": channel})


def from_google(payload: dict) -> Optional[dict]:
    """Google's lead form webhook (developers.google.com/google-ads/webhook/docs/implementation): ad group and creative only for video and discovery ads."""
    return clean({"channel": "google_ads", "campaign_id": payload.get("campaign_id"), "form_id": payload.get("form_id"), "adset_id": payload.get("adgroup_id"),
                  "ad_id": payload.get("creative_id"), "gclid": payload.get("gcl_id")})


def from_instagram(referral) -> Optional[dict]:
    """Meta's referral on an Instagram DM (webhook examples, read 3 November 2026): a Click-to-Direct ad (source ADS: the ad's id and title) or an
    ig.me link (source SHORTLINK: its ref)."""
    if not isinstance(referral, dict):
        return None
    source = str(referral.get("source") or "").upper()
    ad = referral.get("ads_context_data") if isinstance(referral.get("ads_context_data"), dict) else {}
    if source == "ADS" or referral.get("ad_id"):
        return clean({"channel": "instagram_ad", "ad_id": referral.get("ad_id"), "headline": ad.get("ad_title"), "ref": referral.get("ref")})
    if referral.get("ref") or source:
        return clean({"channel": "instagram_link", "ref": referral.get("ref")})
    return None


def from_whatsapp(referral) -> Optional[dict]:
    """Meta's referral on a message from a Click-to-WhatsApp ad: the ad's own words and address, and the click id."""
    if not isinstance(referral, dict):
        return None
    return clean({"channel": "whatsapp_ad", "ad_id": referral.get("source_id"), "ad_url": referral.get("source_url"), "headline": referral.get("headline"),
                  "ad_text": referral.get("body"), "ctwa_clid": referral.get("ctwa_clid")})
