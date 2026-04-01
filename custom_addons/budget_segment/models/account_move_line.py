# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    budget_combination_id = fields.Many2one(
        'budget.code.combination',
        string="Budget Code Combination",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    budget_combination_code = fields.Char(
        related='budget_combination_id.combination_code',
        string="Budget Code",
        store=True,
    )

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
