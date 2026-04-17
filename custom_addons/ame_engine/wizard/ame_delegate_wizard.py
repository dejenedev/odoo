# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class AmeDelegateWizard(models.TransientModel):
    _name = 'ame.delegate.wizard'
    _description = 'AME Delegate Wizard'

    line_id = fields.Many2one(
        'ame.approval.line', string="Approval Line", required=True)
    delegate_to_id = fields.Many2one(
        'res.users', string="Delegate To", required=True)
    comment = fields.Text(string="Reason")

    def action_delegate(self):
        self.ensure_one()
        if not self.delegate_to_id:
            raise UserError(_("Please select a user to delegate to."))
        self.line_id.action_delegate(self.delegate_to_id, self.comment or '')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Delegated"),
                'message': _("Approval delegated to %s.") % self.delegate_to_id.name,
                'type': 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
