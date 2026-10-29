"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/**
 * The agent's answers: paragraphs, headings, bullet and numbered lists, tables, **bold**, `code` and links. Built as
 * React elements (never as HTML), so nothing in an answer can run. Links inside the dashboard stay in the app; others
 * open in a new tab, and only http(s) links are links at all. Nimmi is asked for no tables (the panel is narrow), but
 * a model may still send one: it scrolls sideways inside the answer rather than showing raw pipes.
 */
const SEPARATOR = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/;
const cells = (line: string) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export default function AgentText({ text }: { text: string }) {
    const blocks: ReactNode[] = [];
    let list: { ordered: boolean; items: { text: string; nested: boolean }[] } | null = null;
    let para: string[] = [];

    const flushPara = () => {
        if (para.length) blocks.push(<p key={blocks.length}>{inline(para.join(" "))}</p>);
        para = [];
    };
    const flushList = () => {
        if (!list) return;
        const items = list.items.map((item, i) => <li key={i} className={item.nested ? "ml-4 list-[circle]" : undefined}>{inline(item.text)}</li>);
        blocks.push(list.ordered
            ? <ol key={blocks.length} className="list-decimal pl-5 space-y-1">{items}</ol>
            : <ul key={blocks.length} className="list-disc pl-5 space-y-1">{items}</ul>);
        list = null;
    };

    const lines = text.split("\n");
    for (let n = 0; n < lines.length; n++) {
        const raw = lines[n];
        const line = raw.trim();
        // A table: a row of cells, the |---| line, then its rows.
        if (line.startsWith("|") && SEPARATOR.test((lines[n + 1] ?? "").trim())) {
            flushPara();
            flushList();
            const head = cells(line);
            const rows: string[][] = [];
            n += 2;
            while (n < lines.length && lines[n].trim().startsWith("|")) rows.push(cells(lines[n++]));
            n--;
            blocks.push(
                <div key={blocks.length} className="-mx-1 overflow-x-auto">
                    <table className="min-w-full border-collapse text-[12.5px]">
                        <thead><tr>{head.map((h, i) => <th key={i} className="border-b border-line px-1.5 py-1 text-left font-semibold">{inline(h)}</th>)}</tr></thead>
                        <tbody>{rows.map((r, i) => (
                            <tr key={i}>{head.map((_, j) => <td key={j} className="border-b border-line/60 px-1.5 py-1 align-top">{inline(r[j] ?? "")}</td>)}</tr>
                        ))}</tbody>
                    </table>
                </div>);
            continue;
        }
        const heading = line.match(/^#{1,6}\s+(.*)$/);
        if (heading) {
            flushPara();
            flushList();
            blocks.push(<p key={blocks.length} className="font-semibold">{inline(heading[1])}</p>);
            continue;
        }
        const nested = /^\s{2,}\S/.test(raw) && !!list;  // an indented bullet under the one before it
        const bullet = line.match(/^[-*•]\s+(.*)$/);
        const numbered = line.match(/^\d+[.)]\s+(.*)$/);
        if (bullet || numbered) {
            flushPara();
            const ordered = !!numbered;
            if (list && list.ordered !== ordered && !nested) flushList();
            list ??= { ordered, items: [] };
            list.items.push({ text: (bullet ?? numbered)![1], nested });
        } else if (!line) {
            flushPara();
            flushList();
        } else {
            flushList();
            para.push(line);
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
