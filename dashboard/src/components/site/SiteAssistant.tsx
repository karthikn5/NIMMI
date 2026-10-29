"use client";

import { useEffect, useState } from "react";
import Script from "next/script";
import { usePathname } from "next/navigation";
import { apiBase } from "@/lib/api";

/**
 * Nimmi's own assistant (NIMMI) on the public site, added the way customers add theirs: the "Add to website" script,
 * backend/static/nimmi-widget.js. Its id is NEXT_PUBLIC_SITE_ASSISTANT_ID (unset: no assistant), so the same code
 * serves a local assistant and the live one. Loaded once the page has finished loading, and never on the dashboard,
 * sign-in, chat or demo pages (hidden again after a move to one of them without a reload).
 */
const ASSISTANT_ID = process.env.NEXT_PUBLIC_SITE_ASSISTANT_ID || "";
const NOT_ON = /^\/(dashboard|auth|widget|demo)(\/|$)/;

export default function SiteAssistant() {
    const onSite = !NOT_ON.test(usePathname() || "/");
    const [origin, setOrigin] = useState("");
    useEffect(() => setOrigin(window.location.origin), []);
    useEffect(() => {
        const widget = document.getElementById("nimmi-widget-container");
        if (widget) widget.style.display = onSite ? "" : "none";
    }, [onSite]);
    if (!ASSISTANT_ID || !onSite || !origin) return null;
    const api = apiBase();
    return (
        <Script id="nimmi-site-assistant" src={`${api}/static/nimmi-widget.js`} strategy="lazyOnload"
                data-bot-id={ASSISTANT_ID} data-api-url={api}
                {...(origin !== "https://nimmiai.in" ? { "data-dashboard-url": origin } : {})} />
    );
}
