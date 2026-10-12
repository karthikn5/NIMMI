/**
 * Runs a builder flow (nodes + edges saved by the Flow tab) inside the chat widget.
 * Pure helpers only; the widget page owns the UI and the side effects.
 */

export type FlowNode = { id: string; type: string; data: Record<string, any> };
export type FlowEdge = { id?: string; source: string; target: string; sourceHandle?: string | null };

export const INPUT_TYPES = ["textInput", "emailInput", "numberInput", "phoneInput", "datePicker"] as const;
export type InputType = (typeof INPUT_TYPES)[number];

/** Builder default labels: shown on the canvas, but not something to ask a visitor. */
const DEFAULT_LABELS = new Set([
    "Text Input", "Email Input", "Phone Input", "Number Input", "Date Picker", "Multiple Choice",
    "Star Rating", "File Upload", "Bot Message", "Human Handover", "End",
]);

const DEFAULT_QUESTIONS: Record<string, string> = {
    textInput: "Could you tell me a little more?",
    emailInput: "What's your email address?",
    phoneInput: "What's the best phone number to reach you on?",
    numberInput: "Please enter a number.",
    datePicker: "Which date suits you?",
    multipleChoice: "Please choose an option.",
    rating: "How would you rate your experience?",
    fileUpload: "Please upload your file.",
};

/** What the widget says for a node: its message, a custom label, or a sensible default. */
export function questionFor(node: FlowNode): string {
    const { message, label } = node.data || {};
    if (message && String(message).trim()) return String(message);
    if (label && !DEFAULT_LABELS.has(String(label))) return String(label);
    return DEFAULT_QUESTIONS[node.type] ?? "";
}

/** Name the answer is saved under. Phone and email get plain names so lead alerts pick them up. */
export function variableName(node: FlowNode): string {
    const { variableName: named, label } = node.data || {};
    if (named) return String(named);
    if (node.type === "phoneInput") return "phone";
    if (node.type === "emailInput") return "email";
    return label && !DEFAULT_LABELS.has(String(label)) ? String(label) : node.id;
}

/** Returns an error message, or null if the answer is acceptable. */
export function validate(type: InputType, value: string): string | null {
    const v = value.trim();
    if (type === "emailInput" && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)) return "That email doesn't look right. Please check it and try again.";
    if (type === "phoneInput") {
        const digits = v.replace(/\D/g, "");
        if (!/^\+?[\d\s\-()]+$/.test(v) || digits.length < 10 || digits.length > 15) return "Please enter a valid phone number, with the country code if you're outside India.";
    }
    if (type === "numberInput" && Number.isNaN(Number(v))) return "Please enter a number.";
    return null;
}

export class Flow {
    private byId = new Map<string, FlowNode>();
    private edges: FlowEdge[];

    constructor(nodes: FlowNode[] = [], edges: FlowEdge[] = []) {
        nodes.forEach((n) => this.byId.set(n.id, n));
        // Ignore links left behind by deleted blocks.
        this.edges = edges.filter((e) => this.byId.has(e.source) && this.byId.has(e.target));
    }

    start(): FlowNode | null {
        const start = [...this.byId.values()].find((n) => n.type === "start");
        return start ? this.next(start.id) : null;
    }

    /** True when the flow has at least one block after Start. */
    get hasSteps() {
        return this.start() !== null;
    }

    /** Follows the link from `id`; `handle` picks a branch (condition true/false) when there is one. */
    next(id: string, handle?: string): FlowNode | null {
        const out = this.edges.filter((e) => e.source === id);
        const edge = (handle && out.find((e) => e.sourceHandle === handle)) || out.find((e) => !e.sourceHandle) || (handle ? null : out[0]);
        return edge ? this.byId.get(edge.target) ?? null : null;
    }
}

export function evaluate(node: FlowNode, vars: Record<string, string>): boolean {
    const { variable, operator, value } = node.data || {};
    const actual = String(vars[variable] ?? "");
    const expected = String(value ?? "");
    switch (operator) {
        case "equals": return actual.toLowerCase() === expected.toLowerCase();
        case "contains": return actual.toLowerCase().includes(expected.toLowerCase());
        case "greater_than": return Number(actual) > Number(expected);
        case "less_than": return Number(actual) < Number(expected);
        default: return false;
    }
}
