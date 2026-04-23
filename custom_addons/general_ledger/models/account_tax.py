# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    override_account_from_bill = fields.Boolean(
        string="Override Account from Bill Line",
        default=False,
        help="When enabled on vendor bills, the tax journal item will use "
             "the same account as the invoice line instead of the tax account. "
             "This ensures the tax expense is tracked under the same budget "
             "segment as the invoice line.")
