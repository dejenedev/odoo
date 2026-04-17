# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AmeApprovalMixin(models.AbstractModel):
    _name = 'ame.approval.mixin'
    _description = 'AME Approval Mixin'

    ame_instance_id = fields.Many2one(
        'ame.approval.instance', string="Approval Instance",
        copy=False, readonly=True)
    ame_state = fields.Selection([
        ('none', 'No Approval'),
        ('pending', 'Awaiting Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string="AME Status", compute='_compute_ame_state', store=True)
    ame_is_fully_approved = fields.Boolean(
        string="AME Approved", compute='_compute_ame_state', store=True)
    ame_current_approver_names = fields.Char(
        string="Current Approvers",
        compute='_compute_ame_current_approver')
    ame_is_current_approver = fields.Boolean(
        string="Can Approve",
        compute='_compute_ame_current_approver')

    @api.depends('ame_instance_id.state')
    def _compute_ame_state(self):
        for rec in self:
            inst = rec.ame_instance_id
            if not inst:
                rec.ame_state = 'none'
                rec.ame_is_fully_approved = False
            elif inst.state == 'approved':
                rec.ame_state = 'approved'
                rec.ame_is_fully_approved = True
            elif inst.state == 'rejected':
                rec.ame_state = 'rejected'
                rec.ame_is_fully_approved = False
            elif inst.state in ('draft', 'in_progress'):
                rec.ame_state = 'pending'
                rec.ame_is_fully_approved = False
            else:
                rec.ame_state = 'none'
                rec.ame_is_fully_approved = False

    def _compute_ame_current_approver(self):
        user = self.env.user
        for rec in self:
            inst = rec.ame_instance_id
            if not inst or inst.state != 'in_progress':
                rec.ame_current_approver_names = False
                rec.ame_is_current_approver = False
                continue
            waiting = inst.line_ids.filtered(
                lambda l: l.state == 'waiting')
            rec.ame_current_approver_names = ', '.join(
                waiting.mapped('approver_id.name'))
            rec.ame_is_current_approver = user in waiting.mapped(
                'approver_id')

    def action_submit_for_ame_approval(self):
        """Create an AME approval instance and submit for approval."""
        self.ensure_one()
        if self.ame_instance_id and self.ame_instance_id.state == 'in_progress':
            raise UserError(_("This document already has a pending approval."))

        # Find transaction type
        tt = self.env['ame.transaction.type'].get_for_model(self._name)
        if not tt:
            raise UserError(_(
                "No AME transaction type configured for '%s'. "
                "Please configure it in AME settings."
            ) % self._description)

        # Cancel old instance if exists
        if self.ame_instance_id and self.ame_instance_id.state in (
                'draft', 'rejected', 'cancelled'):
            self.ame_instance_id.unlink()

        # Create instance
        instance = self.env['ame.approval.instance'].create({
            'res_model': self._name,
            'res_id': self.id,
            'transaction_type_id': tt.id,
            'requester_id': self.env.user.id,
        })
        self.ame_instance_id = instance
        instance.action_submit()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Submitted for Approval"),
                'message': _("Document submitted for approval."),
                'type': 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_ame_approve(self):
        """Open the approve wizard for the current user's pending line."""
        self.ensure_one()
        inst = self.ame_instance_id
        if not inst or inst.state != 'in_progress':
            raise UserError(_("No pending approval."))

        waiting = inst.line_ids.filtered(
            lambda l: l.state == 'waiting'
            and l.approver_id == self.env.user)
        if not waiting:
            raise UserError(_("You have no pending approval on this document."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Approve'),
            'res_model': 'ame.approve.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': waiting[0].id,
                'default_action_type': 'approve',
            },
        }

    def action_ame_reject(self):
        """Open the reject wizard."""
        self.ensure_one()
        inst = self.ame_instance_id
        if not inst or inst.state != 'in_progress':
            raise UserError(_("No pending approval."))

        waiting = inst.line_ids.filtered(
            lambda l: l.state == 'waiting'
            and l.approver_id == self.env.user)
        if not waiting:
            raise UserError(_("You have no pending approval on this document."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject'),
            'res_model': 'ame.approve.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': waiting[0].id,
                'default_action_type': 'reject',
            },
        }

    def action_ame_delegate(self):
        """Open the delegation wizard."""
        self.ensure_one()
        inst = self.ame_instance_id
        if not inst or inst.state != 'in_progress':
            raise UserError(_("No pending approval."))

        waiting = inst.line_ids.filtered(
            lambda l: l.state == 'waiting'
            and l.approver_id == self.env.user)
        if not waiting:
            raise UserError(_("You have no pending approval on this document."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Delegate Approval'),
            'res_model': 'ame.delegate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': waiting[0].id,
            },
        }

    def action_view_ame_instance(self):
        """Open the approval instance form."""
        self.ensure_one()
        if not self.ame_instance_id:
            raise UserError(_("No approval instance."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Details'),
            'res_model': 'ame.approval.instance',
            'res_id': self.ame_instance_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _on_ame_approved(self):
        """Callback when approval is complete. Override in inheriting model."""
        pass

    def _on_ame_rejected(self):
        """Callback when approval is rejected. Override in inheriting model."""
        pass
