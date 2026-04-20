# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AmeViewInjector(models.AbstractModel):
    _name = 'ame.view.injector'
    _description = 'AME View Injector'

    @api.model
    def _inject_approval_views(self):
        """Create inherited form views that add AME approval buttons
        for all models that have AME Transaction Types configured."""
        try:
            transaction_types = self.env['ame.transaction.type'].sudo().search([
                ('active', '=', True),
            ])
        except Exception:
            return

        for tt in transaction_types:
            model_name = tt.model_name
            if not model_name:
                continue

            # Check if we already created an AME view for this model
            xmlid = 'ame_engine.view_%s_ame_buttons' % model_name.replace('.', '_')
            existing = self.env['ir.model.data'].sudo().search([
                ('module', '=', 'ame_engine'),
                ('name', '=', 'view_%s_ame_buttons' % model_name.replace('.', '_')),
            ], limit=1)
            if existing:
                continue

            # Find the primary form view for this model
            primary_view = self.env['ir.ui.view'].sudo().search([
                ('model', '=', model_name),
                ('type', '=', 'form'),
                ('inherit_id', '=', False),
            ], order='priority', limit=1)
            if not primary_view:
                continue

            # Check if the view has a <header> element
            arch = """
<form>
    <xpath expr="//header" position="inside">
        <field name="ame_state" invisible="1"/>
        <field name="ame_is_current_approver" invisible="1"/>
        <field name="ame_is_fully_approved" invisible="1"/>
        <button name="action_submit_for_ame_approval"
                string="Request Approval"
                type="object"
                class="btn-primary"
                invisible="ame_state not in ('none', False)"/>
        <button name="action_ame_approve"
                string="Approve"
                type="object"
                class="btn-success"
                invisible="ame_state != 'pending' or not ame_is_current_approver"/>
        <button name="action_ame_reject"
                string="Reject"
                type="object"
                class="btn-danger"
                invisible="ame_state != 'pending' or not ame_is_current_approver"/>
        <button name="action_ame_delegate"
                string="Delegate"
                type="object"
                class="btn-secondary"
                invisible="ame_state != 'pending' or not ame_is_current_approver"/>
    </xpath>
</form>"""

            try:
                view = self.env['ir.ui.view'].sudo().create({
                    'name': '%s.form.ame.buttons' % model_name,
                    'model': model_name,
                    'inherit_id': primary_view.id,
                    'arch': arch,
                    'priority': 999,
                })
                # Create ir.model.data for the xmlid
                self.env['ir.model.data'].sudo().create({
                    'module': 'ame_engine',
                    'name': 'view_%s_ame_buttons' % model_name.replace('.', '_'),
                    'model': 'ir.ui.view',
                    'res_id': view.id,
                    'noupdate': False,
                })
                _logger.info("AME: Injected approval buttons into %s form view", model_name)
            except Exception as e:
                _logger.warning("AME: Failed to inject view for %s: %s", model_name, e)
