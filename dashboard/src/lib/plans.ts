/**
 * The plans, as the website sells them and the billing page shows them (BILLING_PLAN.md). Prices are per assistant;
 * yearly is 12 months for the price of 10. backend/subscriptions.py charges these prices (tests/test_billing.py keeps
 * the two the same).
 */
export type TierId = "starter" | "growth" | "pro";
export type Period = "monthly" | "yearly";

export type Tier = {
    id: TierId; name: string; monthly: number; summary: string; featured?: boolean;
    includes: string[]; previous?: string;
};

export const YEARLY_PAYS_FOR = 10;

export const TIERS: Tier[] = [
    {
        id: "starter", name: "Starter", monthly: 999, summary: "An assistant on your website.",
        includes: ["1 assistant", "Website chat in your brand", "2,000 AI replies a month", "Train on documents, websites and videos",
                   "Questions it couldn't answer, to teach it", "1 team seat"],
    },
    {
        id: "growth", name: "Growth", monthly: 2499, summary: "Website and WhatsApp, with your team.", featured: true,
        previous: "Starter",
        includes: ["WhatsApp on your own business number", "Live chat with notes and saved replies", "10,000 AI replies a month",
                   "Collected data and lead scores", "Email alerts and customer follow-ups", "3 team seats"],
    },
    {
        id: "pro", name: "Pro", monthly: 6999, summary: "Add phone calls and campaigns.",
        previous: "Growth",
        includes: ["Voice assistant with 300 call credits a month", "Call-backs and outbound campaigns", "25,000 AI replies a month",
                   "Webhooks, LeadSquared and Google Sheets", "Business hours and warm transfers", "5 team seats"],
    },
];

export const RANK: Record<TierId, number> = { starter: 0, growth: 1, pro: 2 };

/** What a plan costs for the period: a month, or a year at 10 months' price. */
export const priceOf = (tier: Tier, period: Period) => (period === "yearly" ? tier.monthly * YEARLY_PAYS_FOR : tier.monthly);

/** A month's share of the price (yearly: the year's price over 12 months). */
export const perMonth = (tier: Tier, period: Period) => (period === "yearly" ? Math.round((tier.monthly * YEARLY_PAYS_FOR) / 12) : tier.monthly);

export const inr = (n: number) => `₹${n.toLocaleString("en-IN")}`;
