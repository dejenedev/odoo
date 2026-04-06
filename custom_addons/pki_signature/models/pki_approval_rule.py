# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PkiApprovalRule(models.Model):
    _name = 'pki.approval.rule'
    _description = 'PKI Approval Rule'
    _order = 'model_name, sequence'

    name = fields.Char(string="Step Name", required=True,
                       help="E.g., 'Department Head Approval', 'Finance Director Sign-off'")
    model_id = fields.Many2one(
        'ir.model', string="Document Type", required=True,
        ondelete='cascade',
        help="The Odoo model this approval rule applies to.")
    model_name = fields.Char(
        related='model_id.model', string="Model Name",
        store=True, readonly=True)
    sequence = fields.Integer(
        string="Step Order", default=10, required=True,
        help="Order in the approval chain. Step 1 signs first, then step 2, etc.")
    group_id = fields.Many2one(
        'res.groups', string="Required Role", required=True,
        help="Only users in this group can approve at this step.")
    min_amount = fields.Float(
        string="Minimum Amount",
        help="If set, this rule only applies when document amount >= this value. "
             "Leave 0 for all amounts.")
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)
    active = fields.Boolean(default=True)
    field_ids = fields.Many2many(
        'ir.model.fields', string="Fields to Hash",
        domain="[('model_id', '=', model_id), "
               "('store', '=', True), "
               "('ttype', 'not in', ('binary', 'one2many', 'many2many'))]",
        help="Document fields whose values will be included in the cryptographic hash. "
             "Changes to these fields after signing will be detected as tampering.")

    _sql_constraints = [
        ('model_sequence_company_uniq',
         'unique(model_id, sequence, company_id)',
         'Each approval step must have a unique sequence per model and company.'),
    ]

    @api.constrains('sequence')
    def _check_sequence_positive(self):
        for rec in self:
            if rec.sequence < 1:
                raise ValidationError(_("Step order must be 1 or greater."))

    @api.model
    def get_rules_for_model(self, model_name, company_id=None, amount=0.0):
        """Get applicable approval rules for a given model.

        :param model_name: str, e.g. 'purchase.order'
        :param company_id: int, company ID (defaults to current company)
        :param amount: float, document amount for threshold filtering
        :returns: recordset of pki.approval.rule ordered by sequence
        """
        if not company_id:
            company_id = self.env.company.id
        domain = [
            ('model_name', '=', model_name),
            ('company_id', '=', company_id),
            ('active', '=', True),
        ]
        rules = self.search(domain, order='sequence')
        if amount:
            rules = rules.filtered(
                lambda r: not r.min_amount or amount >= r.min_amount
            )
        return rules
