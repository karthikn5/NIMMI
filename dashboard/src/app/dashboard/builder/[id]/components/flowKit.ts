/** Flow helpers for the builder: block names, problems to fix before going live, and starter templates. */
import type { Edge, Node } from "reactflow";

export const BLOCK_NAMES: Record<string, string> = {
    start: "Start", message: "Message", textInput: "Text question", emailInput: "Email question", numberInput: "Number question",
    phoneInput: "Phone question", datePicker: "Date question", multipleChoice: "Choices", image: "Image", video: "Video",
    fileUpload: "File upload", rating: "Rating", condition: "Condition", handover: "Hand to a person", delay: "Wait",
    variable: "Set value", end: "End", aiPrompt: "AI step", httpRequest: "HTTP request", webhook: "Webhook", slack: "Slack",
    googleSheets: "Google Sheets",
};

export type Issue = { nodeId: string; text: string };

const blank = (v: unknown) => !String(v ?? "").trim();
export const choicesOf = (n: Node) => ((n.data?.options as string[]) || []).map((o) => String(o).trim()).filter(Boolean);

/** Things that would stop the flow or confuse visitors, in canvas order. */
export function checkFlow(nodes: Node[], edges: Edge[]): Issue[] {
    const issues: Issue[] = [];
    const ids = new Set(nodes.map((n) => n.id));
    const live = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    const out = (id: string) => live.filter((e) => e.source === id);
    const name = (n: Node) => BLOCK_NAMES[n.type || ""] || "Block";

    const start = nodes.find((n) => n.type === "start");
    if (start && nodes.length > 1 && !out(start.id).length) {
        issues.push({ nodeId: start.id, text: "Start isn't connected, so the flow won't run. Drag from Start to your first block." });
    }
    // Everything should be reachable from Start.
    const reached = new Set<string>();
    const queue = start ? [start.id] : [];
    while (queue.length) {
        const id = queue.shift()!;
        if (reached.has(id)) continue;
        reached.add(id);
        out(id).forEach((e) => queue.push(e.target));
    }

    const sorted = [...nodes].sort((a, b) => a.position.y - b.position.y || a.position.x - b.position.x);
    for (const n of sorted) {
        const d = n.data || {};
        if (n.type !== "start" && start && out(start.id).length && !reached.has(n.id)) {
            issues.push({ nodeId: n.id, text: `${name(n)} isn't connected to the flow, so visitors never reach it.` });
        }
        switch (n.type) {
            case "message":
                if (blank(d.message)) issues.push({ nodeId: n.id, text: "A message block is empty." });
                break;
            case "multipleChoice": {
                const options = choicesOf(n);
                if (options.length < 2) issues.push({ nodeId: n.id, text: "Choices need at least two options." });
                if (out(n.id).some((e) => e.sourceHandle && !options.includes(e.sourceHandle))) {
                    issues.push({ nodeId: n.id, text: "A branch is linked to a choice that no longer exists. Reconnect it." });
                }
                break;
            }
            case "condition":
                if (blank(d.variable)) issues.push({ nodeId: n.id, text: "A condition doesn't say which answer to check." });
                if (!out(n.id).some((e) => e.sourceHandle === "true") || !out(n.id).some((e) => e.sourceHandle === "false")) {
                    issues.push({ nodeId: n.id, text: "Connect both the Yes and No sides of the condition." });
                }
                break;
            case "image":
                if (blank(d.imageUrl)) issues.push({ nodeId: n.id, text: "An image block has no image link." });
                break;
            case "video":
                if (blank(d.videoUrl)) issues.push({ nodeId: n.id, text: "A video block has no video link." });
                break;
            case "httpRequest":
            case "webhook":
            case "slack":
                if (blank(d.url)) issues.push({ nodeId: n.id, text: `${name(n)} needs a URL.` });
                break;
            case "googleSheets":
                if (blank(d.spreadsheetId)) issues.push({ nodeId: n.id, text: "Google Sheets needs the spreadsheet ID." });
                break;
            case "aiPrompt":
                if (blank(d.prompt)) issues.push({ nodeId: n.id, text: "Say what the AI step should do." });
                break;
            case "variable":
                if (blank(d.variableName)) issues.push({ nodeId: n.id, text: "A Set value block has no name for the value." });
                break;
        }
    }
    return issues;
}

/* ---------- Starter templates (same data the widget's flow runner reads) ---------- */

const node = (id: string, type: string, x: number, y: number, data: Record<string, unknown>): Node => ({ id, type, position: { x, y }, data });
const link = (source: string, target: string, sourceHandle?: string): Edge => ({
    id: `e-${source}-${target}${sourceHandle ? `-${sourceHandle}` : ""}`, source, target, sourceHandle: sourceHandle ?? null,
    type: "animated", markerEnd: { type: "arrowclosed" as never, color: "#550a64" },
});

export const TEMPLATES: { id: string; name: string; description: string; build: () => { nodes: Node[]; edges: Edge[] } }[] = [
    {
        id: "lead", name: "Capture a lead", description: "Greets, asks for a name and phone number, then lets the AI answer.",
        build: () => ({
            nodes: [
                node("start-1", "start", 250, 0, { label: "Start" }),
                node("t-hi", "message", 170, 90, { label: "Message", message: "Hi! I can help with prices, availability and bookings." }),
                node("t-name", "textInput", 170, 230, { label: "Text question", message: "May I have your name?", variableName: "name", required: true }),
                node("t-phone", "phoneInput", 170, 380, { label: "Phone question", message: "Thanks! What's the best number to reach you on?", variableName: "phone", required: true }),
                node("t-end", "end", 170, 530, { label: "End", message: "Thank you. Our team will contact you soon. Ask me anything in the meantime." }),
            ],
            edges: [link("start-1", "t-hi"), link("t-hi", "t-name"), link("t-name", "t-phone"), link("t-phone", "t-end")],
        }),
    },
    {
        id: "booking", name: "Book an appointment", description: "Asks what they need, a date, their name and number.",
        build: () => ({
            nodes: [
                node("start-1", "start", 250, 0, { label: "Start" }),
                node("t-hi", "message", 170, 90, { label: "Message", message: "Hi! I can book an appointment for you." }),
                node("t-what", "multipleChoice", 170, 230, { label: "Choices", message: "What would you like to book?", options: ["Consultation", "Visit", "Call back"], variableName: "service" }),
                node("t-date", "datePicker", 170, 470, { label: "Date question", message: "Which date suits you?", variableName: "date" }),
                node("t-name", "textInput", 170, 610, { label: "Text question", message: "May I have your name?", variableName: "name", required: true }),
                node("t-phone", "phoneInput", 170, 760, { label: "Phone question", message: "And the best number to reach you on?", variableName: "phone", required: true }),
                node("t-end", "end", 170, 910, { label: "End", message: "Thank you! Our team will call you to confirm the time." }),
            ],
            edges: [link("start-1", "t-hi"), link("t-hi", "t-what"), link("t-what", "t-date"), link("t-date", "t-name"), link("t-name", "t-phone"), link("t-phone", "t-end")],
        }),
    },
    {
        id: "route", name: "Route to the right team", description: "Asks what they need and branches: sales, support or free chat.",
        build: () => ({
            nodes: [
                node("start-1", "start", 330, 0, { label: "Start" }),
                node("t-hi", "message", 250, 90, { label: "Message", message: "Hi! Let me get you to the right place." }),
                node("t-what", "multipleChoice", 250, 230, { label: "Choices", message: "What are you looking for?", options: ["Buying", "Help with an order", "Just looking"], variableName: "interest" }),
                node("t-phone", "phoneInput", 0, 520, { label: "Phone question", message: "Great! What's the best number for our sales team to call?", variableName: "phone", required: true }),
                node("t-sales", "handover", 0, 680, { label: "Hand to a person", message: "Connecting you to our sales team now." }),
                node("t-support", "handover", 320, 520, { label: "Hand to a person", message: "Connecting you to our support team now." }),
                node("t-browse", "end", 620, 520, { label: "End", message: "No problem. Ask me anything you'd like to know." }),
            ],
            edges: [link("start-1", "t-hi"), link("t-hi", "t-what"), link("t-what", "t-phone", "Buying"), link("t-phone", "t-sales"),
                    link("t-what", "t-support", "Help with an order"), link("t-what", "t-browse", "Just looking")],
        }),
    },
];
