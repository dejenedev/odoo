# -*- coding: utf-8 -*-
from odoo import fields, models


class AmeDelegation(models.Model):
    _name = 'ame.delegation'
    _description = 'AME Delegation'
    _order = 'create_date desc'

    delegator_id = fields.Many2one(
        'res.users', string="Delegator", required=True,
        default=lambda self: self.env.user)
    delegate_id = fields.Many2one(
        'res.users', string="Delegate", required=True)

    delegation_type = fields.Selection([
        ('permanent', 'Permanent'),
        ('date_range', 'Date Range'),
        ('per_transaction', 'Per Transaction Type'),
    ], required=True, default='date_range')

    transaction_type_id = fields.Many2one(
        'ame.transaction.type',
        help="If set, delegation applies only to this transaction type.")

    start_date = fields.Date(
        required=True, default=fields.Date.context_today)
    end_date = fields.Date()
    reason = fields.Text()

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)
