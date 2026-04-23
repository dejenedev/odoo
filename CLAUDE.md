# General Ledger Project - Knowledge Repository

## Project Overview
Three Odoo 19 custom addons at `custom_addons/`:
- **`general_ledger`** (v19.0.2.0.0) — GL, budget segments, payment consolidation, Metabase BI
- **`ame_engine`** (v19.0.1.0.0) — Approval Management Engine (Oracle AME inspired)
- **`pki_signature`** (v19.0.1.0.0) — PKI digital signatures with certificate management

Author: dejenedev. Branch: `19.0`. Database: `odoo19`.

---

## Module: general_ledger

### Models

| Model | File | Purpose |
|-------|------|---------|
| `budget.organization` | `models/budget_organization.py` | Organization entity linked 1:1 to `res.company`. Paying org flag, bank accounts, clearing account/journal. |
| `budget.segment.type` | `models/budget_segment_type.py` | Segment categories. `is_economic`, `is_organization`, `level_ids`, `value_ids`. |
| `budget.segment.level` | `models/budget_segment_type.py` | Hierarchical levels within a segment type. |
| `budget.segment.value` | `models/budget_segment_value.py` | Hierarchical values. Auto-syncs with `account.account` for economic segments. |
| `budget.code.combination` | `models/budget_code_combination.py` | Unique combination of segment values. |
| `budget.consolidated.payment` | `models/budget_consolidated_payment.py` | Persistent payment history records with AME mixin. |
| `account.move` (inherited) | `models/account_move_line.py` | AME mixin, budget payment state, approval workflow, payment submission. |
| `account.move.line` (inherited) | `models/account_move_line.py` | `budget_combination_id`, allowed combinations filtering. |
| `account.tax` (inherited) | `models/account_tax.py` | `override_account_from_bill` flag for tax account override. |
| `res.config.settings` (inherited) | `models/res_config_settings.py` | Metabase URL/UUID settings. |

### Key Features

#### Budget Code Combination Filtering
- **Organization filter**: Always applied — only combinations matching company's org segment
- **Economic filter**: Only combinations matching the line's account (via economic segment value)
- **Intersection**: Both filters AND-ed — must match both org AND account
- **No match**: If account has no economic segment → no combinations shown
- Budget code **mandatory** for expense (`expense`), revenue (`income`), and direct cost (`expense_direct_cost`) account types

#### Tax Line Budget Code Propagation
- When a budget code is set on an invoice line, related tax lines automatically get updated
- **`override_account_from_bill`** flag on `account.tax`:
  - **Enabled**: Tax line account replaced with invoice line's account + same budget code
  - **Disabled**: Tax line keeps its own account but inherits the invoice line's budget code
- Propagation happens at: save, "Request Approval", and posting

#### Payment Submission Workflow
- States: Draft → Pending Approval → Approved → Submitted → Paid
- Ribbons: PENDING APPROVAL (blue), APPROVED (blue), REJECTED (red), SUBMITTED (yellow), PAID (green)
- "Confirm" button hidden for vendor bills — must go through AME approval
- Post/Cancel buttons blocked during pending approval
- Auto-post on AME approval via `_on_ame_approved()` callback
- "Submit for Payment" only available after AME approval

#### Payment Consolidation
- Source bank account validation required
- Paying organization restriction (non-paying orgs get error)
- Persistent `budget.consolidated.payment` records (Payment History menu)
- Payment entries created in draft — auto-posted after AME approval
- "Invoice Paid" tracking suppressed via `tracking_disable` context

### Menus (Invoicing > Configuration > GL Settings)
1. Organizations (seq 5)
2. Segment Types (seq 10)
3. Segment Values (seq 20)
4. Economic Segment Values (seq 25)
5. Code Combinations (seq 30)
6. Trial Balance by Segment (seq 35)
7. Trial Balance by Code Combination (seq 36)
8. BI Dashboard — Metabase (seq 38)
9. Payment Consolidation (seq 40)
10. Payment History (seq 42)

---

## Module: ame_engine

### 5 Core Building Blocks
1. **Transaction Type** (`ame.transaction.type`) — Registers which Odoo model uses AME
2. **Attribute** (`ame.attribute`) — Extracts runtime values: static, relational, computed (safe_eval), line-item aggregate
3. **Condition** (`ame.condition`) — Boolean expressions: =, !=, >, <, >=, <=, in, not_in, between, contains
4. **Rule** (`ame.rule`) — Combines conditions (AND) + assigns approver action. Validates mutually exclusive conditions.
5. **Approver Action** (`ame.approver.action`) — Resolves WHO: specific user, approval group, supervisory hierarchy, job level, dynamic Python

### Runtime Models
- `ame.approval.instance` — State machine: draft → in_progress → approved/rejected/cancelled
- `ame.approval.line` — Per-approver tracking with SLA, PKI signing fields
- `ame.approval.log` — Immutable audit trail (no write/unlink)
- `ame.delegation` — User-initiated delegation (permanent, date range, per transaction)
- `ame.substitution` — Admin-configured auto-substitution on absence

### Auto-Integration
- `_register_hook()` reads Transaction Types, dynamically injects mixin fields onto configured models
- `ame.view.injector` creates inherited form views with approval buttons (skips if already defined)
- No code changes needed per model — just create Transaction Type + Rules

### PKI Integration
- Approve wizard checks `pki.signing.config` for the document model
- If configured: requires password + visual signature for digital signing
- If not configured: approval proceeds without PKI (comment only)

### Flow Patterns
- Serial, Parallel, Serial-Parallel Hybrid, First Responder

### Escalation
- Hourly cron checks SLA deadlines
- Actions: remind, escalate to manager, auto-approve, notify admin

---

## Module: pki_signature

### Models
- `pki.certificate.authority` — System-wide CA (RSA-2048, self-signed X.509, 10yr)
- `pki.user.certificate` — Per-user certificates (encrypted with Odoo password, 1yr validity)
- `pki.signing.config` — Configure which models need digital signing + which fields to hash
- `pki.approval.rule` — Legacy approval rules (being superseded by AME)
- `pki.signature.line` — Per-document signature records

### Key Notes
- Binary fields use `attachment=False` (stored in DB, not filestore)
- `certificate_text` stored at generation time, not computed on read
- Password validation uses `_crypt_context().verify_and_update()`
- PDF signing hook: `ir.actions.report._render_qweb_pdf` override using CA certificate

---

## Development Notes
- Odoo version: **19.0** (Community — app is "Invoicing" not "Accounting")
- Database: `odoo19` (PostgreSQL, user: odoo, localhost:5432)
- Remote: `origin` → `https://github.com/dejenedev/odoo.git`
- Custom addons path: `custom_addons/`
- Upgrade command: `python odoo-bin -c odoo.conf -d odoo19 -u general_ledger`
- Metabase BI at localhost:3000 (login: dejenegn@gmail.com)
- `--dev=reload` only reloads Python, NOT XML. Always use `-u` after XML changes.
- Hard refresh (Ctrl+Shift+R) needed after menu/view changes.
- `account_accountant` module not available (Enterprise only) — menus under "Invoicing"
- `xpath` cannot use `@string` as selector in Odoo 19 view inheritance
- Odoo 19 uses `res.groups.privilege` pattern (not `category_id`) for Access Rights tab
- `tracking_disable=True` context suppresses all mail tracking (stronger than `mail_notrack`)
- `mail_notify_author=True` context forces notifying the message author (for self-notification testing)
- Cross-company payments: Use inter-company clearing journal entries, not `account.payment`
