# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetSegmentValue(models.Model):
    _name = 'budget.segment.value'
    _description = 'Budget Segment Value'
    _order = 'segment_type_id, full_code'

    segment_type_id = fields.Many2one('budget.segment.type', string="Segment Type",
                                      required=True, ondelete='cascade', index=True)
    is_economic = fields.Boolean(related='segment_type_id.is_economic', store=True)
    level_id = fields.Many2one('budget.segment.level', string="Level",
                               required=True, ondelete='restrict')
    level_number = fields.Integer(related='level_id.level_number', store=True, string="Level No.")
    parent_id = fields.Many2one('budget.segment.value', string="Parent",
                                ondelete='cascade', index=True,
                                domain="[('segment_type_id', '=', segment_type_id), "
                                       "('level_number', '<', level_number)]")
    child_ids = fields.One2many('budget.segment.value', 'parent_id', string="Children")
    code = fields.Char(string="Code", required=True,
                       help="The code for this level only (not the full path code).")
    name = fields.Char(string="Description", required=True, translate=True)
    full_code = fields.Char(string="Full Code", compute='_compute_full_code',
                            store=True, recursive=True)
    is_leaf = fields.Boolean(string="Is Leaf", compute='_compute_is_leaf', store=True)
    is_last_level = fields.Boolean(string="Is Last Level",
                                   compute='_compute_is_last_level', store=True,
                                   help="True if this value is at the deepest level defined for its segment type.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related='segment_type_id.company_id', store=True)

    # === Account fields (only used when segment type is_economic) ===
    account_id = fields.Many2one('account.account', string="Linked Account",
                                 readonly=True, ondelete='set null',
                                 help="The auto-generated account in Chart of Accounts.")
    account_type = fields.Selection(
        selection=[
            ("asset_receivable", "Receivable"),
            ("asset_cash", "Bank and Cash"),
            ("asset_current", "Current Assets"),
            ("asset_non_current", "Non-current Assets"),
            ("asset_prepayments", "Prepayments"),
            ("asset_fixed", "Fixed Assets"),
            ("liability_payable", "Payable"),
            ("liability_credit_card", "Credit Card"),
            ("liability_current", "Current Liabilities"),
            ("liability_non_current", "Non-current Liabilities"),
            ("equity", "Equity"),
            ("equity_unaffected", "Current Year Earnings"),
            ("income", "Income"),
            ("income_other", "Other Income"),
            ("expense", "Expenses"),
            ("expense_other", "Other Expenses"),
            ("expense_depreciation", "Depreciation"),
            ("expense_direct_cost", "Cost of Revenue"),
            ("off_balance", "Off-Balance Sheet"),
        ],
        string="Account Type",
        help="Required for economic segment values. Determines the account behavior.")
    account_currency_id = fields.Many2one('res.currency', string="Account Currency",
                                          help="Force a specific currency on this account.")
    account_tax_ids = fields.Many2many('account.tax', string="Default Taxes",
                                       help="Default taxes applied on this account.")
    account_tag_ids = fields.Many2many('account.account.tag', string="Account Tags",
                                       help="Tags for custom reporting.")
    account_reconcile = fields.Boolean(string="Allow Reconciliation", default=False)
    account_description = fields.Text(string="Account Description", translate=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        parent_level_id = self.env.context.get('budget_parent_level_id')
        seg_type_id = self.env.context.get('default_segment_type_id')
        if parent_level_id and seg_type_id:
            parent_level = self.env['budget.segment.level'].browse(parent_level_id)
            next_level = self.env['budget.segment.level'].search([
                ('segment_type_id', '=', seg_type_id),
                ('level_number', '=', parent_level.level_number + 1),
            ], limit=1)
            if next_level:
                res['level_id'] = next_level.id
        return res

    _code_parent_uniq = models.Constraint(
        'unique(segment_type_id, parent_id, code)',
        'Code must be unique among siblings within the same segment type.',
    )

    @api.depends('code', 'parent_id.full_code', 'segment_type_id.separator')
    def _compute_full_code(self):
        for rec in self:
            code = rec.code or ''
            parent_code = rec.parent_id.full_code or '' if rec.parent_id else ''
            rec.full_code = parent_code + code

    def _compute_display_name(self):
        for rec in self:
            if rec.full_code and rec.name:
                rec.display_name = "[%s] %s" % (rec.full_code, rec.name)
            else:
                rec.display_name = rec.name or ''

    @api.depends('child_ids')
    def _compute_is_leaf(self):
        for rec in self:
            rec.is_leaf = len(rec.child_ids) == 0

    @api.depends('level_id', 'level_id.level_number', 'segment_type_id.level_ids')
    def _compute_is_last_level(self):
        # Cache max level per segment type to avoid repeated queries
        max_levels = {}
        for rec in self:
            seg_id = rec.segment_type_id.id
            if seg_id not in max_levels:
                levels = rec.segment_type_id.level_ids
                max_levels[seg_id] = max(levels.mapped('level_number')) if levels else 0
            rec.is_last_level = (rec.level_number == max_levels[seg_id]) if max_levels[seg_id] else False

    @api.constrains('code', 'level_id')
    def _check_code_length(self):
        for rec in self:
            if rec.level_id and rec.code:
                expected = rec.level_id.digit_count
                if len(rec.code) != expected:
                    raise ValidationError(
                        _("Code '%s' must be exactly %d character(s) for level '%s'.")
                        % (rec.code, expected, rec.level_id.name)
                    )

    @api.constrains('parent_id', 'level_id')
    def _check_parent_level(self):
        for rec in self:
            if rec.parent_id:
                if rec.parent_id.segment_type_id != rec.segment_type_id:
                    raise ValidationError(
                        _("Child value must belong to the same segment type as its parent.")
                    )
                expected_level = rec.parent_id.level_number + 1
                if rec.level_number != expected_level:
                    raise ValidationError(
                        _("Child of '%s' (Level %d) must be Level %d, not Level %d.")
                        % (rec.parent_id.name, rec.parent_id.level_number,
                           expected_level, rec.level_number)
                    )

    @api.constrains('is_economic', 'account_type', 'is_last_level')
    def _check_economic_account_type(self):
        for rec in self:
            if rec.is_economic and rec.is_last_level and not rec.account_type:
                raise ValidationError(
                    _("Account Type is required for leaf-level economic segment values.")
                )

    @api.onchange('segment_type_id')
    def _onchange_segment_type_id(self):
        self.level_id = False
        self.parent_id = False

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        """Auto-set level to the next level after the parent."""
        if self.parent_id and self.segment_type_id:
            next_level_number = self.parent_id.level_number + 1
            next_level = self.env['budget.segment.level'].search([
                ('segment_type_id', '=', self.segment_type_id.id),
                ('level_number', '=', next_level_number),
            ], limit=1)
            if next_level:
                self.level_id = next_level.id

    # === Auto-sync with account.account ===

    def _prepare_account_vals(self):
        """Prepare values for creating/updating account.account."""
        self.ensure_one()
        vals = {
            'name': self.name,
            'account_type': self.account_type,
            'currency_id': self.account_currency_id.id or False,
            'tax_ids': [(6, 0, self.account_tax_ids.ids)],
            'tag_ids': [(6, 0, self.account_tag_ids.ids)],
            'reconcile': self.account_reconcile,
            'description': self.account_description or False,
        }
        return vals

    def _sync_account(self):
        """Create or update the linked account.account record."""
        for rec in self:
            if not rec.is_economic or not rec.is_last_level:
                continue
            if not rec.account_type:
                continue
            account_vals = rec._prepare_account_vals()
            if rec.account_id:
                # Update existing account
                rec.account_id.write(account_vals)
                # Update code if changed
                if rec.account_id.code != rec.full_code:
                    rec.account_id.code = rec.full_code
            else:
                # Create new account
                account_vals['code'] = rec.full_code
                if rec.company_id:
                    account_vals['company_ids'] = [(6, 0, [rec.company_id.id])]
                account = self.env['account.account'].create(account_vals)
                rec.account_id = account.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('is_economic')._sync_account()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Re-sync if any account-relevant field changed
        account_fields = {
            'name', 'code', 'full_code', 'account_type', 'account_currency_id',
            'account_tax_ids', 'account_tag_ids', 'account_reconcile',
            'account_description', 'active',
        }
        if account_fields & set(vals.keys()):
            self.filtered('is_economic')._sync_account()
        # Sync active/archive state
        if 'active' in vals:
            for rec in self.filtered('is_economic'):
                if rec.account_id:
                    rec.account_id.active = vals['active']
        return res
