# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class BudgetCombinationTrialBalance(models.Model):
    _name = 'budget.combination.trial.balance'
    _description = 'Trial Balance by Budget Code Combination'
    _auto = False
    _order = 'combination_code'

    budget_combination_id = fields.Many2one(
        'budget.code.combination', string="Budget Code", readonly=True)
    combination_code = fields.Char(
        string="Code Combination", readonly=True)
    account_id = fields.Many2one(
        'account.account', string="Account", readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string="Partner", readonly=True)
    company_id = fields.Many2one(
        'res.company', string="Company", readonly=True)
    move_id = fields.Many2one(
        'account.move', string="Journal Entry", readonly=True)
    date = fields.Date(string="Date", readonly=True)
    debit = fields.Float(string="Debit", readonly=True)
    credit = fields.Float(string="Credit", readonly=True)
    balance = fields.Float(string="Balance", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    aml.id AS id,
                    aml.budget_combination_id,
                    bcc.combination_code,
                    aml.account_id,
                    aml.partner_id,
                    aml.company_id,
                    aml.move_id,
                    aml.date,
                    aml.debit,
                    aml.credit,
                    (aml.debit - aml.credit) AS balance
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN budget_code_combination bcc ON bcc.id = aml.budget_combination_id
                WHERE am.state = 'posted'
                  AND aml.display_type NOT IN ('line_section', 'line_note')
                  AND aml.budget_combination_id IS NOT NULL
            )
        """ % self._table)
