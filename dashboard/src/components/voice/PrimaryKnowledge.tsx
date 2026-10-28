"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import KnowledgePanel from "@/app/dashboard/builder/[id]/components/KnowledgePanel";
import { Button, Skeleton } from "@/components/ui";
import { apiFetch } from "@/lib/api";

type Saving = "saved" | "dirty" | "saving" | "error";

/** The assistant's knowledge, as in the assistant builder (the same panel and the same saved text): what it knows on
 * calls, in website chat and on WhatsApp. Saved automatically a second after the last change, like the builder. */
export default function PrimaryKnowledge({ botId }: { botId: string }) {
    const [loaded, setLoaded] = useState<"loading" | "ok" | "error">("loading");
    const [knowledge, setKnowledge] = useState("");
    const [provider, setProvider] = useState("google");
    const [model, setModel] = useState("auto");
    const [apiKey, setApiKey] = useState("");
    const [hasSavedKey, setHasSavedKey] = useState(false);
    const [state, setState] = useState<Saving>("saved");
    const lastSaved = useRef("");
    const savedValues = useRef({ knowledge: "", provider: "", model: "" }); // only what changed is sent

    const snapshot = useMemo(() => JSON.stringify({ knowledge, provider, model, apiKey }), [knowledge, provider, model, apiKey]);
    const latest = useRef(snapshot);
    latest.current = snapshot;

    useEffect(() => {
        let gone = false;
        (async () => {
            try {
                const res = await apiFetch(`/api/bots/${botId}/config`);
                if (!res.ok) throw new Error();
                const data = await res.json();
                if (gone) return;
                setKnowledge(data.knowledge_base || "");
                setProvider(data.ai_provider || "google");
                setModel(data.ai_model || "auto");
                setHasSavedKey(!!data.has_ai_api_key);
                savedValues.current = { knowledge: data.knowledge_base || "", provider: data.ai_provider || "google", model: data.ai_model || "auto" };
                lastSaved.current = JSON.stringify({
                    knowledge: data.knowledge_base || "", provider: data.ai_provider || "google", model: data.ai_model || "auto", apiKey: "",
                });
                setLoaded("ok");
            } catch {
                if (!gone) setLoaded("error");
            }
        })();
        return () => { gone = true; };
    }, [botId]);

    const persist = useCallback(async () => {
        if (snapshot === lastSaved.current) return;
        setState("saving");
        try {
            const body: Record<string, string> = {};
            if (knowledge !== savedValues.current.knowledge) body.knowledge_base = knowledge;
            if (provider !== savedValues.current.provider) body.ai_provider = provider;
            if (model !== savedValues.current.model) body.ai_model = model;
            if (apiKey) body.ai_api_key = apiKey;
            const res = await apiFetch(`/api/bots/${botId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
            if (!res.ok) throw new Error();
            lastSaved.current = snapshot;
            savedValues.current = { knowledge, provider, model };
            if (apiKey) setHasSavedKey(true);
            setState(latest.current === snapshot ? "saved" : "dirty"); // edited while saving: the next save follows
        } catch {
            setState("error");
        }
    }, [snapshot, botId, knowledge, provider, model, apiKey]);

    useEffect(() => {
        if (loaded !== "ok") return;
        if (snapshot === lastSaved.current) {
            setState((s) => (s === "saving" ? s : "saved"));
            return;
        }
        setState((s) => (s === "error" ? s : "dirty"));
        const t = setTimeout(persist, 1000);
        return () => clearTimeout(t);
    }, [snapshot, persist, loaded]);

    useEffect(() => {
        const onLeave = (e: BeforeUnloadEvent) => {
            if (state !== "saved") { e.preventDefault(); e.returnValue = ""; }
        };
        window.addEventListener("beforeunload", onLeave);
        return () => window.removeEventListener("beforeunload", onLeave);
    }, [state]);

    const refreshKnowledge = useCallback(async () => {
        const res = await apiFetch(`/api/bots/${botId}/config`);
        if (!res.ok) return knowledge;
        const text: string = (await res.json()).knowledge_base || "";
        setKnowledge(text);
        savedValues.current = { ...savedValues.current, knowledge: text };
        lastSaved.current = JSON.stringify({ knowledge: text, provider, model, apiKey });
        return text;
    }, [botId, knowledge, provider, model, apiKey]);

    if (loaded === "loading") return <div className="space-y-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div>;
    if (loaded === "error") return <p className="text-sm text-signal">Couldn&apos;t load this assistant&apos;s knowledge.</p>;

    return (
        <div>
            <p className="text-xs text-stone-500 mb-4 flex items-center gap-2" role="status" aria-live="polite">
                {state === "saving" ? "Saving…" : state === "dirty" ? "Unsaved changes" : state === "error" ? (
                    <>Couldn&apos;t save. <Button size="sm" variant="ghost" onClick={persist}>Try again</Button></>
                ) : "All changes saved"}
            </p>
            <KnowledgePanel botId={botId} provider={provider} setProvider={setProvider} model={model} setModel={setModel}
                            apiKey={apiKey} setApiKey={setApiKey} hasSavedKey={hasSavedKey}
                            knowledge={knowledge} setKnowledge={setKnowledge} refreshKnowledge={refreshKnowledge} saved={state === "saved"} />
        </div>
    );
}
