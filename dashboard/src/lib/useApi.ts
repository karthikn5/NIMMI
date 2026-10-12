"use client";

import { useCallback, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

/** Load a dashboard resource. `path` null skips loading (e.g. until a dialog opens). */
export function useApi<T>(path: string | null) {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(path !== null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!path) return;
        setLoading(true);
        setError(null);
        try {
            setData(await apiJson<T>(path));
        } catch (e) {
            setError((e as Error).message || "Couldn't reach the server");
        } finally {
            setLoading(false);
        }
    }, [path]);

    useEffect(() => { load(); }, [load]);

    return { data, setData, loading, error, reload: load };
}

export type SaveResult = { ok: true; data?: unknown } | { ok: false; message: string };

export async function apiSave(path: string, method: "PUT" | "PATCH" | "POST" | "DELETE", body?: unknown): Promise<SaveResult> {
    try {
        const data = await apiJson(path, { method, json: body });
        return { ok: true, data };
    } catch (e) {
        return { ok: false, message: (e as Error).message || "Couldn't save. Check your connection." };
    }
}

/** Local edit buffer over a loaded resource; `save` resolves to a toast message. */
export function useDraft<T>(source: { data: T | null; setData: (d: T) => void }, path: string, method: "PUT" | "PATCH" = "PUT") {
    const [draft, setDraft] = useState<T | null>(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => { if (source.data) setDraft(source.data); }, [source.data]);

    const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(source.data);

    const save = async () => {
        if (!draft) return "";
        setSaving(true);
        const res = await apiSave(path, method, draft);
        setSaving(false);
        if (!res.ok) return res.message;
        source.setData((res.data as T) ?? draft);
        return "Saved";
    };

    return { draft, setDraft, dirty, saving, save, discard: () => setDraft(source.data) };
}
