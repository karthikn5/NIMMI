/**
 * Read the first sheet of an Excel .xlsx file in the browser, as rows of text.
 * An .xlsx file is a zip of XML files; we unzip with the browser's DecompressionStream
 * and read the sheet, shared strings and date formats. Old .xls files aren't supported.
 */

const enc = new TextDecoder();

async function inflate(data: Uint8Array): Promise<Uint8Array> {
    const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Zip entries by name (only the ones we ask for are decompressed). */
async function unzip(buf: ArrayBuffer, wanted: (name: string) => boolean): Promise<Map<string, string>> {
    const bytes = new Uint8Array(buf);
    const view = new DataView(buf);
    let eocd = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
        if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error("This doesn't look like an Excel file. Save it as .xlsx or CSV and try again.");
    const count = view.getUint16(eocd + 10, true);
    let p = view.getUint32(eocd + 16, true);
    const out = new Map<string, string>();
    for (let n = 0; n < count; n++) {
        if (view.getUint32(p, true) !== 0x02014b50) break;
        const method = view.getUint16(p + 10, true);
        const size = view.getUint32(p + 20, true);
        const nameLen = view.getUint16(p + 28, true);
        const extraLen = view.getUint16(p + 30, true);
        const commentLen = view.getUint16(p + 32, true);
        const local = view.getUint32(p + 42, true);
        const name = enc.decode(bytes.subarray(p + 46, p + 46 + nameLen));
        p += 46 + nameLen + extraLen + commentLen;
        if (!wanted(name)) continue;
        const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
        const raw = bytes.subarray(start, start + size);
        out.set(name, enc.decode(method === 0 ? raw : await inflate(raw)));
    }
    return out;
}

const xml = (text?: string) => new DOMParser().parseFromString(text || "<x/>", "application/xml");
const byTag = (node: Document | Element, tag: string) => Array.from(node.getElementsByTagNameNS("*", tag));

function columnIndex(ref: string): number {
    let n = 0;
    for (const ch of ref.replace(/\d+$/, "")) n = n * 26 + (ch.charCodeAt(0) - 64);
    return n - 1;
}

const BUILTIN_DATES = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47]);

/** Style indexes (the `s` attribute on cells) that show a date or time. */
function dateStyles(stylesXml?: string): Set<number> {
    const doc = xml(stylesXml);
    const custom = new Map<number, string>();
    for (const f of byTag(doc, "numFmt")) custom.set(Number(f.getAttribute("numFmtId")), f.getAttribute("formatCode") || "");
    const isDate = (id: number) => {
        if (BUILTIN_DATES.has(id)) return true;
        const code = (custom.get(id) || "").replace(/"[^"]*"|\[[^\]]*\]/g, "");
        return /[dmyhs]/i.test(code) && !/^[#0.,%\s]*$/.test(code);
    };
    const xfs = byTag(doc, "cellXfs")[0];
    const set = new Set<number>();
    if (xfs) byTag(xfs, "xf").forEach((xf, i) => { if (isDate(Number(xf.getAttribute("numFmtId")))) set.add(i); });
    return set;
}

function serialToDate(serial: number): string {
    const ms = Math.round((serial - 25569) * 86400 * 1000); // Excel's 1900 date system
    const d = new Date(ms);
    const hasTime = Math.abs(serial % 1) > 1e-9;
    return d.toLocaleString("en-IN", {
        timeZone: "UTC", day: "numeric", month: "short", year: "numeric",
        ...(hasTime ? { hour: "numeric", minute: "2-digit" } : {}),
    });
}

/** Numbers as people typed them: no "9.87654321E9", no ".0". */
function numberText(v: string): string {
    const n = Number(v);
    if (!Number.isFinite(n)) return v;
    return Number.isInteger(n) ? BigInt(Math.round(n)).toString() : String(n);
}

export async function readXlsx(file: File): Promise<string[][]> {
    if (/\.xls$/i.test(file.name)) throw new Error("Old .xls files aren't supported. In Excel, use Save As → Excel Workbook (.xlsx), or CSV.");
    const files = await unzip(await file.arrayBuffer(), (n) =>
        n === "xl/workbook.xml" || n === "xl/_rels/workbook.xml.rels" || n === "xl/sharedStrings.xml" || n === "xl/styles.xml" || n.startsWith("xl/worksheets/"));

    // First sheet in the workbook's own order.
    const firstRel = byTag(xml(files.get("xl/workbook.xml")), "sheet")[0]?.getAttributeNS("http://schemas.openxmlformats.org/officeDocument/2006/relationships", "id");
    const target = byTag(xml(files.get("xl/_rels/workbook.xml.rels")), "Relationship").find((r) => r.getAttribute("Id") === firstRel)?.getAttribute("Target");
    const sheetPath = target ? (target.startsWith("/") ? target.slice(1) : `xl/${target}`) : [...files.keys()].find((n) => n.startsWith("xl/worksheets/sheet"));
    const sheet = sheetPath && files.get(sheetPath);
    if (!sheet) throw new Error("Couldn't find a sheet in this file.");

    const shared = byTag(xml(files.get("xl/sharedStrings.xml")), "si").map((si) => byTag(si, "t").map((t) => t.textContent || "").join(""));
    const dates = dateStyles(files.get("xl/styles.xml"));

    const rows: string[][] = [];
    for (const row of byTag(xml(sheet), "row")) {
        const cells: string[] = [];
        for (const c of byTag(row, "c")) {
            const type = c.getAttribute("t");
            const v = byTag(c, "v")[0]?.textContent ?? "";
            let text: string;
            if (type === "s") text = shared[Number(v)] ?? "";
            else if (type === "inlineStr") text = byTag(c, "t").map((t) => t.textContent || "").join("");
            else if (type === "b") text = v === "1" ? "TRUE" : "FALSE";
            else if (type === "str" || type === "e") text = v;
            else if (v && dates.has(Number(c.getAttribute("s")))) text = serialToDate(Number(v));
            else text = v ? numberText(v) : "";
            const at = c.getAttribute("r") ? columnIndex(c.getAttribute("r")!) : cells.length;
            while (cells.length < at) cells.push("");
            cells[at] = text.trim();
        }
        if (cells.some((x) => x)) rows.push(cells);
    }
    return rows;
}

/** Rows back to CSV text, so the list can be shown and edited before starting. */
export function toCsv(rows: string[][]): string {
    const cell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
    return rows.map((r) => r.map(cell).join(",")).join("\n");
}
