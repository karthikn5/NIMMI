/**
 * API access for the dashboard. Every request carries the signed-in user's
 * token and, when switched, the workspace they are acting in.
 */

const TOKEN_KEY = "nimmi_token";
const WORKSPACE_KEY = "nimmi_workspace";

export function apiBase() {
    if (typeof window !== "undefined" &&
        (window.location.hostname.includes("nimmiai.in") || window.location.hostname.includes("railway.app"))) {
        return "https://api.nimmiai.in";
    }
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/** Absolute URL for an API path; full URLs pass through unchanged. */
export function apiUrl(path: string) {
    return /^https?:\/\//.test(path) ? path : `${apiBase()}${path}`;
}

export function wsUrl(path: string) {
    return apiUrl(path).replace(/^http/, "ws");
}

function read(key: string) {
    try {
        return typeof window === "undefined" ? null : localStorage.getItem(key);
    } catch {
        return null;
    }
}

export function getToken() {
    return read(TOKEN_KEY);
}

/** The signed-in user's id, or null if they need to sign in (no id or no token yet). */
export function currentUserId() {
    const id = read("nimmi_user_id")?.trim();
    return id && getToken() ? id : null;
}

export type Session = { user_id: string; token: string; name?: string; email?: string };

export function saveSession(s: Session) {
    try {
        localStorage.setItem("nimmi_user_id", s.user_id);
        localStorage.setItem(TOKEN_KEY, s.token);
        localStorage.setItem("nimmi_user_name", s.name || "");
        if (s.email) localStorage.setItem("nimmi_user_email", s.email);
        localStorage.removeItem(WORKSPACE_KEY);
    } catch { /* storage blocked */ }
}

export function clearSession() {
    try {
        for (const key of ["nimmi_user_id", TOKEN_KEY, "nimmi_user_name", "nimmi_user_email", "nimmi_user_first_name", WORKSPACE_KEY]) {
            localStorage.removeItem(key);
        }
    } catch { /* storage blocked */ }
}

/** Workspace being acted in: the user's own (null) or one they were invited to. */
export function getWorkspace() {
    return read(WORKSPACE_KEY);
}

export function setWorkspace(ownerId: string | null) {
    try {
        if (ownerId && ownerId !== currentUserId()) localStorage.setItem(WORKSPACE_KEY, ownerId);
        else localStorage.removeItem(WORKSPACE_KEY);
    } catch { /* storage blocked */ }
}

/** The workspace owner id that requests act on. */
export function activeOwnerId() {
    return getWorkspace() || currentUserId();
}

export function authHeaders(extra?: HeadersInit): Record<string, string> {
    const headers: Record<string, string> = { ...(extra as Record<string, string>) };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const workspace = getWorkspace();
    if (workspace) headers["X-Workspace"] = workspace;
    return headers;
}

function redirectToLogin() {
    if (typeof window === "undefined") return;
    clearSession();
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/auth/login?next=${next}`;
}

/**
 * fetch() for dashboard endpoints. Adds auth, sends JSON bodies, and sends
 * people to sign in again when their session has ended.
 */
export async function apiFetch(path: string, init: RequestInit & { json?: unknown } = {}) {
    const { json, headers, ...rest } = init;
    const res = await fetch(apiUrl(path), {
        ...rest,
        headers: authHeaders({ ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...(headers as Record<string, string>) }),
        body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
    if (res.status === 401) redirectToLogin();
    return res;
}

/** apiFetch + JSON parsing; throws an Error with the server's message on failure. */
export async function apiJson<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
    const res = await apiFetch(path, init);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
    return body as T;
}
