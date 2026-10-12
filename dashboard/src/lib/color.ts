/** Small colour helpers for the chat widget and its builder: contrast checks and readable text colours. */

function rgb(hex: string): [number, number, number] | null {
    const h = (hex || "").trim().replace(/^#/, "");
    const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    if (!/^[0-9a-f]{6}$/i.test(full)) return null;
    return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) as [number, number, number];
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function luminance(hex: string): number {
    const c = rgb(hex);
    if (!c) return 0;
    const [r, g, b] = c.map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two colours, 1 to 21. */
export function contrast(a: string, b: string): number {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}

export const isLight = (hex: string) => luminance(hex) > 0.4;

/** Black or white, whichever reads better on this background. */
export const readableOn = (hex: string) => (contrast(hex, "#ffffff") >= contrast(hex, "#1c1917") ? "#ffffff" : "#1c1917");

export const isHex = (v: string) => rgb(v) !== null;
