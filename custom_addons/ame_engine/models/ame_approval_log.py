# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class AmeApprovalLog(models.Model):
    _name = 'ame.approval.log'
    _description = 'AME Approval Audit Log'
    _order = 'create_date desc'
    _rec_name = 'action'

    instance_id = fields.Many2one(
        'ame.approval.instance', required=True,
        ondelete='cascade', index=True)
    line_id = fields.Many2one(
        'ame.approval.line', ondelete='set null')

    res_model = fields.Char(
        related='instance_id.res_model', store=True, index=True)
    res_id = fields.Many2oneReference(
        related='instance_id.res_id', store=True, model_field='res_model')

    action = fields.Selection([
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('delegated', 'Delegated'),
        ('escalated', 'Escalated'),
        ('cancelled', 'Cancelled'),
    ], required=True, index=True)

    user_id = fields.Many2one(
        'res.users', string="Performed By",
        default=lambda self: self.env.user, required=True)
    delegate_to_id = fields.Many2one(
        'res.users', string="Delegated To")
    comment = fields.Text()

    company_id = fields.Many2one(
        related='instance_id.company_id', store=True)

    def write(self, vals):
        raise UserError(_("Approval log entries cannot be modified."))

    def unlink(self):
        raise UserError(_("Approval log entries cannot be deleted."))
