# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AmeSubstitution(models.Model):
    _name = 'ame.substitution'
    _description = 'AME Substitution Rule'
    _order = 'start_date desc'

    original_user_id = fields.Many2one(
        'res.users', string="Original Approver", required=True)
    substitute_id = fields.Many2one(
        'res.users', string="Substitute", required=True)
    reason = fields.Selection([
        ('leave', 'On Leave'),
        ('travel', 'Business Travel'),
        ('other', 'Other'),
    ], default='leave')

    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)

    @api.model
    def get_active_substitute(self, user):
        """Return active substitution record for a user, or False."""
        today = fields.Date.context_today(self)
        return self.search([
            ('original_user_id', '=', user.id),
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
        ], limit=1) or False
