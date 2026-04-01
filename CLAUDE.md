# Budget Segment Project - Knowledge Repository

## Project Overview
Odoo 19 custom addon (`custom_addons/budget_segment`) for multi-segment budget code combinations integrated with the Chart of Accounts. Author: dejenedev. Version: 19.0.1.2.0. Depends on: `account`.

**Purpose:** Define configurable budget segments (Organization, Geographic, Program, Project, Fund Source, Economic, Counterparty) with hierarchical values, and create code combinations for budget tracking on journal entries and invoices.

---

## Module Architecture

### Models

| Model | File | Purpose |
|-------|------|---------|
| `budget.segment.type` | `models/budget_segment_type.py` | Segment categories (e.g., Economic, Geographic). Has `level_ids`, `value_ids`. |
| `budget.segment.level` | `models/budget_segment_type.py` | Hierarchical levels within a segment type (level_number, digit_count, is_leaf). |
| `budget.segment.value` | `models/budget_segment_value.py` | Hierarchical values within a segment. Self-referencing parent/child. Auto-syncs with `account.account` for economic segments. |
| `budget.code.combination` | `models/budget_code_combination.py` | Unique combination of segment values across all segment types. Has `line_ids`. |
| `budget.code.combination.line` | `models/budget_code_combination.py` | One segment value per segment type within a combination. |
| `account.move.line` (inherited) | `models/account_move_line.py` | Adds `budget_combination_id` and wizard button to journal items. |
| `res.config.settings` (inherited) | `models/res_config_settings.py` | `budget_auto_create_combination` setting (block/auto). |

### Wizard
| Model | File | Purpose |
|-------|------|---------|
| `budget.combination.wizard` | `wizard/budget_combination_wizard.py` | Modal for selecting segment values and finding/creating combinations. |
| `budget.combination.wizard.line` | `wizard/budget_combination_wizard.py` | One line per segment type in the wizard. |

### Views — Segment Values (TWO SEPARATE FORMS)
| View ID | Type | Purpose |
|---------|------|---------|
| `view_budget_segment_value_form` | Form | Non-economic segment values (no accounting fields) |
| `view_budget_segment_value_list` | List | Non-economic segment values list |
| `view_budget_segment_value_economic_form` | Form | Economic segment values (with Accounting tab, Linked Account) |
| `view_budget_segment_value_economic_list` | List | Economic segment values list (with Type, Linked Account columns) |
| `view_budget_segment_value_search` | Search | Shared search view for both |

### Actions & Menus
| Action | Menu | Domain | Bound Views |
|--------|------|--------|-------------|
| `action_budget_segment_value` | "Segment Values" | `is_economic = False` | `view_budget_segment_value_form` + `_list` via `ir.actions.act_window.view` |
| `action_budget_segment_value_economic` | "Economic Segment Values" | `is_economic = True` | `view_budget_segment_value_economic_form` + `_list` via `ir.actions.act_window.view` |

### Other Views
| File | What it does |
|------|-------------|
| `views/budget_segment_type_views.xml` | Form/list for segment types with inline level editing (includes `is_leaf` on levels). |
| `views/budget_code_combination_views.xml` | Form/list/search for code combinations with segment summary HTML. |
| `views/account_account_views.xml` | Makes Chart of Accounts read-only (managed via segment values). |
| `views/account_move_views.xml` | Adds budget code column + wizard button to journal entries and invoices. |
| `views/res_config_settings_views.xml` | Settings for auto-create combination mode. |
| `views/menu.xml` | Menu under Accounting > Configuration > Budget Segments. |
| `wizard/budget_combination_wizard_views.xml` | Wizard form with select/found/not_found states. |

### Security
- `account_account_manager`: Full CRUD on all models.
- `account_account_invoice`: Read-only on config models; full CRUD on wizard models.

---

## Key Relationships
```
budget.segment.type
  ├── level_ids → budget.segment.level (level_number, digit_count, is_leaf computed)
  └── value_ids → budget.segment.value (hierarchical, self-referencing parent_id/child_ids)
                    └── account_id → account.account (auto-synced for economic segments)

budget.code.combination
  └── line_ids → budget.code.combination.line
                    ├── segment_type_id → budget.segment.type
                    └── segment_value_id → budget.segment.value (must be is_last_level=True)

account.move.line
  └── budget_combination_id → budget.code.combination
```

---

## Known Issues & Status

### Level auto-default in Child Values (NEEDS TESTING)
- Context key renamed from `default_parent_level_id` to `budget_parent_level_id` to avoid Odoo intercepting it as a field default.
- `level_id` is `readonly="1" force_save="1"` in child list, auto-set via `default_get`.
- **Status:** Fix applied, needs testing after upgrade.

### View binding for non-economic form (NEEDS TESTING)
- Added explicit `ir.actions.act_window.view` records to bind both the non-economic and economic actions to their specific form/list views.
- Without this, Odoo was picking the wrong form (economic form for non-economic records).
- **Status:** Fix applied, needs testing after upgrade with `-d odoo19 -u budget_segment` + hard refresh.

---

## Data Flow: Budget-Tracked Transaction
1. User creates Journal Entry/Invoice with line items
2. Clicks budget wizard button (fa-search) on a line
3. Wizard loads all segment types, pre-selects economic segment by matching account
4. User selects remaining segment values
5. "Search" finds or auto-creates a combination
6. "Confirm & Assign" writes combination to the move line

## Data Flow: Economic Segment Value → Account Sync
1. Create/edit a `budget.segment.value` where `is_economic=True` and `is_last_level=True`
2. Set `account_type` and other account fields
3. On save, `_sync_account()` creates/updates linked `account.account` with `code=full_code`

---

## Development Notes
- Odoo version: **19.0** (branch: `19.0`)
- Database: `odoo19` (PostgreSQL, user: odoo, localhost:5432)
- Custom addons path: `custom_addons/`
- Upgrade command: `python odoo-bin -c odoo.conf -d odoo19 -u budget_segment`
- `--dev=reload` only reloads Python, NOT XML. Always use `-u` after XML changes.
- Hard refresh (Ctrl+Shift+R) needed after menu/view changes — browser caches menus.
- String domains in Odoo 19 are **client-side only** — the ORM returns `Domain.TRUE` for them server-side.
- `column_invisible="not parent.field"` does NOT work reliably in self-referencing one2many lists. Use separate form views instead.
- Context keys prefixed with `default_` are auto-processed by Odoo to set fields. Use non-default prefixes (e.g. `budget_parent_level_id`) for custom context keys read by `default_get`.
- When two form views exist for the same model, use `ir.actions.act_window.view` records to explicitly bind each action to its specific views.
