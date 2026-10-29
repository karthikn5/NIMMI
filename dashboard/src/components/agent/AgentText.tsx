"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/**
 * The agent's answers: paragraphs, bullet and numbered lists, **bold**, `code` and links. Built as React elements
 * (never as HTML), so nothing in an answer can run. Links inside the dashboard stay in the app; others open in a
 * new tab, and only http(s) links are links at all.
 */
export default function AgentText({ text }: { text: string }) {
    const blocks: ReactNode[] = [];
    let list: { ordered: boolean; items: string[] } | null = null;
    let para: string[] = [];

    const flushPara = () => {
        if (para.length) blocks.push(<p key={blocks.length}>{inline(para.join(" "))}</p>);
        para = [];
    };
    const flushList = () => {
        if (!list) return;
        const items = list.items.map((item, i) => <li key={i}>{inline(item)}</li>);
        blocks.push(list.ordered
            ? <ol key={blocks.length} className="list-decimal pl-5 space-y-1">{items}</ol>
            : <ul key={blocks.length} className="list-disc pl-5 space-y-1">{items}</ul>);
        list = null;
    };

    for (const raw of text.split("\n")) {
        const line = raw.trim();
        const bullet = line.match(/^[-*•]\s+(.*)$/);
        const numbered = line.match(/^\d+[.)]\s+(.*)$/);
        if (bullet || numbered) {
            flushPara();
            const ordered = !!numbered;
            if (list && list.ordered !== ordered) flushList();
            list ??= { ordered, items: [] };
            list.items.push((bullet ?? numbered)![1]);
        } else if (!line) {
            flushPara();
            flushList();
        } else {
            flushList();
            para.push(line.replace(/^#{1,6}\s+/, ""));
        }
    }
    flushPara();
    flushList();
    return <div className="space-y-2 [overflow-wrap:anywhere]">{blocks}</div>;
}

const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

function inline(text: string): ReactNode[] {
    return text.split(TOKEN).filter(Boolean).map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
        if (part.startsWith("`") && part.endsWith("`")) {
            return <code key={i} className="px-1 py-0.5 rounded bg-stone-100 text-[12px] font-mono">{part.slice(1, -1)}</code>;
        }
        const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
        if (link) {
            const [, label, href] = link;
            const cls = "text-plum underline underline-offset-2 hover:text-plum-hover";
            if (href.startsWith("/") && !href.startsWith("//")) return <Link key={i} href={href} className={cls}>{label}</Link>;
            if (/^https?:\/\//.test(href)) return <a key={i} href={href} target="_blank" rel="noopener noreferrer" className={cls}>{label}</a>;
            return <span key={i}>{label}</span>;
        }
        return <span key={i}>{part}</span>;
    });
}
