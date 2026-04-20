# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AmeApprovalLine(models.Model):
    _name = 'ame.approval.line'
    _description = 'AME Approval Line'
    _order = 'priority, sequence, id'

    instance_id = fields.Many2one(
        'ame.approval.instance', string="Approval Instance",
        required=True, ondelete='cascade')
    rule_id = fields.Many2one(
        'ame.rule', string="Source Rule", ondelete='set null')
    approver_action_id = fields.Many2one(
        'ame.approver.action', string="Source Action", ondelete='set null')

    approver_id = fields.Many2one(
        'res.users', string="Approver", required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('waiting', 'Awaiting'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('delegated', 'Delegated'),
        ('skipped', 'Skipped'),
    ], default='pending', required=True, index=True)

    priority = fields.Integer(default=10, help="Approval level")
    sequence = fields.Integer(default=10)

    # Timestamps
    activated_date = fields.Datetime(string="Activated On")
    decided_date = fields.Datetime(string="Decided On")

    # SLA
    sla_hours = fields.Float(default=0, help="0 = no SLA")
    sla_deadline = fields.Datetime(
        compute='_compute_sla_deadline', store=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue')

    # Decision
    comment = fields.Text(string="Comment")
    delegated_to_id = fields.Many2one('res.users', string="Delegated To")

    # PKI Digital Signature (populated when PKI module is installed)
    pki_certificate_id = fields.Many2one(
        'pki.user.certificate', string="PKI Certificate", readonly=True)
    pki_document_hash = fields.Char(
        string="Document Hash", readonly=True)
    pki_digital_signature = fields.Binary(
        string="Digital Signature", readonly=True)
    pki_visual_signature = fields.Binary(
        string="Visual Signature")
    pki_signed_by_name = fields.Char(
        string="Signed By", readonly=True)
    pki_is_digitally_signed = fields.Boolean(
        compute='_compute_pki_is_digitally_signed')

    # Convenience
    res_model = fields.Char(related='instance_id.res_model', store=True)
    res_id = fields.Many2oneReference(
        related='instance_id.res_id', store=True, model_field='res_model')
    company_id = fields.Many2one(
        related='instance_id.company_id', store=True)

    def _compute_pki_is_digitally_signed(self):
        for line in self:
            line.pki_is_digitally_signed = bool(line.pki_digital_signature)

    @api.depends('activated_date', 'sla_hours')
    def _compute_sla_deadline(self):
        for line in self:
            if line.activated_date and line.sla_hours > 0:
                import datetime as dt
                line.sla_deadline = line.activated_date + dt.timedelta(
                    hours=line.sla_hours)
            else:
                line.sla_deadline = False

    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for line in self:
            line.is_overdue = (
                line.state == 'waiting'
                and line.sla_deadline
                and now > line.sla_deadline
            )

    def _check_can_decide(self):
        """Verify the current user can act on this line."""
        self.ensure_one()
        if self.state != 'waiting':
            raise UserError(_(
                "This approval is not in 'Awaiting' state."))
        # Check substitution
        actual_approver = self._get_effective_approver()
        if (self.env.user != actual_approver
                and not self.env.user._is_admin()):
            raise UserError(_(
                "You are not authorized to act on this approval. "
                "Assigned to: %s") % actual_approver.name)

    def _get_effective_approver(self):
        """Get effective approver considering substitutions."""
        sub = self.env['ame.substitution'].get_active_substitute(
            self.approver_id)
        return sub.substitute_id if sub else self.approver_id

    def action_approve(self, comment=''):
        """Approve this line."""
        self.ensure_one()
        self._check_can_decide()
        self.write({
            'state': 'approved',
            'decided_date': fields.Datetime.now(),
            'comment': comment,
        })
        self._log_decision('approved', comment)
        self._feedback_activity()
        self.instance_id._on_line_decided(self, 'approved')

    def action_reject(self, comment=''):
        """Reject this line."""
        self.ensure_one()
        self._check_can_decide()
        self.write({
            'state': 'rejected',
            'decided_date': fields.Datetime.now(),
            'comment': comment,
        })
        self._log_decision('rejected', comment)
        self._feedback_activity()
        self.instance_id._on_line_decided(self, 'rejected')

    def action_delegate(self, delegate_user, comment=''):
        """Delegate to another user."""
        self.ensure_one()
        self._check_can_decide()
        self.write({
            'state': 'delegated',
            'decided_date': fields.Datetime.now(),
            'delegated_to_id': delegate_user.id,
            'comment': comment,
        })
        # Create new line for the delegate
        new_line = self.copy({
            'approver_id': delegate_user.id,
            'state': 'waiting',
            'activated_date': fields.Datetime.now(),
            'decided_date': False,
            'comment': False,
            'delegated_to_id': False,
        })
        new_line._schedule_activity()
        new_line._send_notification()
        self._log_decision('delegated', comment, delegate_to=delegate_user)
        self._feedback_activity()

    def _log_decision(self, action, comment='', delegate_to=None):
        """Create immutable audit log entry."""
        vals = {
            'instance_id': self.instance_id.id,
            'line_id': self.id,
            'action': action,
            'user_id': self.env.user.id,
            'comment': comment,
        }
        if delegate_to:
            vals['delegate_to_id'] = delegate_to.id
        self.env['ame.approval.log'].sudo().create(vals)

    def _schedule_activity(self):
        """Schedule a mail.activity on the source document."""
        try:
            record = self.env[self.res_model].browse(self.res_id)
            if record.exists() and hasattr(record, 'activity_schedule'):
                act_type = self.env.ref(
                    'ame_engine.mail_activity_type_ame_approval',
                    raise_if_not_found=False)
                if act_type:
                    record.activity_schedule(
                        'ame_engine.mail_activity_type_ame_approval',
                        summary=_("Approval Required: %s") % (
                            self.instance_id.name or ''),
                        note=_("You have been assigned as approver for step: %s") % (
                            self.rule_id.name or ''),
                        user_id=self.approver_id.id,
                    )
        except Exception as e:
            _logger.warning("AME activity scheduling failed: %s", e)

    def _send_notification(self):
        """Post chatter message and notify the approver via inbox/email."""
        try:
            from markupsafe import Markup
            record = self.env[self.res_model].browse(self.res_id)
            if not record.exists() or not hasattr(record, 'message_post'):
                return

            # Add approver as follower so they get inbox notifications
            if hasattr(record, 'message_subscribe'):
                record.message_subscribe(
                    partner_ids=self.approver_id.partner_id.ids)

            doc_name = record.display_name or ''
            body = Markup(
                "<p>Dear <b>%s</b>,</p>"
                "<p>Your approval is required for: <b>%s</b></p>"
                "<p>Step: %s<br/>"
                "Requested by: %s</p>"
            ) % (
                self.approver_id.name,
                doc_name,
                self.rule_id.name or 'N/A',
                self.instance_id.requester_id.name or '',
            )
            record.message_post(
                body=body,
                subject=_("Approval Required: %s") % doc_name,
                partner_ids=self.approver_id.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
                message_type='comment',
            )
        except Exception as e:
            _logger.warning("AME notification failed: %s", e)

    def _feedback_activity(self):
        """Mark the activity as done when approved/rejected."""
        try:
            record = self.env[self.res_model].browse(self.res_id)
            if record.exists() and hasattr(record, 'activity_feedback'):
                record.activity_feedback(
                    ['ame_engine.mail_activity_type_ame_approval'],
                    user_id=self.approver_id.id,
                    feedback=self.comment or self.state,
                )
        except Exception:
            pass

    @api.model
    def _cron_check_escalation(self):
        """Cron job: check for overdue approval lines and escalate."""
        now = fields.Datetime.now()
        overdue_lines = self.search([
            ('state', '=', 'waiting'),
            ('sla_deadline', '!=', False),
            ('sla_deadline', '<', now),
        ])
        for line in overdue_lines:
            tt = line.instance_id.transaction_type_id
            action = tt.escalation_action or 'remind'
            _logger.info(
                "AME escalation: line %s overdue, action=%s", line.id, action)

            if action == 'remind':
                line._send_notification()
            elif action == 'escalate':
                # Try to find manager of current approver
                if 'hr.employee' in self.env:
                    emp = self.env['hr.employee'].sudo().search([
                        ('user_id', '=', line.approver_id.id)], limit=1)
                    if emp and emp.parent_id and emp.parent_id.user_id:
                        line.action_delegate(
                            emp.parent_id.user_id,
                            _("Auto-escalated: SLA exceeded"))
                        continue
                line._send_notification()
            elif action == 'auto_approve':
                line.sudo().write({
                    'state': 'approved',
                    'decided_date': now,
                    'comment': _("Auto-approved: SLA exceeded"),
                })
                line._log_decision('escalated',
                                   _("Auto-approved due to SLA breach"))
                line.instance_id._on_line_decided(line, 'approved')
            elif action == 'notify_admin':
                admin = self.env.ref('base.user_admin', raise_if_not_found=False)
                if admin:
                    line.instance_id.message_post(
                        body=_("ESCALATION: Approval by %s is overdue (SLA: %s hours).") % (
                            line.approver_id.name, line.sla_hours),
                        partner_ids=admin.partner_id.ids,
                        subtype_xmlid='mail.mt_note',
                    )
