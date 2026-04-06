# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class BudgetSegmentTrialBalance(models.Model):
    _name = 'budget.segment.trial.balance'
    _description = 'Trial Balance by Budget Segment'
    _auto = False
    _order = 'combination_code'

    budget_combination_id = fields.Many2one(
        'budget.code.combination', string="Budget Code", readonly=True)
    combination_code = fields.Char(
        string="Code Combination", readonly=True)
    # Up to 7 segment value columns, ordered by segment type sequence
    segment_1_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 1", readonly=True)
    segment_2_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 2", readonly=True)
    segment_3_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 3", readonly=True)
    segment_4_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 4", readonly=True)
    segment_5_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 5", readonly=True)
    segment_6_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 6", readonly=True)
    segment_7_value_id = fields.Many2one(
        'budget.segment.value', string="Segment 7", readonly=True)
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

    def _get_segment_labels(self):
        """Return segment type names ordered by sequence for column headers."""
        types = self.env['budget.segment.type'].sudo().search(
            [], order='sequence', limit=7)
        return {i + 1: t.name for i, t in enumerate(types)}

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH ranked_segments AS (
                    SELECT
                        bcl.combination_id,
                        bcl.segment_value_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY bcl.combination_id
                            ORDER BY bst.sequence
                        ) AS rn
                    FROM budget_code_combination_line bcl
                    JOIN budget_segment_type bst ON bst.id = bcl.segment_type_id
                )
                SELECT
                    aml.id AS id,
                    aml.budget_combination_id,
                    bcc.combination_code,
                    rs1.segment_value_id AS segment_1_value_id,
                    rs2.segment_value_id AS segment_2_value_id,
                    rs3.segment_value_id AS segment_3_value_id,
                    rs4.segment_value_id AS segment_4_value_id,
                    rs5.segment_value_id AS segment_5_value_id,
                    rs6.segment_value_id AS segment_6_value_id,
                    rs7.segment_value_id AS segment_7_value_id,
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
                LEFT JOIN ranked_segments rs1
                    ON rs1.combination_id = bcc.id AND rs1.rn = 1
                LEFT JOIN ranked_segments rs2
                    ON rs2.combination_id = bcc.id AND rs2.rn = 2
                LEFT JOIN ranked_segments rs3
                    ON rs3.combination_id = bcc.id AND rs3.rn = 3
                LEFT JOIN ranked_segments rs4
                    ON rs4.combination_id = bcc.id AND rs4.rn = 4
                LEFT JOIN ranked_segments rs5
                    ON rs5.combination_id = bcc.id AND rs5.rn = 5
                LEFT JOIN ranked_segments rs6
                    ON rs6.combination_id = bcc.id AND rs6.rn = 6
                LEFT JOIN ranked_segments rs7
                    ON rs7.combination_id = bcc.id AND rs7.rn = 7
                WHERE am.state = 'posted'
                  AND aml.display_type NOT IN ('line_section', 'line_note')
                  AND aml.budget_combination_id IS NOT NULL
            )
        """ % self._table)
