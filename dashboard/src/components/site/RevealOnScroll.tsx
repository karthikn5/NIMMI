"use client";

import { useEffect } from "react";

/**
 * Fades elements marked `data-reveal` into place as they enter the viewport.
 * One observer for the whole page; nothing is hidden until it starts (see globals.css).
 */
export default function RevealOnScroll() {
    useEffect(() => {
        const items = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
        if (!("IntersectionObserver" in window) || !items.length) return;
        const observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }
            }
        }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
        // Anything already on screen is shown straight away, so nothing flickers.
        const fold = window.innerHeight;
        for (const el of items) {
            if (el.getBoundingClientRect().top < fold * 0.92) el.classList.add("is-visible");
            else observer.observe(el);
        }
        document.documentElement.classList.add("reveal-ready");
        return () => {
            observer.disconnect();
            document.documentElement.classList.remove("reveal-ready");
        };
    }, []);
    return null;
}
