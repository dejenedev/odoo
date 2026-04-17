# -*- coding: utf-8 -*-
from odoo import fields, models


class AmeApprovalGroup(models.Model):
    _name = 'ame.approval.group'
    _description = 'AME Approval Group'
    _order = 'name'

    name = fields.Char(string="Group Name", required=True,
                       help="e.g. 'Finance Review Board'")
    description = fields.Text()
    member_ids = fields.Many2many(
        'res.users', 'ame_approval_group_user_rel',
        'group_id', 'user_id', string="Members")
    min_approvals = fields.Integer(
        default=1,
        help="Minimum number of members that must approve. "
             "0 = ALL members must approve. "
             "1 = any ONE member suffices.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)
