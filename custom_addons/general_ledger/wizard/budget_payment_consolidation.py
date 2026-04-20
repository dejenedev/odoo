# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BudgetPaymentConsolidationLine(models.TransientModel):
    _name = 'budget.payment.consolidation.line'
    _description = 'Payment Consolidation Bill Line'

    wizard_id = fields.Many2one(
        'budget.payment.consolidation', string="Wizard",
        required=True, ondelete='cascade')
    selected = fields.Boolean(string="Select", default=True)
    bill_id = fields.Integer(string="Bill ID", required=True)
    bill_name = fields.Char(string="Bill")
    partner_name = fields.Char(string="Vendor")
    company_name = fields.Char(string="Company")
    company_id = fields.Integer(string="Company ID")
    invoice_date = fields.Date(string="Bill Date")
    amount_total = fields.Float(string="Total")
    amount_residual = fields.Float(string="Amount Due")
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)


class BudgetPaymentConsolidation(models.TransientModel):
    _name = 'budget.payment.consolidation'
    _description = 'Payment Consolidation Wizard'

    paying_org_id = fields.Many2one(
        'budget.organization', string="Paying Organization",
        required=True,
        domain="[('is_paying_org', '=', True)]",
        default=lambda self: self.env['budget.organization'].search(
            [('is_paying_org', '=', True)], limit=1))
    payment_journal_id = fields.Many2one(
        'account.journal', string="Payment Journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash')), "
               "('company_id', '=', paying_company_id)]",
        help="Journal to use for consolidated payments.")
    paying_company_id = fields.Many2one(
        related='paying_org_id.company_id', string="Paying Company")
    source_bank_account_id = fields.Many2one(
        'res.partner.bank', string="Source Bank Account",
        domain="[('id', 'in', available_bank_ids)]",
        help="Bank account from which consolidated payments are sent.")
    available_bank_ids = fields.Many2many(
        'res.partner.bank', compute='_compute_available_bank_ids')
    date_from = fields.Date(string="Bills From")
    date_to = fields.Date(string="Bills To")
    line_ids = fields.One2many(
        'budget.payment.consolidation.line', 'wizard_id',
        string="Bills to Pay")
    total_amount = fields.Float(
        string="Total Amount", compute='_compute_total_amount')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], default='draft')
    created_move_ids = fields.Many2many(
        'account.move', string="Created Entries", readonly=True)
    message = fields.Char(string="Message", readonly=True)

    @api.depends('paying_org_id')
    def _compute_available_bank_ids(self):
        for rec in self:
            if rec.paying_org_id and rec.paying_org_id.bank_account_ids:
                rec.available_bank_ids = rec.paying_org_id.bank_account_ids
            else:
                rec.available_bank_ids = False

    @api.onchange('paying_org_id')
    def _onchange_paying_org_id(self):
        if self.paying_org_id:
            self.payment_journal_id = self.paying_org_id.payment_journal_id
            self.source_bank_account_id = self.paying_org_id.bank_account_ids[:1]

    @api.depends('line_ids.selected', 'line_ids.amount_residual')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(
                line.amount_residual
                for line in rec.line_ids
                if line.selected
            )

    @api.model
    def default_get(self, fields_list):
        """Check that current company is the paying organization."""
        res = super().default_get(fields_list)
        paying_org = self.env['budget.organization'].search([
            ('is_paying_org', '=', True),
        ], limit=1)
        if paying_org and paying_org.company_id != self.env.company:
            raise UserError(_(
                "Payment Consolidation is only available for the paying "
                "organization (%s). Please switch to company '%s'."
            ) % (paying_org.name, paying_org.company_id.name))
        return res

    def action_load_bills(self):
        """Load submitted bills into wizard lines."""
        self.ensure_one()
        # Clear existing lines
        self.line_ids.unlink()

        domain = [
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('submitted_for_payment', '=', True),
        ]
        if self.date_from:
            domain.append(('invoice_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('invoice_date', '<=', self.date_to))

        # Search across all companies with sudo
        bills = self.env['account.move'].sudo().search(domain)

        line_vals = []
        for bill in bills:
            # The clearing entry amount is what needs to be paid
            clearing = bill.clearing_move_id
            amount = 0.0
            if clearing:
                clearing_line = clearing.line_ids.filtered(
                    lambda l: l.account_id.account_type != 'liability_payable'
                )
                amount = sum(clearing_line.mapped('credit'))
            line_vals.append((0, 0, {
                'bill_id': bill.id,
                'bill_name': bill.name,
                'partner_name': bill.partner_id.name or '',
                'company_name': bill.company_id.name or '',
                'company_id': bill.company_id.id,
                'invoice_date': bill.invoice_date,
                'amount_total': bill.amount_total,
                'amount_residual': amount or bill.amount_total,
            }))

        self.write({'line_ids': line_vals})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'budget.payment.consolidation',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        """Create bank payment entries at the paying organization.

        The clearing entries (DR Payable, CR Clearing) were already created
        when each company submitted their bills. This step only creates the
        bank payment at the paying org: DR Clearing Account, CR Bank.
        """
        self.ensure_one()
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_("Please select at least one bill to pay."))
        if not self.payment_journal_id:
            raise UserError(_("Please select a payment journal."))
        if not self.source_bank_account_id:
            raise UserError(_("Please select a source bank account for payment."))

        paying_org = self.paying_org_id
        paying_company = paying_org.company_id

        if not paying_org.clearing_account_id or not paying_org.clearing_journal_id:
            raise UserError(_(
                "Paying organization '%s' must have a Clearing Account "
                "and Clearing Journal configured."
            ) % paying_org.name)

        today = fields.Date.context_today(self)
        created_moves = self.env['account.move']

        # Get the bank account from the payment journal
        bank_account = (
            self.payment_journal_id.outbound_payment_method_line_ids[:1]
            .payment_account_id
            or self.payment_journal_id.company_id
            .account_journal_suspense_account_id
        )

        # Group by source company for cleaner entries
        lines_by_company = {}
        for line in selected_lines:
            lines_by_company.setdefault(line.company_id, [])
            lines_by_company[line.company_id].append(line)

        for company_id, lines in lines_by_company.items():
            total = sum(l.amount_residual for l in lines)
            bill_names = ', '.join(l.bill_name for l in lines)

            # Create bank payment: DR Clearing Account, CR Bank
            payment_move = self.env['account.move'].with_company(
                paying_company
            ).create({
                'journal_id': paying_org.clearing_journal_id.id,
                'date': today,
                'ref': _('Consolidated payment: %s') % bill_names,
                'line_ids': [
                    (0, 0, {
                        'account_id': paying_org.clearing_account_id.id,
                        'debit': abs(total),
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'account_id': bank_account.id,
                        'credit': abs(total),
                        'debit': 0.0,
                    }),
                ],
            })
            payment_move.action_post()
            created_moves |= payment_move

            # Mark bills as no longer submitted
            for line in lines:
                bill = self.env['account.move'].sudo().browse(line.bill_id)
                if bill.exists():
                    bill.write({'submitted_for_payment': False})

        # Create persistent payment record
        payment_line_vals = []
        for line in selected_lines:
            payment_line_vals.append((0, 0, {
                'bill_name': line.bill_name,
                'partner_name': line.partner_name,
                'company_name': line.company_name,
                'amount': line.amount_residual,
                'bill_id': line.bill_id,
            }))
        self.env['budget.consolidated.payment'].create({
            'paying_org_id': self.paying_org_id.id,
            'payment_journal_id': self.payment_journal_id.id,
            'source_bank_account_id': self.source_bank_account_id.id,
            'payment_date': fields.Date.context_today(self),
            'total_amount': self.total_amount,
            'bill_count': len(selected_lines),
            'payment_move_ids': [(6, 0, created_moves.ids)],
            'line_ids': payment_line_vals,
        })

        self.write({
            'state': 'done',
            'created_move_ids': [(6, 0, created_moves.ids)],
            'message': _("%d payment(s) created for %d bill(s). Total: %s %s") % (
                len(created_moves), len(selected_lines),
                self.currency_id.symbol, '{:,.2f}'.format(self.total_amount)),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'budget.payment.consolidation',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
