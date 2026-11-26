# Payments & subscriptions: setup and go-live checklist

**Status: built and tested against a fake gateway and mock HTTP only. Midtrans/Xendit have never been called for real.** The adapters
follow those providers' documented shapes as understood when written; verify each against the current official docs and run the
provider's SANDBOX end to end before any live transaction.

## How it works (the guarantees)
- The client only says *what* to buy. The price is always read from the database.
- A purchase only takes effect from a **webhook that passes signature verification**, and even then we **re-fetch the transaction from the
  gateway's API** and compare order id and amount before granting anything. The webhook body is only a hint about which order to check.
- Fulfilment is exactly-once (`fulfilled_at` claimed atomically; credit allocations are unique per source). Duplicates, replays and
  concurrent deliveries do nothing extra. Every webhook, valid or not, is stored (`/admin/webhooks`); headers are not stored.
- Returning from the gateway's page grants nothing; the status page only reports what our server knows.
- If the gateway API cannot be reached, the webhook gets 503 (fail closed) so the gateway retries.
- Admin can reconcile any order (`POST /admin/orders/{order_no}/reconcile`) to recover a lost webhook.

## 1. Accounts and keys you must obtain
Midtrans (merchant + Snap) and/or Xendit (invoices) accounts, approved for production by the provider. Never commit keys.

| Variable | Used by |
|---|---|
| `PAYMENT_GATEWAY` | `midtrans` or `xendit` (`fake` works only when `APP_ENV=development`) |
| `MIDTRANS_SERVER_KEY`, `MIDTRANS_PRODUCTION` | Midtrans (`true` only for live keys) |
| `XENDIT_SECRET_KEY`, `XENDIT_CALLBACK_TOKEN` | Xendit |
| `APP_BASE_URL` | links in emails/redirects |
| `SMTP_*`, `MAIL_FROM` | receipts and renewal reminders |

## 2. Register the webhook URL in the provider dashboard
`https://<your-api-host>/api/v1/webhooks/midtrans` or `.../xendit` (HTTPS only). The Xendit callback token you set in their dashboard must
equal `XENDIT_CALLBACK_TOKEN`.

## 3. Catalogue
`python ../scripts/seed_commerce.py` (from `backend/`) creates EXAMPLE plans and packages. **Their prices are placeholders**; review them in the
database/admin API (`/admin/plans`, `/admin/credit-packages`) before launch. Changing a price creates a new price row; existing orders keep theirs.

## 4. Scheduled work
The Celery `beat` service must run: `subscriptions.tick` (every 15 min) allocates monthly credit slices (annual plans drip monthly),
sends renewal links 3 days before the period ends, moves lapsed subscriptions to `past_due` then `expired` after `GRACE_DAYS`, and expires stale orders.

## Product decisions encoded (confirm them)
- Renewal is **invoice-based**: the user pays a link we email; there is no automatic card debit.
- Subscription credits expire at the end of each month-slice; **no rollover**. Purchased credits expire per package (default seed: 365 days). Bonus has its own expiry.
- **Changing plans switches immediately with no proration and no refund** of the old plan's remaining time.
- Cancelling stops renewal; access continues to period end. **Refunds are not implemented** (no refund API calls, no credit clawback).
- Tax/PPN and invoice format are not handled (invoices here are simple records, not tax invoices).
- Plan tiers do not yet restrict which AI tools a user can use; credits are the only gate.

## Go-live checklist
1. Sandbox: pay, fail, expire, and replay a webhook; confirm each outcome in `/admin/orders` and `/admin/webhooks`.
2. Pay a real small amount with live keys; reconcile it against the provider's dashboard.
3. Confirm a tampered webhook is rejected (401) in your deployed environment.
4. Have an accountant/lawyer review pricing display, tax, refund and credit-expiry wording.
