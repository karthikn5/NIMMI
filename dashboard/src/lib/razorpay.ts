/** Razorpay Checkout: open the payment sheet for a server-created order or subscription, then verify on the server. */
import { apiJson } from "@/lib/api";

type Order = { order_id: string; amount: number; currency: string; key_id: string };
/** A plan that renews by itself (BILLING_PLAN.md); `card_change`: replace the card a renewing plan is charged to. */
type Recurring = { subscription_id: string; key_id: string; card_change?: boolean };
type Paid = { razorpay_payment_id: string; razorpay_signature: string; razorpay_order_id?: string; razorpay_subscription_id?: string };

declare global {
    interface Window { Razorpay?: new (options: Record<string, unknown>) => { open: () => void } }
}

let loading: Promise<void> | null = null;

function loadCheckout(): Promise<void> {
    if (typeof window !== "undefined" && window.Razorpay) return Promise.resolve();
    loading ??= new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "https://checkout.razorpay.com/v1/checkout.js";
        s.onload = () => resolve();
        s.onerror = () => { loading = null; reject(new Error("Couldn't load the payment page. Check your connection.")); };
        document.body.appendChild(s);
    });
    return loading;
}

/**
 * Opens Checkout for `checkout` and verifies the result with the backend.
 * Resolves with the server's verify response, or null if the person closed the sheet. A card change has nothing to
 * verify: Razorpay keeps the new card for the plan's next charge.
 */
export async function payAndVerify<T = { message: string }>(checkout: Order | Recurring, opts: { description: string; email?: string; name?: string }): Promise<T | null> {
    await loadCheckout();
    const what = "subscription_id" in checkout
        ? { subscription_id: checkout.subscription_id, ...(checkout.card_change ? { subscription_card_change: true } : {}) }
        : { amount: checkout.amount, currency: checkout.currency, order_id: checkout.order_id };
    const paid = await new Promise<Paid | null>((resolve) => {
        const rzp = new window.Razorpay!({
            key: checkout.key_id,
            ...what,
            name: "Nimmi AI",
            description: opts.description,
            prefill: { email: opts.email, name: opts.name },
            theme: { color: "#550a64" },
            handler: (r: Paid) => resolve(r),
            modal: { ondismiss: () => resolve(null) },
        });
        rzp.open();
    });
    if (!paid) return null;
    if ("subscription_id" in checkout && checkout.card_change) return { message: "Payment method updated. The next charge uses it." } as T;
    return apiJson<T>("/api/payments/verify", { method: "POST", json: paid });
}
