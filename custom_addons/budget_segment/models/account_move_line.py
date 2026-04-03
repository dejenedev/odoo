# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    submitted_for_payment = fields.Boolean(
        string="Submitted for Payment", default=False, copy=False,
        help="When checked, this bill is visible to the paying organization "
             "for consolidated payment processing.")
    clearing_move_id = fields.Many2one(
        'account.move', string="Clearing Entry", copy=False, readonly=True,
        help="The inter-company clearing journal entry created on submission.")
    budget_payment_state = fields.Selection([
        ('not_submitted', 'Not Submitted'),
        ('submitted', 'Submitted'),
        ('paid', 'Paid'),
    ], string="Budget Payment Status", compute='_compute_budget_payment_state',
        store=True)
    is_paying_org_company = fields.Boolean(
        string="Is Paying Org Company",
        compute='_compute_is_paying_org_company')

    @api.depends('submitted_for_payment', 'payment_state', 'move_type')
    def _compute_budget_payment_state(self):
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                move.budget_payment_state = False
            elif move.submitted_for_payment:
                # Still awaiting MoF payment (clearing reconciled but not yet disbursed)
                move.budget_payment_state = 'submitted'
            elif move.payment_state in ('paid', 'in_payment', 'reversed'):
                move.budget_payment_state = 'paid'
            else:
                move.budget_payment_state = 'not_submitted'

    def _compute_is_paying_org_company(self):
        paying_org = self.env['budget.organization'].sudo().search([
            ('is_paying_org', '=', True),
        ], limit=1)
        paying_company_id = paying_org.company_id.id if paying_org else False
        for move in self:
            move.is_paying_org_company = (
                move.company_id.id == paying_company_id if paying_company_id else False
            )

    def action_post(self):
        for move in self:
            zero_lines = move.line_ids.filtered(
                lambda l: l.debit == 0 and l.credit == 0
                and l.display_type not in ('line_section', 'line_note')
            )
            if zero_lines:
                raise UserError(
                    _("Cannot post journal entry '%s': lines with zero debit and credit are not allowed.")
                    % move.name
                )
            # Budget code mandatory for expense account lines
            expense_lines = move.line_ids.filtered(
                lambda l: l.account_id.account_type == 'expense'
                and l.display_type not in ('line_section', 'line_note')
                and not l.budget_combination_id
            )
            if expense_lines:
                accounts = ', '.join(expense_lines.mapped('account_id.display_name'))
                raise UserError(_(
                    "Cannot post '%s': Budget Code Combination is required "
                    "for expense account lines.\n\nMissing on: %s"
                ) % (move.name, accounts))
        return super().action_post()

    def action_submit_for_payment(self):
        """Submit posted vendor bills for consolidated payment.

        Creates a clearing journal entry in the bill's company:
          DR Accounts Payable (vendor partner)
          CR Clearing Account
        Then reconciles with the bill so the bill shows as Paid.
        """
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                raise UserError(_("Only vendor bills can be submitted for payment."))
            if move.state != 'posted':
                raise UserError(_("Only posted bills can be submitted for payment."))
            if move.payment_state not in ('not_paid', 'partial'):
                raise UserError(_("Bill '%s' is already paid.") % move.name)

            # Get the organization for this bill's company
            bill_org = self.env['budget.organization'].search([
                ('company_id', '=', move.company_id.id),
            ], limit=1)
            if not bill_org or not bill_org.clearing_account_id or not bill_org.clearing_journal_id:
                raise UserError(_(
                    "Organization for company '%s' must have a Clearing Account "
                    "and Clearing Journal configured."
                ) % move.company_id.name)

            # Find the payable line on the bill
            payable_line = move.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
                and not l.reconciled
            )
            if not payable_line:
                raise UserError(_(
                    "Bill '%s' has no unreconciled payable line."
                ) % move.name)

            amount = move.amount_residual

            # Create clearing entry: DR Payable, CR Clearing
            clearing_move = self.env['account.move'].with_context(
                default_move_type='entry'
            ).create({
                'move_type': 'entry',
                'journal_id': bill_org.clearing_journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': _('Payment submission: %s') % move.name,
                'line_ids': [
                    (0, 0, {
                        'account_id': payable_line[0].account_id.id,
                        'partner_id': move.partner_id.id,
                        'debit': amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'account_id': bill_org.clearing_account_id.id,
                        'credit': amount,
                        'debit': 0.0,
                    }),
                ],
            })
            clearing_move.action_post()

            # Reconcile clearing entry payable line with bill's payable line
            # Filter by the exact same account as the bill's payable line
            bill_payable_account = payable_line[0].account_id
            clearing_payable = clearing_move.line_ids.filtered(
                lambda l: l.account_id == bill_payable_account
            )
            (payable_line + clearing_payable).reconcile()

            move.write({
                'submitted_for_payment': True,
                'clearing_move_id': clearing_move.id,
            })

    def action_unsubmit_for_payment(self):
        """Withdraw bill from consolidated payment queue.

        Reverses the clearing entry and unreconciles the bill.
        """
        for move in self:
            if move.clearing_move_id and move.clearing_move_id.state == 'posted':
                # Unreconcile first
                clearing_payable = move.clearing_move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable'
                    and l.reconciled
                )
                if clearing_payable and clearing_payable.matched_debit_ids:
                    clearing_payable.matched_debit_ids.unlink()
                if clearing_payable and clearing_payable.matched_credit_ids:
                    clearing_payable.matched_credit_ids.unlink()
                # Reverse the clearing entry
                move.clearing_move_id._reverse_moves(cancel=True)
            move.write({
                'submitted_for_payment': False,
                'clearing_move_id': False,
            })


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    budget_combination_id = fields.Many2one(
        'budget.code.combination',
        string="Budget Code Combination",
        domain="[('id', 'in', allowed_budget_combination_ids)]",
        tracking=True,
    )
    allowed_budget_combination_ids = fields.Many2many(
        'budget.code.combination',
        compute='_compute_allowed_budget_combination_ids')
    budget_combination_code = fields.Char(
        related='budget_combination_id.combination_code',
        string="Budget Code",
        store=True,
    )

    @api.depends('account_id', 'company_id')
    def _compute_allowed_budget_combination_ids(self):
        for line in self:
            domain = [('company_id', '=', line.company_id.id)]
            if line.account_id:
                # Find economic segment value matching this account
                eco_value = self.env['budget.segment.value'].search([
                    ('is_economic', '=', True),
                    ('account_id', '=', line.account_id.id),
                    ('is_last_level', '=', True),
                ], limit=1)
                if not eco_value:
                    eco_value = self.env['budget.segment.value'].search([
                        ('is_economic', '=', True),
                        ('full_code', '=', line.account_id.code),
                        ('is_last_level', '=', True),
                    ], limit=1)
                if eco_value:
                    # Only show combinations containing this economic value
                    combo_lines = self.env['budget.code.combination.line'].search([
                        ('segment_value_id', '=', eco_value.id),
                    ])
                    domain.append(('id', 'in', combo_lines.mapped('combination_id').ids))
                    # Also filter by organization
                    org = self.env['budget.organization'].search([
                        ('company_id', '=', line.company_id.id),
                    ], limit=1)
                    if org and org.segment_value_ids:
                        org_combo_lines = self.env['budget.code.combination.line'].search([
                            ('segment_value_id', 'in', org.segment_value_ids.ids),
                        ])
                        domain.append(('id', 'in', org_combo_lines.mapped('combination_id').ids))
            line.allowed_budget_combination_ids = self.env['budget.code.combination'].search(domain)

    def action_open_budget_wizard(self):
        """Open the budget code combination wizard for this journal item."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Budget Code'),
            'res_model': 'budget.combination.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_move_line_id': self.id,
            },
        }

    def action_view_budget_combination(self):
        """Open budget combination detail in a readonly popup."""
        self.ensure_one()
        if not self.budget_combination_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget Code Detail'),
            'res_model': 'budget.code.combination',
            'res_id': self.budget_combination_id.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'budget_segment.view_budget_code_combination_popup_form').id,
            'target': 'new',
        }
