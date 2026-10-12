/** Minimal CSV: parse uploaded contact lists and export tables (quotes, commas and newlines handled). */

export function parseCsv(text: string): string[][] {
    const rows: string[][] = [];
    let row: string[] = [];
    let cell = "";
    let quoted = false;
    const src = text.replace(/^﻿/, "");
    for (let i = 0; i < src.length; i++) {
        const ch = src[i];
        if (quoted) {
            if (ch === '"' && src[i + 1] === '"') { cell += '"'; i++; }
            else if (ch === '"') quoted = false;
            else cell += ch;
        } else if (ch === '"') {
            quoted = true;
        } else if (ch === "," || ch === "\t") {
            row.push(cell); cell = "";
        } else if (ch === "\n" || ch === "\r") {
            if (ch === "\r" && src[i + 1] === "\n") i++;
            row.push(cell); cell = "";
            if (row.some((c) => c.trim())) rows.push(row);
            row = [];
        } else {
            cell += ch;
        }
    }
    row.push(cell);
    if (row.some((c) => c.trim())) rows.push(row);
    return rows.map((r) => r.map((c) => c.trim()));
}

const escapeCell = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function downloadCsv(filename: string, header: string[], rows: unknown[][]) {
    const text = [header, ...rows].map((r) => r.map(escapeCell).join(",")).join("\r\n");
    // BOM so Excel opens UTF-8 (Indian names, ₹) correctly.
    const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    a.click();
    URL.revokeObjectURL(url);
}
