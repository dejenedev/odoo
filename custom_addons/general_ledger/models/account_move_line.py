# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = ['account.move', 'ame.approval.mixin']
    _name = 'account.move'

    hide_post_button = fields.Boolean(
        compute='_compute_hide_post_button_override')

    @api.depends('state', 'auto_post', 'date', 'ame_state', 'ame_instance_id')
    def _compute_hide_post_button_override(self):
        """Override to hide Post/Confirm when AME approval is pending."""
        for move in self:
            # Standard logic
            move.hide_post_button = (
                move.state != 'draft'
                or (move.auto_post != 'no'
                    and move.date
                    and move.date > fields.Date.context_today(move))
            )
            # AME: hide if pending approval or if vendor bill needs approval
            if not move.hide_post_button and move.ame_instance_id:
                if move.ame_state in ('pending', 'rejected'):
                    move.hide_post_button = True
            if not move.hide_post_button and move.move_type in ('in_invoice', 'in_refund'):
                tt = self.env['ame.transaction.type'].get_for_model(
                    'account.move', move.company_id.id)
                if tt and move.ame_state != 'approved':
                    move.hide_post_button = True

    ame_hide_cancel = fields.Boolean(
        compute='_compute_ame_hide_cancel')

    @api.depends('ame_state', 'ame_instance_id')
    def _compute_ame_hide_cancel(self):
        for move in self:
            move.ame_hide_cancel = bool(
                move.ame_instance_id and move.ame_state == 'pending')

    submitted_for_payment = fields.Boolean(
        string="Submitted for Payment", default=False, copy=False,
        help="When checked, this bill is visible to the paying organization "
             "for consolidated payment processing.")
    clearing_move_id = fields.Many2one(
        'account.move', string="Clearing Entry", copy=False, readonly=True,
        help="The inter-company clearing journal entry created on submission.")
    budget_payment_state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('submitted', 'Submitted for Payment'),
        ('paid', 'Paid'),
    ], string="Budget Payment Status", compute='_compute_budget_payment_state',
        store=True)
    is_paying_org_company = fields.Boolean(
        string="Is Paying Org Company",
        compute='_compute_is_paying_org_company')

    @api.depends('submitted_for_payment', 'payment_state', 'move_type',
                 'state', 'ame_state')
    def _compute_budget_payment_state(self):
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                move.budget_payment_state = False
            elif not move.submitted_for_payment and move.payment_state in ('paid', 'in_payment'):
                # Fully paid (MoF has processed — submitted_for_payment was reset)
                move.budget_payment_state = 'paid'
            elif move.submitted_for_payment:
                # Submitted to MoF, awaiting consolidated payment
                move.budget_payment_state = 'submitted'
            elif move.ame_state == 'rejected':
                move.budget_payment_state = 'rejected'
            elif move.ame_state == 'approved':
                move.budget_payment_state = 'approved'
            elif move.ame_state == 'pending':
                move.budget_payment_state = 'pending_approval'
            elif move.state == 'draft':
                move.budget_payment_state = 'draft'
            else:
                move.budget_payment_state = 'draft'

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
        if not self.env.context.get('ame_auto_post'):
            for move in self:
                # Block posting if AME approval is required but not yet complete
                if move.ame_instance_id and move.ame_state not in ('approved', 'none', False):
                    raise UserError(_(
                        "Cannot post '%s': approval is pending.\n\n"
                        "The entry will be posted automatically once approved."
                    ) % move.name)
                # Block direct posting of vendor bills — must go through AME
                if move.move_type in ('in_invoice', 'in_refund'):
                    tt = self.env['ame.transaction.type'].get_for_model(
                        'account.move', move.company_id.id)
                    if tt and move.ame_state != 'approved':
                        raise UserError(_(
                            "Vendor bills require approval before posting.\n\n"
                            "Please use the 'Request Approval' button to submit "
                            "'%s' for approval."
                        ) % move.name)

            zero_lines = move.line_ids.filtered(
                lambda l: l.debit == 0 and l.credit == 0
                and l.display_type not in ('line_section', 'line_note')
            )
            if zero_lines:
                raise UserError(
                    _("Cannot post journal entry '%s': lines with zero debit and credit are not allowed.")
                    % move.name
                )
            # Budget code mandatory for expense and revenue account lines
            budget_required_lines = move.line_ids.filtered(
                lambda l: l.account_id.account_type in ('expense', 'income', 'expense_direct_cost')
                and l.display_type not in ('line_section', 'line_note', 'tax')
                and not l.budget_combination_id
            )
            if budget_required_lines:
                accounts = ', '.join(budget_required_lines.mapped('account_id.display_name'))
                raise UserError(_(
                    "Cannot post '%s': Budget Code Combination is required "
                    "for expense and revenue account lines.\n\nMissing on: %s"
                ) % (move.name, accounts))
        res = super().action_post()
        # Copy budget code from invoice lines to their tax lines
        self._propagate_budget_code_to_tax_lines()
        return res

    def _propagate_budget_code_to_tax_lines(self):
        """Propagate budget code and optionally account from invoice lines
        to their related tax lines.

        If the tax has 'override_account_from_bill' enabled:
          - Tax line account is replaced with the invoice line's account
          - Tax line gets the same budget code as the invoice line

        Otherwise:
          - Tax line gets the same budget code as the invoice line
          - Tax line account stays as the tax's configured account
        """
        for move in self:
            if not move.is_invoice(True):
                continue
            base_lines = move.line_ids.filtered(
                lambda l: l.display_type == 'product' and l.budget_combination_id)
            if not base_lines:
                continue
            tax_lines = move.line_ids.filtered(
                lambda l: l.display_type == 'tax')
            if not tax_lines:
                continue

            for tax_line in tax_lines:
                tax = tax_line.tax_line_id
                if not tax:
                    matching_base = base_lines[0] if len(base_lines) == 1 else None
                else:
                    matching_bases = base_lines.filtered(lambda l: tax in l.tax_ids)
                    matching_base = matching_bases[0] if matching_bases else (
                        base_lines[0] if len(base_lines) == 1 else None)
                if not matching_base:
                    continue

                vals = {
                    'budget_combination_id': matching_base.budget_combination_id.id,
                }

                # If tax has override_account_from_bill, use invoice line's account
                if tax and tax.override_account_from_bill:
                    vals['account_id'] = matching_base.account_id.id

                tax_line.with_context(
                    skip_budget_propagation=True,
                    check_move_validity=False,
                ).write(vals)

    def button_cancel(self):
        for move in self:
            if move.ame_instance_id and move.ame_state == 'pending':
                raise UserError(_(
                    "Cannot cancel '%s': approval is pending.\n\n"
                    "Please cancel the approval first."
                ) % move.name)
        return super().button_cancel()

    def write(self, vals):
        res = super().write(vals)
        # Propagate budget codes to tax lines on save
        if any(k in vals for k in ('invoice_line_ids', 'line_ids')):
            self._propagate_budget_code_to_tax_lines()
        return res

    def action_submit_for_ame_approval(self):
        """Override to validate budget codes before submitting for approval."""
        # First propagate budget codes to tax lines
        self._propagate_budget_code_to_tax_lines()

        for move in self:
            if move.is_invoice(True):
                missing_lines = move.invoice_line_ids.filtered(
                    lambda l: l.account_id.account_type in (
                        'expense', 'income', 'expense_direct_cost')
                    and l.display_type not in ('line_section', 'line_note')
                    and not l.budget_combination_id
                )
                if missing_lines:
                    accounts = ', '.join(
                        missing_lines.mapped('account_id.display_name'))
                    raise UserError(_(
                        "Cannot submit for approval: Budget Code Combination "
                        "is required for expense and revenue lines.\n\n"
                        "Missing on: %s"
                    ) % accounts)
        return super().action_submit_for_ame_approval()

    def _on_ame_approved(self):
        """Callback when AME approval is complete — auto-post the bill."""
        for move in self:
            if move.state == 'draft' and move.move_type in ('in_invoice', 'in_refund'):
                move.with_context(ame_auto_post=True).action_post()

    def _on_ame_rejected(self):
        """Callback when AME approval is rejected."""
        pass  # Bill stays in draft, user can modify and resubmit

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

            # Suppress Odoo's "Invoice Paid" tracking during clearing
            move_ctx = move.with_context(mail_notrack=True)

            # Create clearing entry: DR Payable, CR Clearing
            clearing_move = self.env['account.move'].with_context(
                default_move_type='entry', mail_notrack=True,
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
            # Use tracking_disable to suppress "Invoice Paid" tracking on the move
            bill_payable_account = payable_line[0].account_id
            clearing_payable = clearing_move.line_ids.filtered(
                lambda l: l.account_id == bill_payable_account
            )
            (payable_line + clearing_payable).with_context(
                tracking_disable=True).reconcile()

            move.with_context(tracking_disable=True).write({
                'submitted_for_payment': True,
                'clearing_move_id': clearing_move.id,
            })

            # Post our own tracking message instead
            move.message_post(
                body=_("Submitted for consolidated payment. "
                       "Clearing entry: %s") % clearing_move.name,
                subject=_("Submitted for Payment"),
                subtype_xmlid='mail.mt_note',
            )

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
            if not line.company_id:
                line.allowed_budget_combination_ids = False
                continue

            combo_ids = None  # None = not filtered yet

            # 1. Filter by organization segment (always)
            org = self.env['budget.organization'].search([
                ('company_id', '=', line.company_id.id),
            ], limit=1)
            if org and org.segment_value_ids:
                org_combo_lines = self.env['budget.code.combination.line'].search([
                    ('segment_value_id', 'in', org.segment_value_ids.ids),
                ])
                org_combo_ids = set(org_combo_lines.mapped('combination_id').ids)
                combo_ids = org_combo_ids

            # 2. Filter by economic segment (match account)
            if line.account_id:
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
                    eco_combo_lines = self.env['budget.code.combination.line'].search([
                        ('segment_value_id', '=', eco_value.id),
                    ])
                    eco_combo_ids = set(eco_combo_lines.mapped('combination_id').ids)
                    # Intersect with org filter
                    if combo_ids is not None:
                        combo_ids = combo_ids & eco_combo_ids
                    else:
                        combo_ids = eco_combo_ids
                else:
                    # Account has no matching economic segment — no combinations
                    combo_ids = set()

            # 3. Apply company filter and return
            domain = [('company_id', '=', line.company_id.id)]
            if combo_ids is not None:
                domain.append(('id', 'in', list(combo_ids)))
            line.allowed_budget_combination_ids = self.env['budget.code.combination'].search(domain)

    def write(self, vals):
        res = super().write(vals)
        if 'budget_combination_id' in vals and not self.env.context.get('skip_budget_propagation'):
            # Propagate to related tax lines via the move-level method
            moves = self.mapped('move_id').filtered(lambda m: m.is_invoice(True))
            if moves:
                moves._propagate_budget_code_to_tax_lines()
        return res

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
                'general_ledger.view_budget_code_combination_popup_form').id,
            'target': 'new',
        }
