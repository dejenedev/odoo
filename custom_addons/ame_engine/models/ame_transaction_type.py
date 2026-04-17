# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AmeTransactionType(models.Model):
    _name = 'ame.transaction.type'
    _description = 'AME Transaction Type'
    _order = 'name'

    name = fields.Char(string="Name", required=True,
                       help="e.g. 'Purchase Order Approval'")
    model_id = fields.Many2one(
        'ir.model', string="Document Model", required=True,
        ondelete='cascade', domain=[('transient', '=', False)])
    model_name = fields.Char(
        related='model_id.model', string="Model Name",
        store=True, readonly=True, index=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)

    flow_pattern = fields.Selection([
        ('serial', 'Serial (Sequential)'),
        ('parallel', 'Parallel (All at Same Level)'),
        ('serial_parallel', 'Serial-Parallel Hybrid'),
        ('first_responder', 'First Responder'),
    ], default='serial', required=True, string="Flow Pattern")
    auto_approve_on_no_rules = fields.Boolean(
        default=False,
        help="If checked, documents auto-approve when no rules fire.")

    # Escalation settings
    escalation_hours = fields.Float(
        string="Default SLA (Hours)", default=0,
        help="Default SLA for approval steps. 0 = no SLA.")
    escalation_action = fields.Selection([
        ('remind', 'Send Reminder'),
        ('escalate', 'Escalate to Manager'),
        ('auto_approve', 'Auto-Approve'),
        ('notify_admin', 'Notify Administrator'),
    ], default='remind', string="Escalation Action")

    # Related
    attribute_ids = fields.One2many(
        'ame.attribute', 'transaction_type_id', string="Attributes")
    rule_ids = fields.One2many(
        'ame.rule', 'transaction_type_id', string="Rules")

    _sql_constraints = [
        ('model_company_uniq', 'UNIQUE(model_id, company_id)',
         'Each model can only have one AME transaction type per company.'),
    ]

    @api.model
    def get_for_model(self, model_name, company_id=None):
        """Get the transaction type for a given model."""
        if not company_id:
            company_id = self.env.company.id
        return self.search([
            ('model_name', '=', model_name),
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], limit=1)
