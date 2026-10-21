import { Fragment, type ReactNode } from "react";

/**
 * An assistant's reply with the light formatting models write: paragraphs, "-" / "*" and "1." lists,
 * headings, **bold**, *italic* and links. Built as React elements (never as HTML), so a reply can't
 * inject markup; only http(s), mailto and tel links are made clickable.
 */
const INLINE = /\*\*(.+?)\*\*|__(.+?)__|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|\[([^\]]+)\]\(((?:https?:\/\/|mailto:|tel:)[^\s)]+)\)|(https?:\/\/[^\s<>()]+[^\s<>().,!?;:'"])|([\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,})/gi;
const BULLET = /^\s*[-*•]\s+/;
const NUMBER = /^\s*(\d{1,3})[.)]\s+/;
const HEADING = /^\s*#{1,6}\s+/;

function inline(text: string, linkColor: string | undefined, key: string): ReactNode[] {
    const out: ReactNode[] = [];
    let last = 0;
    let n = 0;
    const link = (href: string, label: ReactNode) => (
        <a key={`${key}-${n++}`} href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer"
           className="underline underline-offset-2 break-words" style={linkColor ? { color: linkColor } : undefined}>{label}</a>
    );
    for (const m of text.matchAll(INLINE)) {
        if (m.index > last) out.push(text.slice(last, m.index));
        const [, bold, bold2, italic, label, href, url, email] = m;
        if (bold || bold2) out.push(<strong key={`${key}-${n++}`} className="font-semibold">{inline(bold || bold2, linkColor, `${key}-b${n}`)}</strong>);
        else if (italic) out.push(<em key={`${key}-${n++}`}>{italic}</em>);
        else if (href) out.push(link(href, label));
        else if (url) out.push(link(url, url.replace(/^https?:\/\/(www\.)?/, "")));
        else if (email) out.push(link(`mailto:${email}`, email));
        last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul" | "ol"; items: string[]; start: number } | { kind: "h"; text: string };

function blocks(text: string): Block[] {
    const out: Block[] = [];
    let para: string[] = [];
    const flush = () => { if (para.length) out.push({ kind: "p", lines: para }); para = []; };
    for (const raw of text.replace(/\r/g, "").split("\n")) {
        const line = raw.trimEnd();
        const prev = out[out.length - 1];
        const bullet = BULLET.test(line) && !/^\s*\*\*/.test(line);
        const number = NUMBER.exec(line);
        if (!line.trim()) { flush(); continue; }
        if (bullet || number) {
            flush();
            const kind = bullet ? "ul" : "ol";
            const item = line.replace(bullet ? BULLET : NUMBER, "");
            if (prev && prev.kind === kind) prev.items.push(item);
            else out.push({ kind, items: [item], start: number ? Number(number[1]) : 1 });
        } else if (HEADING.test(line)) {
            flush();
            out.push({ kind: "h", text: line.replace(HEADING, "") });
        } else if (/^\s{2,}\S/.test(raw) && prev && (prev.kind === "ul" || prev.kind === "ol") && !para.length) {
            prev.items[prev.items.length - 1] += ` ${line.trim()}`; // a wrapped list item
        } else {
            para.push(line);
        }
    }
    flush();
    return out;
}

export function RichText({ text, linkColor }: { text: string; linkColor?: string }) {
    return (
        <div className="space-y-2 break-words">
            {blocks(text).map((b, i) => {
                const key = `b${i}`;
                if (b.kind === "h") return <p key={key} className="font-semibold">{inline(b.text, linkColor, key)}</p>;
                if (b.kind === "p") {
                    return (
                        <p key={key}>
                            {b.lines.map((line, j) => (
                                <Fragment key={j}>{j > 0 && <br />}{inline(line, linkColor, `${key}-${j}`)}</Fragment>
                            ))}
                        </p>
                    );
                }
                const List = b.kind;
                return (
                    <List key={key} start={b.kind === "ol" && b.start !== 1 ? b.start : undefined}
                          className={`${b.kind === "ul" ? "list-disc" : "list-decimal"} pl-5 space-y-1 marker:opacity-60`}>
                        {b.items.map((item, j) => <li key={j}>{inline(item, linkColor, `${key}-${j}`)}</li>)}
                    </List>
                );
            })}
        </div>
    );
}
