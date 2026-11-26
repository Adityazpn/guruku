# API reference (generated)

Base path `/api/v1`. Bearer access token (15 min) unless noted; refresh token is an HttpOnly cookie. Errors: `{"detail": "<code>"}`.

Money/credit/AI-generation endpoints require an `Idempotency-Key` header (8–100 chars). Interactive docs at `/docs` when running.


## admin

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/admin/ai/usage` | Usage | bearer |
| GET | `/api/v1/admin/audit-logs` | Audit Logs | bearer |
| POST | `/api/v1/admin/fx-rates` | Add Fx | bearer |
| PATCH | `/api/v1/admin/models/{mid}` | Patch Model | bearer |
| POST | `/api/v1/admin/models/{mid}/pricing` | Add Pricing | bearer |
| POST | `/api/v1/admin/prompts/{vid}/publish` | Publish Prompt | bearer |
| GET | `/api/v1/admin/providers` | List Providers | bearer |
| POST | `/api/v1/admin/providers` | Create Provider | bearer |
| PATCH | `/api/v1/admin/providers/{pid}` | Patch Provider | bearer |
| PUT | `/api/v1/admin/providers/{pid}/credential` | Set Credential | bearer |
| POST | `/api/v1/admin/providers/{pid}/models` | Add Model | bearer |
| POST | `/api/v1/admin/providers/{pid}/test` | Test Provider | bearer |
| GET | `/api/v1/admin/system` | System Health | bearer |
| GET | `/api/v1/admin/tools` | Admin Tools | bearer |
| PATCH | `/api/v1/admin/tools/{tid}` | Patch Tool | bearer |
| PUT | `/api/v1/admin/tools/{tid}/assignments` | Set Assignments | bearer |
| PUT | `/api/v1/admin/tools/{tid}/pricing-rule` | Set Pricing Rule | bearer |
| GET | `/api/v1/admin/tools/{tid}/prompts` | List Prompts | bearer |
| POST | `/api/v1/admin/tools/{tid}/prompts` | Create Prompt | bearer |
| POST | `/api/v1/admin/tools/{tid}/prompts/rollback` | Rollback Prompt | bearer |
| GET | `/api/v1/admin/users` | Search Users | bearer |
| POST | `/api/v1/admin/users/{uid}/credits/grant` | Grant Credits | bearer |

## admin-commerce

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/admin/credit-packages` | List Packages | bearer |
| POST | `/api/v1/admin/credit-packages` | Create Package | bearer |
| PATCH | `/api/v1/admin/credit-packages/{kid}` | Patch Package | bearer |
| GET | `/api/v1/admin/orders` | Admin Orders | bearer |
| POST | `/api/v1/admin/orders/{order_no}/reconcile` | Reconcile | bearer |
| GET | `/api/v1/admin/plans` | List Plans | bearer |
| POST | `/api/v1/admin/plans` | Create Plan | bearer |
| PATCH | `/api/v1/admin/plans/{pid}` | Patch Plan | bearer |
| GET | `/api/v1/admin/webhooks` | Admin Webhooks | bearer |

## admin-library

| method | path | summary | auth |
|---|---|---|---|
| POST | `/api/v1/admin/library/categories` | Create Category | bearer |
| GET | `/api/v1/admin/library/downloads` | Admin Downloads | bearer |
| GET | `/api/v1/admin/library/items` | Admin Items | bearer |
| POST | `/api/v1/admin/library/items` | Create Item | bearer |
| PATCH | `/api/v1/admin/library/items/{item_id}` | Patch Item | bearer |
| POST | `/api/v1/admin/library/items/{item_id}/files` | Upload | bearer |

## assistant

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/assistant/conversations` | List Conversations | bearer |
| POST | `/api/v1/assistant/conversations` | New Conversation | bearer |
| GET | `/api/v1/assistant/conversations/{cid}` | Get Conversation | bearer |
| PATCH | `/api/v1/assistant/conversations/{cid}` | Rename | bearer |
| DELETE | `/api/v1/assistant/conversations/{cid}` | Delete Conversation | bearer |
| POST | `/api/v1/assistant/conversations/{cid}/messages` | Send Message | bearer |

## auth

| method | path | summary | auth |
|---|---|---|---|
| POST | `/api/v1/auth/forgot-password` | Forgot Password | — |
| POST | `/api/v1/auth/login` | Login | — |
| POST | `/api/v1/auth/logout` | Logout | — |
| POST | `/api/v1/auth/mfa/confirm` | Mfa Confirm | bearer |
| POST | `/api/v1/auth/mfa/setup` | Mfa Setup | bearer |
| POST | `/api/v1/auth/refresh` | Refresh | — |
| POST | `/api/v1/auth/register` | Register | — |
| POST | `/api/v1/auth/resend-verification` | Resend Verification | bearer |
| POST | `/api/v1/auth/reset-password` | Reset Password | — |
| POST | `/api/v1/auth/verify-email` | Verify Email | — |

## billing

| method | path | summary | auth |
|---|---|---|---|
| POST | `/api/v1/checkout/credits` | Checkout Credits | bearer |
| POST | `/api/v1/checkout/subscription` | Checkout Subscription | bearer |
| GET | `/api/v1/credit-packages` | Packages | — |
| POST | `/api/v1/dev/fake-pay/{order_no}` | Dev Fake Pay | bearer |
| GET | `/api/v1/invoices` | Invoices | bearer |
| GET | `/api/v1/orders` | Orders | bearer |
| GET | `/api/v1/orders/{order_no}` | Order | bearer |
| GET | `/api/v1/plans` | Plans | — |
| GET | `/api/v1/subscription` | My Subscription | bearer |
| POST | `/api/v1/subscription/cancel` | Cancel | bearer |
| POST | `/api/v1/subscription/resume` | Resume | bearer |
| POST | `/api/v1/webhooks/{gateway}` | Webhook | — |

## credits

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/credits/ledger` | Get Ledger | bearer |
| GET | `/api/v1/credits/summary` | Get Summary | bearer |

## documents

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/documents` | List Documents | bearer |
| GET | `/api/v1/documents/{doc_id}` | Get Document | bearer |
| PATCH | `/api/v1/documents/{doc_id}` | Save Document | bearer |
| DELETE | `/api/v1/documents/{doc_id}` | Delete Document | bearer |
| POST | `/api/v1/documents/{doc_id}/duplicate` | Duplicate Document | bearer |
| GET | `/api/v1/documents/{doc_id}/export` | Export | bearer |
| POST | `/api/v1/documents/{doc_id}/regenerate` | Regenerate | bearer |
| POST | `/api/v1/documents/{doc_id}/restore` | Restore | bearer |
| GET | `/api/v1/documents/{doc_id}/versions` | Versions | bearer |

## library

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/library/categories` | Categories | — |
| GET | `/api/v1/library/downloads` | History | bearer |
| GET | `/api/v1/library/files/{token}` | Local File | — |
| GET | `/api/v1/library/items` | Items | bearer |
| GET | `/api/v1/library/items/{item_id}` | Item | bearer |
| POST | `/api/v1/library/items/{item_id}/download` | Download | bearer |

## other

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/health` | Health | — |
| GET | `/api/v1/ready` | Ready | — |

## privacy

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/me/consents` | My Consents | bearer |
| POST | `/api/v1/me/consents` | Give | bearer |
| DELETE | `/api/v1/me/consents/{type_}` | Withdraw | bearer |
| POST | `/api/v1/me/student-data/delete` | Erase | bearer |

## tools

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/ai/requests/{request_id}` | Get Request | bearer |
| GET | `/api/v1/ai/requests/{request_id}/export` | Export Request | bearer |
| GET | `/api/v1/tools` | List Tools | bearer |
| GET | `/api/v1/tools/{slug}` | Get Tool | bearer |
| POST | `/api/v1/tools/{slug}/estimate` | Estimate | bearer |
| POST | `/api/v1/tools/{slug}/generate` | Generate | bearer |

## users

| method | path | summary | auth |
|---|---|---|---|
| GET | `/api/v1/me` | Me | bearer |
| GET | `/api/v1/me/profile` | Get Profile | bearer |
| PUT | `/api/v1/me/profile` | Put Profile | bearer |
