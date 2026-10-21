/** The chat widget's look (stored as the bot's visual_config) and reply behaviour, with defaults and theme presets. */

export const API_URL = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
    ? "https://api.nimmiai.in"
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

export type Visual = {
    color: string;
    text_color: string;
    logo_url: string;
    position: "left" | "right";
    font_family: string;
    subtitle: string;
    show_human_toggle: boolean;
    header_height: number;
    welcome_message: string;
    starters: string[];
    input_placeholder: string;
    user_bubble_bg: string;
    user_bubble_text: string;
    assistant_bubble_bg: string;
    assistant_bubble_text: string;
    chat_bg_color: string;
    border_radius: number;
    background_image: string;
    background_opacity: number;
    input_bg_color: string;
    input_text_color: string;
    footer_bg_color: string; // "" keeps the default dark footer
    launcher_shape: "circle" | "rounded" | "square" | "oval";
    show_launcher_bg: boolean;
    show_tail: boolean;
    logo_size: number;
    right_padding: number;
    bottom_padding: number;
    launcher_greeting: string;
    greeting_delay: number;
    auto_open_delay: number; // 0 = off
    window_width: number;
    window_height: number;
    launcher_label: string; // "" = icon only; otherwise a pill such as "Chat with us"
    page_rule: "all" | "only" | "except";
    page_paths: string[]; // e.g. "/pricing", "/blog/*"
    hide_on_mobile: boolean;
    answer_feedback: boolean; // thumbs up/down under AI answers
};

export const VISUAL_DEFAULTS: Visual = {
    color: "#3b82f6",
    text_color: "#ffffff",
    logo_url: "",
    position: "right",
    font_family: "sans-serif",
    subtitle: "",
    show_human_toggle: true,
    header_height: 80,
    welcome_message: "",
    starters: [],
    input_placeholder: "",
    user_bubble_bg: "#3b82f6",
    user_bubble_text: "#ffffff",
    assistant_bubble_bg: "#e5e7eb",
    assistant_bubble_text: "#000000",
    chat_bg_color: "#f9fafb",
    border_radius: 24,
    background_image: "",
    background_opacity: 1,
    input_bg_color: "#ffffff",
    input_text_color: "#000000",
    footer_bg_color: "",
    launcher_shape: "circle",
    show_launcher_bg: true,
    show_tail: true,
    logo_size: 32,
    right_padding: 20,
    bottom_padding: 20,
    launcher_greeting: "",
    greeting_delay: 3,
    auto_open_delay: 0,
    window_width: 400,
    window_height: 600,
    launcher_label: "",
    page_rule: "all",
    page_paths: [],
    hide_on_mobile: false,
    answer_feedback: false,
};

const num = (v: unknown, d: number) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const str = (v: unknown, d: string) => (typeof v === "string" ? v : d);
const bool = (v: unknown, d: boolean) => (typeof v === "boolean" ? v : d);

/** Saved config (including older camelCase keys) to a complete Visual. */
export function normalizeVisual(raw: Record<string, unknown> | null | undefined): Visual {
    const r = raw || {};
    const pick = (snake: string, camel?: string) => (r[snake] !== undefined ? r[snake] : camel ? r[camel] : undefined);
    const d = VISUAL_DEFAULTS;
    const color = str(pick("color"), d.color) || d.color;
    const textColor = str(pick("text_color", "textColor"), d.text_color) || d.text_color;
    let logo = str(pick("logo_url", "botLogo"), "");
    if (logo.includes("/static/uploads/")) logo = `${API_URL}/static/uploads/${logo.split("/").pop()}`;
    const shape = str(pick("launcher_shape", "launcherShape"), d.launcher_shape);
    return {
        color,
        text_color: textColor,
        logo_url: logo,
        position: pick("position") === "left" ? "left" : "right",
        font_family: str(pick("font_family", "fontFamily"), d.font_family) || d.font_family,
        subtitle: str(pick("subtitle"), ""),
        show_human_toggle: bool(pick("show_human_toggle"), true),
        header_height: num(pick("header_height", "headerHeight"), d.header_height) || d.header_height,
        welcome_message: str(pick("welcome_message"), ""),
        starters: Array.isArray(r.starters) ? (r.starters as unknown[]).map(String).filter(Boolean).slice(0, 4) : [],
        input_placeholder: str(pick("input_placeholder"), ""),
        user_bubble_bg: str(pick("user_bubble_bg", "userBubbleBg"), "") || color,
        user_bubble_text: str(pick("user_bubble_text", "userBubbleText"), "") || textColor,
        assistant_bubble_bg: str(pick("assistant_bubble_bg", "assistantBubbleBg"), "") || d.assistant_bubble_bg,
        assistant_bubble_text: str(pick("assistant_bubble_text", "assistantBubbleText"), "") || d.assistant_bubble_text,
        chat_bg_color: str(pick("chat_bg_color", "chatBgColor"), "") || d.chat_bg_color,
        border_radius: num(pick("border_radius", "borderRadius"), d.border_radius),
        background_image: str(pick("background_image", "backgroundImage"), ""),
        background_opacity: num(pick("background_opacity", "backgroundOpacity"), 1),
        input_bg_color: str(pick("input_bg_color", "inputBgColor"), "") || d.input_bg_color,
        input_text_color: str(pick("input_text_color", "inputTextColor"), "") || d.input_text_color,
        footer_bg_color: str(pick("footer_bg_color"), ""),
        launcher_shape: (["circle", "rounded", "square", "oval"].includes(shape) ? shape : "circle") as Visual["launcher_shape"],
        show_launcher_bg: bool(pick("show_launcher_bg", "showLauncherBg"), true),
        show_tail: bool(pick("show_tail", "showTail"), true),
        logo_size: num(pick("logo_size", "logoSize"), d.logo_size) || d.logo_size,
        right_padding: num(pick("right_padding", "rightPadding"), d.right_padding),
        bottom_padding: num(pick("bottom_padding", "bottomPadding"), d.bottom_padding),
        launcher_greeting: str(pick("launcher_greeting"), ""),
        greeting_delay: num(pick("greeting_delay"), d.greeting_delay),
        auto_open_delay: num(pick("auto_open_delay"), 0),
        window_width: num(pick("window_width"), d.window_width),
        window_height: num(pick("window_height"), d.window_height),
        launcher_label: str(pick("launcher_label"), ""),
        page_rule: (["only", "except"].includes(String(r.page_rule)) ? r.page_rule : "all") as Visual["page_rule"],
        page_paths: Array.isArray(r.page_paths) ? (r.page_paths as unknown[]).map(String).filter(Boolean).slice(0, 30) : [],
        hide_on_mobile: bool(pick("hide_on_mobile"), false),
        answer_feedback: bool(pick("answer_feedback"), false),
    };
}

/** One-click palettes. Each sets every colour so the result is always consistent and readable. */
type Palette = Pick<Visual, "color" | "text_color" | "user_bubble_bg" | "user_bubble_text" | "assistant_bubble_bg"
    | "assistant_bubble_text" | "chat_bg_color" | "input_bg_color" | "input_text_color" | "footer_bg_color">;

export const THEMES: { id: string; name: string; palette: Palette }[] = [
    { id: "plum", name: "Plum", palette: {
        color: "#550a64", text_color: "#ffffff", user_bubble_bg: "#550a64", user_bubble_text: "#ffffff",
        assistant_bubble_bg: "#f3eef5", assistant_bubble_text: "#1c1719", chat_bg_color: "#ffffff",
        input_bg_color: "#ffffff", input_text_color: "#1c1719", footer_bg_color: "#ffffff" } },
    { id: "ocean", name: "Ocean", palette: {
        color: "#1d4ed8", text_color: "#ffffff", user_bubble_bg: "#1d4ed8", user_bubble_text: "#ffffff",
        assistant_bubble_bg: "#eef2ff", assistant_bubble_text: "#111827", chat_bg_color: "#f8fafc",
        input_bg_color: "#ffffff", input_text_color: "#111827", footer_bg_color: "#ffffff" } },
    { id: "forest", name: "Forest", palette: {
        color: "#166534", text_color: "#ffffff", user_bubble_bg: "#166534", user_bubble_text: "#ffffff",
        assistant_bubble_bg: "#ecf5ee", assistant_bubble_text: "#14251b", chat_bg_color: "#fbfdfb",
        input_bg_color: "#ffffff", input_text_color: "#14251b", footer_bg_color: "#ffffff" } },
    { id: "saffron", name: "Saffron", palette: {
        color: "#c2410c", text_color: "#ffffff", user_bubble_bg: "#c2410c", user_bubble_text: "#ffffff",
        assistant_bubble_bg: "#fdf1e8", assistant_bubble_text: "#2b1a10", chat_bg_color: "#fffdfb",
        input_bg_color: "#ffffff", input_text_color: "#2b1a10", footer_bg_color: "#ffffff" } },
    { id: "graphite", name: "Graphite", palette: {
        color: "#1c1917", text_color: "#ffffff", user_bubble_bg: "#1c1917", user_bubble_text: "#ffffff",
        assistant_bubble_bg: "#f2f1ef", assistant_bubble_text: "#1c1917", chat_bg_color: "#ffffff",
        input_bg_color: "#ffffff", input_text_color: "#1c1917", footer_bg_color: "#ffffff" } },
    { id: "midnight", name: "Midnight", palette: {
        color: "#16161c", text_color: "#ffffff", user_bubble_bg: "#7c5cff", user_bubble_text: "#ffffff",
        assistant_bubble_bg: "#24242c", assistant_bubble_text: "#ecebf2", chat_bg_color: "#0f0f14",
        input_bg_color: "#1d1d24", input_text_color: "#f4f4f6", footer_bg_color: "#15151b" } },
];

export const themeMatches = (v: Visual, p: Palette) =>
    (Object.keys(p) as (keyof Palette)[]).every((k) => String(v[k]).toLowerCase() === String(p[k]).toLowerCase());

/** Readable, widely used fonts. Mukta, Hind and Noto Sans also cover Hindi and other Indian scripts. */
export const FONTS: { label: string; value: string }[] = [
    { label: "System default", value: "sans-serif" },
    { label: "Inter", value: "'Inter', sans-serif" },
    { label: "Roboto", value: "'Roboto', sans-serif" },
    { label: "Open Sans", value: "'Open Sans', sans-serif" },
    { label: "Lato", value: "'Lato', sans-serif" },
    { label: "Poppins", value: "'Poppins', sans-serif" },
    { label: "Montserrat", value: "'Montserrat', sans-serif" },
    { label: "Nunito", value: "'Nunito', sans-serif" },
    { label: "DM Sans", value: "'DM Sans', sans-serif" },
    { label: "Manrope", value: "'Manrope', sans-serif" },
    { label: "Work Sans", value: "'Work Sans', sans-serif" },
    { label: "Figtree", value: "'Figtree', sans-serif" },
    { label: "Outfit", value: "'Outfit', sans-serif" },
    { label: "Mukta (Indian scripts)", value: "'Mukta', sans-serif" },
    { label: "Hind (Indian scripts)", value: "'Hind', sans-serif" },
    { label: "Noto Sans (Indian scripts)", value: "'Noto Sans', sans-serif" },
    { label: "Lora (serif)", value: "'Lora', serif" },
    { label: "Merriweather (serif)", value: "'Merriweather', serif" },
    { label: "Playfair Display (serif)", value: "'Playfair Display', serif" },
    { label: "Serif", value: "serif" },
    { label: "Monospace", value: "monospace" },
];

/** A Google Fonts stylesheet for a font value, or null for the generic families. */
export function fontStylesheet(font: string): string | null {
    if (["sans-serif", "serif", "monospace"].includes(font)) return null;
    const family = font.replace(/'/g, "").split(",")[0].trim().replace(/ /g, "+");
    return family ? `https://fonts.googleapis.com/css2?family=${family}:wght@400;500;700&display=swap` : null;
}

export const assetUrl = (url: string) =>
    url && url.includes("/static/uploads/") ? `${API_URL}/static/uploads/${url.split("/").pop()}` : url;

/* ---------- Behaviour (stored as the bot's behaviour; see backend/behaviour.py) ---------- */

export type StandardField = "name" | "phone" | "email";
export type Collect = {
    enabled: boolean;
    fields: StandardField[];
    /** The business's own details, such as Budget or City (up to 6). */
    custom: string[];
    timing: "early" | "after_answer" | "interest";
};

export type Behaviour = {
    reply_length: "short" | "balanced" | "detailed";
    language: string;
    ask_for_contact: boolean;
    offer_human: boolean;
    fallback_followup: string;
    collect: Collect;
};

export const STANDARD_FIELDS: { value: StandardField; label: string }[] = [
    { value: "name", label: "Name" }, { value: "phone", label: "Phone number" }, { value: "email", label: "Email" },
];
export const MAX_CUSTOM_FIELDS = 6;
export const COLLECT_DEFAULTS: Collect = { enabled: true, fields: ["name", "phone", "email"], custom: [], timing: "after_answer" };

export const BEHAVIOUR_DEFAULTS: Behaviour = {
    reply_length: "balanced", language: "match", ask_for_contact: false, offer_human: true, fallback_followup: "",
    collect: COLLECT_DEFAULTS,
};

export const LANGUAGES = [
    { value: "match", label: "Same as the visitor" }, { value: "en", label: "English" }, { value: "hi", label: "Hindi" },
    { value: "ta", label: "Tamil" }, { value: "te", label: "Telugu" }, { value: "kn", label: "Kannada" },
    { value: "ml", label: "Malayalam" }, { value: "mr", label: "Marathi" }, { value: "bn", label: "Bengali" },
    { value: "gu", label: "Gujarati" },
];

export const normalizeBehaviour = (raw: Partial<Behaviour> | null | undefined): Behaviour => ({
    ...BEHAVIOUR_DEFAULTS, ...(raw || {}), collect: { ...COLLECT_DEFAULTS, ...(raw?.collect || {}) },
});
