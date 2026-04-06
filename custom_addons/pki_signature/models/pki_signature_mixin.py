# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PkiSignatureMixin(models.AbstractModel):
    _name = 'pki.signature.mixin'
    _description = 'PKI Signature Mixin'

    pki_signature_line_ids = fields.One2many(
        'pki.signature.line', 'res_id',
        string="Approval Signatures",
        domain=lambda self: [('res_model', '=', self._name)])
    pki_approval_status = fields.Selection([
        ('none', 'No Approval Needed'),
        ('pending', 'Awaiting Approval'),
        ('signed', 'Fully Signed'),
        ('rejected', 'Rejected'),
    ], string="Approval Status", compute='_compute_pki_approval_status',
        store=True)
    pki_is_fully_signed = fields.Boolean(
        string="Fully Signed", compute='_compute_pki_approval_status',
        store=True)
    pki_current_step = fields.Char(
        string="Current Step", compute='_compute_pki_current_step')
    pki_is_current_approver = fields.Boolean(
        string="Can Approve", compute='_compute_pki_is_current_approver')

    @api.depends('pki_signature_line_ids.status')
    def _compute_pki_approval_status(self):
        for rec in self:
            lines = rec.pki_signature_line_ids
            if not lines:
                rec.pki_approval_status = 'none'
                rec.pki_is_fully_signed = False
            elif any(l.status == 'rejected' for l in lines):
                rec.pki_approval_status = 'rejected'
                rec.pki_is_fully_signed = False
            elif all(l.status == 'signed' for l in lines):
                rec.pki_approval_status = 'signed'
                rec.pki_is_fully_signed = True
            else:
                rec.pki_approval_status = 'pending'
                rec.pki_is_fully_signed = False

    def _compute_pki_current_step(self):
        for rec in self:
            pending = rec.pki_signature_line_ids.filtered(
                lambda l: l.status == 'pending'
            ).sorted('sequence')
            if pending:
                rec.pki_current_step = pending[0].rule_name
            else:
                rec.pki_current_step = False

    def _compute_pki_is_current_approver(self):
        user = self.env.user
        for rec in self:
            pending = rec.pki_signature_line_ids.filtered(
                lambda l: l.status == 'pending'
            ).sorted('sequence')
            if pending:
                required_group = pending[0].group_id
                rec.pki_is_current_approver = required_group in user.groups_id
            else:
                rec.pki_is_current_approver = False

    def action_request_pki_approval(self):
        """Create signature lines based on applicable approval rules."""
        self.ensure_one()
        rules = self.env['pki.approval.rule'].get_rules_for_model(
            self._name,
            company_id=self.company_id.id if 'company_id' in self._fields else self.env.company.id,
            amount=self._pki_get_amount(),
        )
        if not rules:
            raise UserError(_(
                "No approval rules configured for %s."
            ) % self._description)

        # Remove existing pending lines
        existing = self.env['pki.signature.line'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('status', '=', 'pending'),
        ])
        existing.unlink()

        # Create new lines
        for rule in rules:
            self.env['pki.signature.line'].create({
                'rule_id': rule.id,
                'res_model': self._name,
                'res_id': self.id,
                'company_id': rule.company_id.id,
            })

        return True

    def action_open_sign_wizard(self):
        """Open the signing wizard for the current approval step."""
        self.ensure_one()
        pending = self.pki_signature_line_ids.filtered(
            lambda l: l.status == 'pending'
        ).sorted('sequence')
        if not pending:
            raise UserError(_("No pending approval steps."))

        line = pending[0]
        if line.group_id not in self.env.user.groups_id:
            raise UserError(_(
                "You do not have the required role '%s' for this step."
            ) % line.group_id.full_name)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign Document'),
            'res_model': 'pki.sign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
                'default_signature_line_id': line.id,
                'default_role_name': line.rule_name,
            },
        }

    def action_open_verify_wizard(self):
        """Open the signature verification wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Verify Signatures'),
            'res_model': 'pki.verify.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    def _pki_get_amount(self):
        """Return the document amount for threshold filtering.
        Override in inheriting models.
        """
        for fname in ('amount_total', 'amount_residual', 'amount_untaxed'):
            if fname in self._fields:
                return self[fname] or 0.0
        return 0.0
