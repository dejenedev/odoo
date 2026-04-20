# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PkiSigningConfig(models.Model):
    _name = 'pki.signing.config'
    _description = 'PKI Digital Signature Configuration'
    _order = 'model_name'

    name = fields.Char(compute='_compute_name', store=True)
    model_id = fields.Many2one(
        'ir.model', string="Document Model", required=True,
        ondelete='cascade',
        domain=[('transient', '=', False)],
        help="Select the document type that requires digital signing.")
    model_name = fields.Char(
        related='model_id.model', store=True, readonly=True, index=True)
    field_ids = fields.Many2many(
        'ir.model.fields', 'pki_signing_config_field_rel',
        'config_id', 'field_id',
        string="Fields to Sign",
        domain="[('model_id', '=', model_id), ('store', '=', True), "
               "('ttype', 'not in', ('binary', 'one2many', 'many2many'))]",
        help="Select fields whose values will be included in the cryptographic hash. "
             "Changes to these fields after signing will be detected as tampering.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company)
    require_visual_signature = fields.Boolean(
        string="Require Visual Signature", default=True,
        help="If checked, approvers must draw their signature.")

    _sql_constraints = [
        ('model_company_uniq', 'UNIQUE(model_id, company_id)',
         'Each model can only have one digital signature configuration per company.'),
    ]

    @api.depends('model_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.model_id.name if rec.model_id else ''

    @api.model
    def get_config_for_model(self, model_name, company_id=None):
        """Get signing config for a model. Returns False if not configured."""
        if not company_id:
            company_id = self.env.company.id
        return self.search([
            ('model_name', '=', model_name),
            ('active', '=', True),
            '|', ('company_id', '=', company_id), ('company_id', '=', False),
        ], limit=1) or False

    def get_hash_field_names(self):
        """Return list of field names to include in hash."""
        self.ensure_one()
        if self.field_ids:
            return self.field_ids.mapped('name')
        return []
