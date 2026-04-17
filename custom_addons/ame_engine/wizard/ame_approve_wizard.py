# -*- coding: utf-8 -*-
from odoo import fields, models, _


class AmeApproveWizard(models.TransientModel):
    _name = 'ame.approve.wizard'
    _description = 'AME Approve/Reject Wizard'

    line_id = fields.Many2one(
        'ame.approval.line', string="Approval Line", required=True)
    action_type = fields.Selection([
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ], required=True, default='approve')
    comment = fields.Text(string="Comment")

    def action_confirm(self):
        self.ensure_one()
        if self.action_type == 'approve':
            self.line_id.action_approve(self.comment or '')
            msg = _("Approved successfully.")
            msg_type = 'success'
        else:
            self.line_id.action_reject(self.comment or '')
            msg = _("Rejected.")
            msg_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Done"),
                'message': msg,
                'type': msg_type,
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
