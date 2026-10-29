/**
 * The dashboard's screens by route, with the ids the agent's notes use (backend/agent/screens.py; a backend test
 * checks the two lists match). Pages can add more about themselves with useAgentScreen.
 */
export type Entity = { kind: string; id: string; name?: string };
export type Screen = {
    path: string;
    id: string;
    title: string;
    tab?: string;
    entity?: Entity;
    details?: Record<string, unknown>;
    errors?: string[];
};

// [route, screen id, title, what the route's id is]
const ROUTES: [RegExp, string, string, string?][] = [
    [/^\/dashboard\/?$/, "assistants", "Assistants"],
    [/^\/dashboard\/builder\/([^/]+)/, "builder", "Assistant builder", "assistant"],
    [/^\/dashboard\/deployments\/([^/]+)/, "deployment", "A deployed website", "website"],
    [/^\/dashboard\/deployments\/?$/, "deployments", "Deployments"],
    [/^\/dashboard\/live-chat/, "live_chat", "Live chat"],
    [/^\/dashboard\/questions/, "questions", "Questions"],
    [/^\/dashboard\/voice\/agents\/([^/]+)/, "voice_agent", "Voice agent settings", "assistant"],
    [/^\/dashboard\/voice\/agents\/?$/, "voice_agents", "Voice: Agents"],
    [/^\/dashboard\/voice\/knowledge\/([^/]+)/, "voice_script", "Voice script", "assistant"],
    [/^\/dashboard\/voice\/knowledge\/?$/, "voice_knowledge", "Voice: Knowledge"],
    [/^\/dashboard\/voice\/contacts/, "voice_contacts", "Voice: Contacts"],
    [/^\/dashboard\/voice\/calls/, "voice_calls", "Voice: Calls"],
    [/^\/dashboard\/voice\/schedule/, "voice_schedule", "Voice: Schedule"],
    [/^\/dashboard\/voice\/campaigns\/([^/]+)/, "voice_campaign", "A campaign", "campaign"],
    [/^\/dashboard\/voice\/campaigns\/?$/, "voice_campaigns", "Voice: Campaigns"],
    [/^\/dashboard\/voice\/data/, "voice_data", "Voice: Collected data"],
    [/^\/dashboard\/voice\/numbers/, "voice_numbers", "Voice: Numbers"],
    [/^\/dashboard\/voice\/compliance/, "voice_compliance", "Voice: Compliance"],
    [/^\/dashboard\/voice\/?$/, "voice_overview", "Voice: Overview"],
    [/^\/dashboard\/whatsapp\/inbox/, "whatsapp_inbox", "WhatsApp: Inbox"],
    [/^\/dashboard\/whatsapp\/assistant/, "whatsapp_assistant", "WhatsApp: Assistant"],
    [/^\/dashboard\/whatsapp\/files/, "whatsapp_files", "WhatsApp: Files"],
    [/^\/dashboard\/whatsapp\/settings/, "whatsapp_settings", "WhatsApp: Settings"],
    [/^\/dashboard\/whatsapp\/?$/, "whatsapp_overview", "WhatsApp: Overview"],
    [/^\/dashboard\/integrations/, "integrations", "Integrations"],
    [/^\/dashboard\/analytics/, "analytics", "Analytics"],
    [/^\/dashboard\/billing/, "billing", "Billing"],
    [/^\/dashboard\/profile/, "profile", "Profile"],
    [/^\/dashboard\/team/, "team", "Team"],
];

/** The screen at a route; unknown routes still say where they are. */
export function screenFor(pathname: string, search = ""): Screen {
    const params = new URLSearchParams(search);
    for (const [pattern, id, title, kind] of ROUTES) {
        const m = pathname.match(pattern);
        if (!m) continue;
        const screen: Screen = { path: pathname, id, title };
        if (kind && m[1]) screen.entity = { kind, id: decodeURIComponent(m[1]) };
        const direction = params.get("direction");
        if (direction === "inbound" || direction === "outbound") screen.details = { direction };
        return screen;
    }
    return { path: pathname, id: "other", title: "Dashboard" };
}

/** A few questions that fit the screen, for an empty chat. */
export function suggestionsFor(id: string): string[] {
    const page = "What can I do on this page?";
    const by: Record<string, string[]> = {
        assistants: [page, "Which of my assistants have a paid plan?", "How do I add an assistant to my website?"],
        builder: [page, "What does this assistant know?", "How do I change its colours?"],
        live_chat: [page, "How many people are waiting?"],
        questions: [page, "Which questions come up most?"],
        voice_overview: [page, "How many voice credits do I have left?", "How did my recent calls go?"],
        voice_agent: [page, "Which AI model is this agent using, and what does a minute cost?"],
        voice_schedule: [page, "Is anything waiting for me in Schedule?"],
        voice_numbers: [page, "How do I get an Indian phone number?"],
        whatsapp_overview: [page, "Is my WhatsApp number working?"],
        analytics: [page, "How did this month compare with the last?"],
        billing: [page, "What does my plan include?"],
    };
    return by[id] ?? [page, "Which of my assistants have a paid plan?"];
}
