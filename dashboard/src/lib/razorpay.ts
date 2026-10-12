/** Razorpay Checkout: open the payment sheet for a server-created order, then verify on the server. */
import { apiJson } from "@/lib/api";

type Order = { order_id: string; amount: number; currency: string; key_id: string };
type Paid = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };

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
 * Opens Checkout for `order` and verifies the result with the backend.
 * Resolves with the server's verify response, or null if the person closed the sheet.
 */
export async function payAndVerify<T = { message: string }>(order: Order, opts: { description: string; email?: string; name?: string }): Promise<T | null> {
    await loadCheckout();
    const paid = await new Promise<Paid | null>((resolve) => {
        const rzp = new window.Razorpay!({
            key: order.key_id,
            amount: order.amount,
            currency: order.currency,
            order_id: order.order_id,
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
    return apiJson<T>("/api/payments/verify", { method: "POST", json: paid });
}
