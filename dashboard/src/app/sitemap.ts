import type { MetadataRoute } from "next";
import { POSTS } from "@/lib/site/blog";

const BASE = "https://nimmiai.in";
const UPDATED = "2026-10-29";  // the public pages' last real change; bump it when one changes

// Public pages only: the app, sign-in pages and the embedded chat window are kept out of search (robots.txt, noindex).
const PAGES: [string, MetadataRoute.Sitemap[number]["changeFrequency"], number][] = [
  ["", "weekly", 1],
  ["/ai-voice-agent", "monthly", 0.9],
  ["/whatsapp-chatbot", "monthly", 0.9],
  ["/ai-chatbot-for-website", "monthly", 0.9],
  ["/lead-management", "monthly", 0.9],
  ["/pricing", "monthly", 0.8],
  ["/solutions/real-estate", "monthly", 0.7],
  ["/solutions/healthcare", "monthly", 0.7],
  ["/solutions/ecommerce", "monthly", 0.7],
  ["/blog", "weekly", 0.6],
];

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    ...PAGES.map(([path, changeFrequency, priority]) => ({ url: `${BASE}${path}`, lastModified: UPDATED, changeFrequency, priority })),
    ...POSTS.map((p) => ({ url: `${BASE}/blog/${p.slug}`, lastModified: p.published, changeFrequency: "yearly" as const, priority: 0.6 })),
  ];
}
