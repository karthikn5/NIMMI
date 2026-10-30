# Billing: plan

Written 30 Oct 2026 after the owner asked to "fix this billing module properly" and chose: the website's three plans,
real automatic renewal, and the ₹1 price fixed at once (pushed in ce5bf33).

## 1. What was wrong (read from the code and live, 30 Oct 2026)

- Billing sold "1/6/12 Month Plans" at ₹1, ₹499 and ₹999 per assistant; the website (nimmiai.in/pricing, indexed by
  Google) sells Starter ₹999, Growth ₹2,499 and Pro ₹6,999 a month per assistant, yearly at 10 months' price.
- The 1-month plan cost ₹1 on live with live Razorpay keys since 12 Oct (b31318f). Fixed to ₹999 in ce5bf33.
- The three plans unlocked the same things; their feature lists ("Lightning fast API", "Priority support") and
  struck-through prices were made up.
- "Auto-renew" was a switch that nothing read: plans just ended and the assistant went off the customer's website.
- Payment history guessed the plan from the amount.
- Locally RAZORPAY_WEBHOOK_SECRET is empty: without it the backup path (a payment whose browser closed before the
  check) is ignored. Railway's value is unknown.

## 2. Research (Oct 2026)

- Razorpay Subscriptions ([API](https://razorpay.com/docs/api/payments/subscriptions/),
  [integration](https://razorpay.com/docs/payments/subscriptions/integration-guide/),
  [webhooks](https://razorpay.com/docs/webhooks/subscriptions/)): plans (`POST /v1/plans`, not editable: a new price is a
  new plan), subscriptions (`POST /v1/subscriptions`: plan_id, total_count, start_at, addons = an upfront amount, notes).
  Without start_at the first cycle is charged at checkout; with start_at, ₹5 is taken and refunded. Checkout gets
  `subscription_id`; the handler's signature is HMAC-SHA256 of `payment_id|subscription_id` (the id we stored).
  Failed charges: pending, retried T+1..T+3, then halted (the customer changes the card to recover). Cancel with
  `cancel_at_cycle_end`; a cancelled subscription can't be restarted. Changing the plan isn't allowed for UPI or
  eMandate subscriptions. Events: authenticated, activated, charged, pending, halted, cancelled, completed, paused,
  resumed, updated. The Subscriptions feature (and Flash Checkout) must be on for the account; on the live account
  listing plans and subscriptions works (0 of each), so creation is expected to work.
- RBI e-mandate framework (April 2026): the first payment of a mandate needs an OTP; later automatic debits go through
  without one only up to ₹15,000. Growth yearly (₹24,990) and Pro yearly (₹69,990) can't renew silently.

## 3. How it works

1. **Plans** (per assistant, as the website says): Starter, Growth, Pro; monthly, or yearly at 10 months' price.
   Prices live in `subscriptions.py`; the website and billing page share `dashboard/src/lib/plans.ts` (a test keeps
   the two in step).
2. **Monthly plans renew by themselves**: a Razorpay subscription per assistant charges each month; the plan's end
   date follows each charge. A failed charge emails the owner ("update your card"); after Razorpay's retries the plan
   stops renewing and ends at its date. If the account can't create subscriptions, a monthly plan is paid once, like a
   yearly one, and the owner hears about it.
3. **Yearly plans are paid once a year** (the RBI limit above, and one rule for all yearly plans): emails 7, 3 and 1 day
   before the end, and "Renew" on the billing page extends it by a year.
4. **Changes**: an upgrade starts now, paying the difference for the rest of the current period; a downgrade, or
   monthly to yearly and back, starts when the current period ends. "Stop renewing" keeps the plan to its end date;
   "Keep renewing" undoes it before then.
5. **Earlier plans** (1/6/12 Month): everything included until they end. A plan bought for such an assistant starts
   when the earlier one ends, so no paid day is lost.
6. **What each plan includes** (the website's lists, made real; section 5 phase 2): Starter: website chat, 2,000 AI
   replies a month, 1 team seat. Growth: + WhatsApp, live chat, 10,000 replies, lead scores, email alerts and
   follow-ups, 3 seats. Pro: + 300 call credits a month, call-backs and campaigns, 25,000 replies, webhooks,
   LeadSquared and Google Sheets, business hours and warm transfers, 5 seats. Phone calls work on every plan with
   credits. Free: build and test only (as today).

## 4. Owner's part

- Razorpay Dashboard: Subscriptions on (Account & Settings, or ask Razorpay support), Flash Checkout on (Account &
  Settings > Checkout features), and a webhook to `https://api.nimmiai.in/api/payments/webhook` with payment.captured
  and the subscription.* events, its secret in Railway's `RAZORPAY_WEBHOOK_SECRET`.
- First real purchase on live after the push: buy Starter monthly for an assistant, check it shows "Renews on ...",
  then "Stop renewing" (Razorpay keeps the ₹999; refund it from the Razorpay Dashboard if it was only a test).

## 5. Phases

1. Billing core: catalog, subscriptions and yearly payments, changes, stop/keep renewing, earlier plans, webhooks,
   reminders and failed-payment emails, payment history with plan names, the new billing page.
2. What each plan includes, enforced: WhatsApp, live chat, Schedule and campaigns, integrations, seats, monthly AI
   replies, Pro's call credits; upgrade prompts where something is locked.
3. Receipts (Razorpay invoices for subscription charges), GST once the business is registered.

## 6. Status (30 Oct 2026, local, not committed)

Phase 1 built:
- Backend: `subscriptions.py` (catalog, `plans_of`, `plan_purchase`, `apply_purchase` once per payment,
  `renewal_charged`), `payments.py` (`/plans`, `/quote`, `/checkout`, `/verify` for orders and subscriptions,
  `/stop-renewal`, `/update-card`, the webhook's `subscription.*` events, `maintenance`), new columns
  `subscriptions.tier/period/rzp_status`, `transactions.plan_name`, table `billing_plans`. The assistants list and
  `plans.is_paid` count only plans that have started.
- Dashboard: `lib/plans.ts` (shared with the website's pricing table), `lib/razorpay.ts` (subscriptions, card change),
  the billing page (each assistant's plan and what follows, plans with monthly/yearly, a confirm step with the quote).
- Safety: a renewing plan at its end asks Razorpay where its subscription is (`sync_subscription`), so a customer
  charged while the webhook isn't set up keeps their assistant; any refusal to make a subscription becomes a single
  payment for the month.
- Checked: `tests/test_billing.py` (11: the purchase rules, monthly and yearly, upgrade with the old subscription
  stopped, a change from the period's end and changing it again, no subscriptions on the account, renewals and failed
  charges and a closed browser by webhook, stop and keep renewing, the browser's check and the webhook at once,
  reminders, the website's prices, a renewal the webhook never reported); 394 backend tests pass. Browser: `billing_ui.mjs` 21 of 21 (every state, the
  buttons per assistant, the upgrade's ₹3,000 for 20 days, a plan after an earlier one, stop renewing, cancel a
  change, phone width).
- Not checked: a real Razorpay subscription (live keys only; test-mode keys would allow it without money).

Phase 2 (what each plan includes, enforced) is next.
