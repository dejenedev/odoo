# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval, datetime as se_datetime, dateutil as se_dateutil, time as se_time

_logger = logging.getLogger(__name__)


class AmeApproverAction(models.Model):
    _name = 'ame.approver.action'
    _description = 'AME Approver Action'
    _order = 'name'

    name = fields.Char(string="Action Name", required=True,
                       help="e.g. 'Manager Chain up to Director'")
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company)

    action_type = fields.Selection([
        ('specific_user', 'Specific User'),
        ('approval_group', 'Approval Group'),
        ('supervisory_hierarchy', 'Supervisory Hierarchy (Manager Chain)'),
        ('job_level_authority', 'Job Level Authority'),
        ('dynamic', 'Dynamic (Python Expression)'),
    ], required=True, default='specific_user')

    # For specific_user
    user_id = fields.Many2one('res.users', string="Specific Approver")

    # For approval_group
    approval_group_id = fields.Many2one(
        'ame.approval.group', string="Approval Group")

    # For supervisory_hierarchy
    hierarchy_levels = fields.Integer(
        default=1,
        help="Number of management levels to traverse. "
             "1 = direct manager, 2 = manager's manager, etc.")

    # For job_level_authority
    min_authority_level = fields.Integer(
        default=0,
        help="Walk up the manager chain until finding someone "
             "whose job authority level meets this minimum.")

    # For dynamic
    python_expression = fields.Text(
        string="Python Expression",
        help="Must return a res.users recordset. "
             "Available: record, env, user, datetime, dateutil")

    # Voting type within this action
    require_all = fields.Boolean(
        default=True,
        help="If True, ALL resolved approvers must approve. "
             "If False, any ONE suffices (first-responder within this action).")

    def resolve_approvers(self, record):
        """Resolve the actual approver user(s) for a given document.

        :param record: the document record
        :returns: res.users recordset
        """
        self.ensure_one()

        if self.action_type == 'specific_user':
            if not self.user_id:
                raise UserError(_(
                    "Approver action '%s' has no specific user configured."
                ) % self.name)
            return self.user_id

        elif self.action_type == 'approval_group':
            if not self.approval_group_id:
                raise UserError(_(
                    "Approver action '%s' has no approval group configured."
                ) % self.name)
            return self.approval_group_id.member_ids

        elif self.action_type == 'supervisory_hierarchy':
            return self._resolve_supervisory(record)

        elif self.action_type == 'job_level_authority':
            return self._resolve_job_level(record)

        elif self.action_type == 'dynamic':
            return self._resolve_dynamic(record)

        return self.env['res.users']

    def _get_requester_employee(self, record):
        """Find the employee record for the document's requester."""
        if 'hr.employee' not in self.env:
            raise UserError(_(
                "HR module is required for hierarchy-based approval. "
                "Please install the 'hr' module."))

        # Try common requester fields
        requester = None
        for fname in ('user_id', 'create_uid', 'requested_by'):
            if fname in record._fields:
                requester = record[fname]
                if requester:
                    break
        if not requester:
            requester = record.create_uid

        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', requester.id),
        ], limit=1)
        if not employee:
            raise UserError(_(
                "No employee record found for user '%s'. "
                "Supervisory hierarchy requires HR employee records."
            ) % requester.name)
        return employee

    def _resolve_supervisory(self, record):
        """Walk up the manager chain for N levels."""
        employee = self._get_requester_employee(record)
        approvers = self.env['res.users']
        current = employee
        for _i in range(self.hierarchy_levels):
            manager = current.parent_id
            if not manager:
                break
            if manager.user_id:
                approvers |= manager.user_id
            current = manager
        if not approvers:
            _logger.warning(
                "AME: No managers found for employee %s after %d levels",
                employee.name, self.hierarchy_levels)
        return approvers

    def _resolve_job_level(self, record):
        """Walk up manager chain until finding sufficient authority level."""
        employee = self._get_requester_employee(record)
        current = employee
        max_iterations = 20
        for _i in range(max_iterations):
            manager = current.parent_id
            if not manager:
                break
            # Check if hr.job has ame_authority_level (optional field)
            authority = 0
            if hasattr(manager.job_id, 'ame_authority_level'):
                authority = manager.job_id.ame_authority_level or 0
            if authority >= self.min_authority_level and manager.user_id:
                return manager.user_id
            current = manager
        _logger.warning(
            "AME: No manager with authority level >= %d found for %s",
            self.min_authority_level, employee.name)
        return self.env['res.users']

    def _resolve_dynamic(self, record):
        """Execute Python expression to resolve approvers."""
        if not self.python_expression:
            raise UserError(_(
                "Approver action '%s' has no Python expression."
            ) % self.name)
        eval_context = {
            'record': record.sudo(),
            'env': self.env,
            'user': self.env.user,
            'datetime': se_datetime,
            'dateutil': se_dateutil,
            'time': se_time,
        }
        result = safe_eval(
            self.python_expression.strip(),
            eval_context,
            filename='ame.approver.action(%s)' % self.id,
        )
        if isinstance(result, models.BaseModel) and result._name == 'res.users':
            return result
        raise UserError(_(
            "Dynamic expression for '%s' must return a res.users recordset."
        ) % self.name)
