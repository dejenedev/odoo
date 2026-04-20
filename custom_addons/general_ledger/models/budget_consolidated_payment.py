# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BudgetConsolidatedPayment(models.Model):
    _name = 'budget.consolidated.payment'
    _description = 'Consolidated Payment Record'
    _order = 'payment_date desc, id desc'
    _inherit = ['mail.thread', 'ame.approval.mixin']

    name = fields.Char(string="Reference", compute='_compute_name', store=True)
    paying_org_id = fields.Many2one(
        'budget.organization', string="Paying Organization",
        required=True, readonly=True)
    payment_journal_id = fields.Many2one(
        'account.journal', string="Payment Journal", readonly=True)
    source_bank_account_id = fields.Many2one(
        'res.partner.bank', string="Source Bank Account", readonly=True)
    payment_date = fields.Date(string="Payment Date", readonly=True)
    total_amount = fields.Monetary(
        string="Total Amount", currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    bill_count = fields.Integer(string="Bills Paid", readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], default='draft', tracking=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)

    # Related entries
    payment_move_ids = fields.Many2many(
        'account.move', 'budget_consolidated_payment_move_rel',
        'payment_id', 'move_id',
        string="Payment Entries", readonly=True)
    line_ids = fields.One2many(
        'budget.consolidated.payment.line', 'payment_id',
        string="Bills Paid", readonly=True)

    created_by_id = fields.Many2one(
        'res.users', string="Created By",
        default=lambda self: self.env.user, readonly=True)

    @api.depends('paying_org_id', 'payment_date')
    def _compute_name(self):
        for rec in self:
            org = rec.paying_org_id.code or 'PAY'
            date = rec.payment_date or ''
            rec.name = '%s/%s/%s' % (org, date, rec.id or 'New')

    def action_confirm(self):
        """Confirm the consolidated payment — post the journal entries."""
        self.ensure_one()
        for move in self.payment_move_ids:
            if move.state == 'draft':
                move.action_post()
        self.write({'state': 'done'})

    def _on_ame_approved(self):
        """AME callback — auto-confirm when approved."""
        for rec in self:
            rec.action_confirm()

    def _on_ame_rejected(self):
        """AME callback — handle rejection."""
        pass


class BudgetConsolidatedPaymentLine(models.Model):
    _name = 'budget.consolidated.payment.line'
    _description = 'Consolidated Payment Line'
    _order = 'id'

    payment_id = fields.Many2one(
        'budget.consolidated.payment', required=True, ondelete='cascade')
    bill_name = fields.Char(string="Bill")
    partner_name = fields.Char(string="Vendor")
    company_name = fields.Char(string="Company")
    amount = fields.Float(string="Amount Paid")
    bill_id = fields.Integer(string="Bill ID")
