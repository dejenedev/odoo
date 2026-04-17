# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AmeApprovalInstance(models.Model):
    _name = 'ame.approval.instance'
    _description = 'AME Approval Instance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(compute='_compute_name', store=True)

    # Polymorphic reference to source document
    res_model = fields.Char(string="Document Model", required=True, index=True)
    res_id = fields.Many2oneReference(
        string="Document ID", model_field='res_model',
        required=True, index=True)
    res_name = fields.Char(
        string="Document", compute='_compute_res_name')

    transaction_type_id = fields.Many2one(
        'ame.transaction.type', string="Transaction Type",
        required=True, ondelete='restrict')
    flow_pattern = fields.Selection(
        related='transaction_type_id.flow_pattern', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True, index=True)

    line_ids = fields.One2many(
        'ame.approval.line', 'instance_id', string="Approval Lines")

    requester_id = fields.Many2one(
        'res.users', string="Requested By",
        default=lambda self: self.env.user, required=True)
    submitted_date = fields.Datetime(string="Submitted On")
    completed_date = fields.Datetime(string="Completed On")

    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)

    # Computed
    current_level = fields.Integer(
        compute='_compute_current_level', store=True)
    progress_pct = fields.Float(
        compute='_compute_progress', string="Progress %")

    @api.depends('transaction_type_id.name', 'res_model', 'res_id')
    def _compute_name(self):
        for rec in self:
            tt_name = rec.transaction_type_id.name or ''
            rec.name = '%s #%s' % (tt_name, rec.res_id or 'New')

    def _compute_res_name(self):
        for rec in self:
            if rec.res_model and rec.res_id:
                try:
                    record = self.env[rec.res_model].browse(rec.res_id)
                    rec.res_name = record.display_name if record.exists() else ''
                except Exception:
                    rec.res_name = ''
            else:
                rec.res_name = ''

    @api.depends('line_ids.state', 'line_ids.priority')
    def _compute_current_level(self):
        for rec in self:
            pending = rec.line_ids.filtered(
                lambda l: l.state in ('pending', 'waiting'))
            rec.current_level = min(pending.mapped('priority')) if pending else 0

    @api.depends('line_ids.state')
    def _compute_progress(self):
        for rec in self:
            total = len(rec.line_ids)
            if not total:
                rec.progress_pct = 0
                continue
            decided = len(rec.line_ids.filtered(
                lambda l: l.state in ('approved', 'skipped')))
            rec.progress_pct = (decided / total) * 100

    def action_submit(self):
        """Submit for approval: evaluate rules, create lines, start the chain."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Can only submit from draft state."))

        # Evaluate rules and build chain
        engine = self.env['ame.engine']
        lines = engine.evaluate_and_build_chain(self)

        if not lines and self.transaction_type_id.auto_approve_on_no_rules:
            self.write({
                'state': 'approved',
                'submitted_date': fields.Datetime.now(),
                'completed_date': fields.Datetime.now(),
            })
            self._notify_document('approved')
            return

        self.write({
            'state': 'in_progress',
            'submitted_date': fields.Datetime.now(),
        })
        self._activate_current_level()

    def action_cancel(self):
        """Cancel the approval."""
        self.ensure_one()
        if self.state not in ('draft', 'in_progress'):
            raise UserError(_("Cannot cancel in state '%s'.") % self.state)
        self.write({
            'state': 'cancelled',
            'completed_date': fields.Datetime.now(),
        })
        self._cancel_remaining_lines()
        self._cancel_activities()

        self.env['ame.approval.log'].sudo().create({
            'instance_id': self.id,
            'action': 'cancelled',
            'user_id': self.env.user.id,
        })
        self._notify_document('cancelled')

    def _activate_current_level(self):
        """Activate pending lines at the current (lowest) priority level."""
        pending = self.line_ids.filtered(lambda l: l.state == 'pending')
        if not pending:
            self._mark_approved()
            return

        if self.flow_pattern == 'parallel':
            # All levels at once
            lines_to_activate = pending
        else:
            # Serial / serial_parallel / first_responder: activate lowest priority
            min_priority = min(pending.mapped('priority'))
            lines_to_activate = pending.filtered(
                lambda l: l.priority == min_priority)

        for line in lines_to_activate:
            line.write({
                'state': 'waiting',
                'activated_date': fields.Datetime.now(),
            })
            line._schedule_activity()
            line._send_notification()

    def _on_line_decided(self, line, decision):
        """Called when an approval line is approved/rejected.

        Handles flow pattern logic to determine next steps.
        """
        if decision == 'rejected':
            self.write({
                'state': 'rejected',
                'completed_date': fields.Datetime.now(),
            })
            self._cancel_remaining_lines()
            self._cancel_activities()
            self._notify_document('rejected')
            return

        # decision == 'approved'
        current_priority = line.priority
        same_level = self.line_ids.filtered(
            lambda l: l.priority == current_priority)

        if self.flow_pattern == 'first_responder':
            # One approval at this level is enough — skip others
            for other in same_level.filtered(
                    lambda l: l.state == 'waiting' and l.id != line.id):
                other.write({'state': 'skipped'})
            self._activate_current_level()

        elif self.flow_pattern in ('serial', 'serial_parallel'):
            # Check if all at this level are decided
            undecided = same_level.filtered(
                lambda l: l.state in ('waiting', 'pending'))
            if not undecided:
                self._activate_current_level()

        elif self.flow_pattern == 'parallel':
            # Check if ALL lines across ALL levels are decided
            undecided = self.line_ids.filtered(
                lambda l: l.state in ('waiting', 'pending'))
            if not undecided:
                self._mark_approved()

    def _mark_approved(self):
        """Mark instance as fully approved."""
        self.write({
            'state': 'approved',
            'completed_date': fields.Datetime.now(),
        })
        self._cancel_activities()
        self._notify_document('approved')

    def _cancel_remaining_lines(self):
        """Skip all remaining pending/waiting lines."""
        remaining = self.line_ids.filtered(
            lambda l: l.state in ('pending', 'waiting'))
        remaining.write({'state': 'skipped'})

    def _cancel_activities(self):
        """Cancel all pending AME activities on the source document."""
        if not self.res_model or not self.res_id:
            return
        try:
            record = self.env[self.res_model].browse(self.res_id)
            if record.exists() and hasattr(record, 'activity_ids'):
                activities = record.activity_ids.filtered(
                    lambda a: a.activity_type_id ==
                    self.env.ref('ame_engine.mail_activity_type_ame_approval',
                                 raise_if_not_found=False))
                activities.unlink()
        except Exception:
            pass

    def _notify_document(self, decision):
        """Post chatter message and call mixin callback on the source document."""
        try:
            record = self.env[self.res_model].browse(self.res_id)
            if not record.exists():
                return

            # Post chatter message
            if hasattr(record, 'message_post'):
                body_map = {
                    'approved': _("Approval completed. All approvers have signed off."),
                    'rejected': _("Approval rejected."),
                    'cancelled': _("Approval cancelled."),
                }
                record.message_post(
                    body=body_map.get(decision, ''),
                    subject=_("AME: %s") % decision.capitalize(),
                    subtype_xmlid='mail.mt_note',
                )

            # Call mixin callbacks
            if decision == 'approved' and hasattr(record, '_on_ame_approved'):
                record._on_ame_approved()
            elif decision == 'rejected' and hasattr(record, '_on_ame_rejected'):
                record._on_ame_rejected()
        except Exception as e:
            _logger.warning("AME notify_document failed: %s", e)
