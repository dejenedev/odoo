# Budget Segment Project - Knowledge Repository

## Project Overview
Odoo 19 custom addon (`custom_addons/general_ledger`) for multi-segment budget code combinations integrated with the Chart of Accounts. Author: dejenedev. Version: 19.0.1.2.0. Depends on: `account`.

**Purpose:** Define configurable budget segments (Organization, Geographic, Program, Project, Fund Source, Economic, Counterparty) with hierarchical values, and create code combinations for budget tracking on journal entries and invoices. Includes organization management with payment consolidation.

---

## Module Architecture

### Models

| Model | File | Purpose |
|-------|------|---------|
| `budget.organization` | `models/budget_organization.py` | Organization entity linked 1:1 to `res.company`. Holds segment assignments, paying org flag, bank accounts, payment journal, clearing account/journal for inter-company payments. |
| `budget.segment.type` | `models/budget_segment_type.py` | Segment categories. Has `is_economic`, `is_organization`, `level_ids`, `value_ids`. |
| `budget.segment.level` | `models/budget_segment_type.py` | Hierarchical levels within a segment type (level_number, digit_count, is_leaf). |
| `budget.segment.value` | `models/budget_segment_value.py` | Hierarchical values within a segment. Self-referencing parent/child. Auto-syncs with `account.account` for economic segments. |
| `budget.code.combination` | `models/budget_code_combination.py` | Unique combination of segment values. Has `line_ids`, `date_from`, `date_to`. |
| `budget.code.combination.line` | `models/budget_code_combination.py` | One segment value per segment type within a combination. |
| `account.move.line` (inherited) | `models/account_move_line.py` | Adds `budget_combination_id` and wizard button to journal items. |
| `res.config.settings` (inherited) | `models/res_config_settings.py` | `budget_auto_create_combination` setting (block/auto). |

### Wizards
| Model | File | Purpose |
|-------|------|---------|
| `budget.combination.wizard` | `wizard/budget_combination_wizard.py` | Modal for selecting segment values and finding/creating combinations. Supports partial search with org filtering. |
| `budget.combination.wizard.line` | `wizard/budget_combination_wizard.py` | One line per segment type. Has `allowed_value_ids` computed field for org filtering. |
| `budget.payment.consolidation` | `wizard/budget_payment_consolidation.py` | Payment consolidation wizard for paying organization. |

### Views — Segment Values (TWO SEPARATE FORMS)
| View ID | Type | Purpose |
|---------|------|---------|
| `view_budget_segment_value_form` | Form | Non-economic segment values (no accounting fields) |
| `view_budget_segment_value_list` | List | Non-economic segment values list |
| `view_budget_segment_value_economic_form` | Form | Economic segment values (with Accounting tab, Linked Account) |
| `view_budget_segment_value_economic_list` | List | Economic segment values list |
| `view_budget_segment_value_search` | Search | Shared search view for both |

### Menus (Accounting > Configuration > Budget Segments)
1. Organizations (seq 5)
2. Segment Types (seq 10)
3. Segment Values (seq 20) — non-economic
4. Economic Segment Values (seq 25)
5. Code Combinations (seq 30)
6. Payment Consolidation (seq 40)

### Security
- `account_account_manager`: Full CRUD on all models.
- `account_account_invoice`: Read-only on config models; full CRUD on wizard models.

---

## Key Relationships
```
budget.organization
  ├── company_id → res.company (1:1, unique)
  ├── segment_value_ids → budget.segment.value (allowed org codes)
  ├── bank_account_ids → res.partner.bank
  ├── payment_journal_id → account.journal
  ├── clearing_account_id → account.account (inter-company clearing)
  └── clearing_journal_id → account.journal (for clearing entries)

budget.segment.type
  ├── is_economic (Boolean) — links to Chart of Accounts
  ├── is_organization (Boolean) — used for org filtering
  ├── level_ids → budget.segment.level
  └── value_ids → budget.segment.value

budget.segment.value (hierarchical, self-referencing)
  └── account_id → account.account (auto-synced for economic segments)

budget.code.combination
  └── line_ids → budget.code.combination.line
                    ├── segment_type_id → budget.segment.type
                    └── segment_value_id → budget.segment.value (must be is_last_level=True)

account.move.line
  └── budget_combination_id → budget.code.combination
```

---

## Organization System

### Architecture
- **Multi-company**: Each organization = separate `res.company`
- **`budget.organization`**: Separate model linked 1:1 to `res.company`
- Segment type has `is_organization=True` flag to identify org segments
- Organizations are assigned specific segment values — only those are accessible in the budget wizard

### Paying Organization
- One org flagged `is_paying_org=True` (constraint: only one globally)
- Has `bank_account_ids` and `payment_journal_id` for consolidated payments
- Payment Consolidation wizard: loads unpaid bills across all companies, uses inter-company clearing to pay and reconcile

### Inter-Company Clearing
- Each organization has `clearing_account_id` and `clearing_journal_id`
- Avoids cross-company journal conflicts by creating separate entries per company
- **Bill's company side** (e.g. MoE): Clearing entry DR Accounts Payable, CR Clearing Account → auto-reconciles with bill (bill shows Paid)
- **Paying company side** (e.g. MoF): Payment entry DR Clearing Account, CR Bank → records actual disbursement
- Both orgs must have clearing account + journal configured before consolidation

### Budget Wizard Filtering
- `allowed_value_ids` computed on wizard lines
- For org segments: restricted to values in current company's `budget.organization.segment_value_ids`
- For other segments: all last-level values
- Supports partial search: fill only economic segment → shows matching combinations filtered by org

---

## Data Flows

### Budget-Tracked Transaction
1. User creates Journal Entry/Invoice with line items
2. Clicks budget wizard button (fa-search) on a line
3. Wizard loads all segment types, pre-selects economic segment by matching account
4. Organization segment filtered to current company's allowed values
5. Partial search: shows matching combinations; or full search with auto-create
6. "Confirm & Assign" writes combination to the move line

### Payment Consolidation (Inter-Company Clearing)
1. Ministry of Education creates vendor bill and posts it
2. Ministry of Finance (paying org) opens Payment Consolidation wizard
3. Sets date range, clicks "Load Bills" — shows all unpaid bills across companies
4. Selects bills, clicks "Create Payments"
5. **Per bill's company**: clearing entry (DR Payable, CR Clearing) auto-reconciles → bill shows Paid
6. **Paying company**: payment entry (DR Clearing, CR Bank) records disbursement
7. All created entries shown in done state for review

### Economic Segment Value → Account Sync
1. Create/edit a `budget.segment.value` where `is_economic=True` and `is_last_level=True`
2. Set `account_type` and other account fields
3. On save, `_sync_account()` creates/updates linked `account.account` with `code=full_code`

---

## Development Notes
- Odoo version: **19.0** (branch: `19.0`)
- Database: `odoo19` (PostgreSQL, user: odoo, localhost:5432)
- Remote: `origin` → `https://github.com/dejenedev/odoo.git`
- Custom addons path: `custom_addons/`
- Upgrade command: `python odoo-bin -c odoo.conf -d odoo19 -u budget_segment`
- `--dev=reload` only reloads Python, NOT XML. Always use `-u` after XML changes.
- Hard refresh (Ctrl+Shift+R) needed after menu/view changes — browser caches menus.
- `column_invisible="not parent.field"` does NOT work reliably in self-referencing one2many lists. Use separate form views instead.
- Context keys prefixed with `default_` are auto-processed by Odoo to set fields. Use non-default prefixes for custom context keys.
- When two form views exist for the same model, use `ir.actions.act_window.view` records to explicitly bind each action to its views.
- `force_save="1"` on readonly fields in transient models may not persist values. Prefer making fields editable with pre-filled defaults.
- `account.payment` in Odoo 19 uses `memo` field, NOT `ref`. The `ref` field does not exist on this model.
- Cross-company payments: `account.payment` and `account.payment.register` enforce company consistency. Use inter-company clearing journal entries (`account.move`) instead of direct cross-company payments.
