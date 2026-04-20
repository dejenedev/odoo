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
        for models with AME Transaction Types — only if not already present."""
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

            # Skip if ANY view already has AME buttons for this model
            self.env.cr.execute("""
                SELECT COUNT(*) FROM ir_ui_view
                WHERE model = %s AND arch_db::text LIKE %s
            """, (model_name, '%action_submit_for_ame_approval%'))
            count = self.env.cr.fetchone()[0]
            if count > 0:
                _logger.info(
                    "AME: Skipping %s - %d view(s) already have approval buttons",
                    model_name, count)
                continue

            # Find the primary form view
            primary_view = self.env['ir.ui.view'].sudo().search([
                ('model', '=', model_name),
                ('type', '=', 'form'),
                ('inherit_id', '=', False),
            ], order='priority', limit=1)
            if not primary_view:
                continue

            # Check if the form has a <header> element
            if '//header' not in (primary_view.arch or '') and '<header' not in (primary_view.arch or ''):
                _logger.info("AME: Skipping %s - form view has no <header>", model_name)
                continue

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
                _logger.info(
                    "AME: Injected approval buttons into %s form view (view id=%s)",
                    model_name, view.id)
            except Exception as e:
                _logger.warning("AME: Failed to inject view for %s: %s", model_name, e)
