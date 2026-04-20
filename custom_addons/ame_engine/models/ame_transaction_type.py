# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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

    def write(self, vals):
        res = super().write(vals)
        if 'active' in vals or 'model_id' in vals:
            self._register_hook()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._register_hook()
        return records

    def unlink(self):
        # Remove injected views for models being removed
        for rec in self:
            if rec.model_name:
                view_data = self.env['ir.model.data'].sudo().search([
                    ('module', '=', 'ame_engine'),
                    ('name', '=', 'view_%s_ame_buttons' % rec.model_name.replace('.', '_')),
                ], limit=1)
                if view_data and view_data.res_id:
                    self.env['ir.ui.view'].sudo().browse(view_data.res_id).unlink()
                    view_data.unlink()
        return super().unlink()

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

    def _register_hook(self):
        """Auto-inject ame.approval.mixin fields onto models with Transaction Types."""
        super()._register_hook()
        if not self.env.cr:
            return
        try:
            self.env.cr.execute("""
                SELECT DISTINCT model_name FROM ame_transaction_type
                WHERE active = true AND model_name IS NOT NULL
            """)
            model_names = [r[0] for r in self.env.cr.fetchall()]
        except Exception:
            return

        Mixin = self.env.registry.get('ame.approval.mixin')
        if not Mixin:
            return

        for model_name in model_names:
            Model = self.env.registry.get(model_name)
            if not Model:
                continue
            # Skip if already has the mixin fields
            if 'ame_instance_id' in Model._fields:
                continue

            _logger.info("AME: Auto-injecting approval fields onto %s", model_name)
            # Inject mixin fields onto the model
            for fname, field in Mixin._fields.items():
                if fname not in Model._fields:
                    Model._add_field(fname, field)

            # Inject mixin methods
            for attr_name in dir(Mixin):
                if attr_name.startswith('_') and not attr_name.startswith('action_') \
                        and not attr_name.startswith('_on_ame_') \
                        and not attr_name.startswith('_compute_ame'):
                    continue
                if attr_name.startswith(('action_submit_for_ame',
                                         'action_ame_',
                                         'action_view_ame',
                                         '_on_ame_',
                                         '_compute_ame')):
                    mixin_method = getattr(Mixin, attr_name, None)
                    if callable(mixin_method) and not hasattr(Model, attr_name):
                        setattr(Model, attr_name, mixin_method)

        # Inject approval buttons into form views
        try:
            self.env['ame.view.injector'].sudo()._inject_approval_views()
        except Exception as e:
            _logger.warning("AME: View injection failed: %s", e)
