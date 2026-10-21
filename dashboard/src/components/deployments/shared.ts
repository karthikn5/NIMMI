/** Shapes and helpers shared by the Deployments screens (see backend/routers/sites.py). */

export type Deploy = {
    id: string;
    status: "building" | "ready" | "failed";
    source: "upload" | "git" | "hook";
    file_count: number;
    total_bytes: number;
    commit_sha: string | null;
    commit_message: string | null;
    note: string | null;
    error: string | null;
    created_at: string | null;
    finished_at: string | null;
    live: boolean;
    preview_url: string | null;
};

export type DnsRecord = { type: "CNAME" | "TXT"; host: string; name: string; value: string };

export type Site = {
    id: string;
    name: string;
    slug: string;
    status: "active" | "blocked";
    url: string | null;
    bot_id: string | null;
    spa: "auto" | "on" | "off";
    git: { url: string; branch: string | null; folder: string | null; has_token: boolean; hook: boolean } | null;
    domain: {
        name: string; status: "pending" | "issuing" | "active" | "failed"; error: string | null; records: DnsRecord[];
        apex: string; checked_at: string | null; url: string | null;
    } | null;
    latest: Deploy | null;
    live: Deploy | null;
    created_at: string | null;
    deleted_at: string | null;
    deploys?: Deploy[];
};

export type SiteList = {
    sites: Site[];
    deleted: Site[];
    domain: string | null;
    ready: boolean;
    custom_domains: boolean;
    custom_domains_available: boolean;
    limits: { sites: number; deploy_bytes: number; deploy_files: number; file_bytes: number; paid: boolean };
};

/** Server times are UTC; some arrive without a zone. */
export const toDate = (iso: string | null) => (iso ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`) : null);

export function timeAgo(iso: string | null) {
    const d = toDate(iso);
    if (!d) return "";
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
    if (s < 7 * 86400) return `${Math.floor(s / 86400)} d ago`;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export const hostOf = (url: string | null) => (url ? url.replace(/^https?:\/\//, "") : "");

export const SOURCE_LABEL: Record<Deploy["source"], string> = { upload: "Upload", git: "Git", hook: "Git push" };

/** Mirrors backend/sites/bundle.py: never uploaded, so a dropped project folder stays small. */
const SKIP_DIRS = new Set([".git", ".github", ".gitlab", ".svn", ".hg", "node_modules", "__MACOSX", ".idea", ".vscode", ".cache", ".next", ".nuxt",
    ".vercel", ".netlify", "__pycache__", ".venv", "venv"]);
const SKIP_NAMES = new Set([".DS_Store", "Thumbs.db", "desktop.ini", ".gitignore", ".gitattributes", ".gitmodules"]);
export const skipPath = (path: string) => {
    const parts = path.split("/");
    return parts.slice(0, -1).some((p) => SKIP_DIRS.has(p)) || SKIP_NAMES.has(parts[parts.length - 1]);
};
