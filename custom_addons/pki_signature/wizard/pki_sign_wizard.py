# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PkiSignWizard(models.TransientModel):
    _name = 'pki.sign.wizard'
    _description = 'PKI Signing Wizard'

    res_model = fields.Char(string="Document Model", required=True)
    res_id = fields.Integer(string="Document ID", required=True)
    signature_line_id = fields.Many2one(
        'pki.signature.line', string="Approval Step", required=True)
    role_name = fields.Char(string="Signing As", readonly=True)
    password = fields.Char(string="Your Password", required=True,
                           help="Enter your Odoo login password to unlock your signing key.")
    visual_signature = fields.Binary(string="Signature")
    document_hash_preview = fields.Char(
        string="Document Hash", compute='_compute_document_hash_preview',
        help="SHA-256 hash of the document data that will be signed.")

    @api.depends('res_model', 'res_id', 'signature_line_id')
    def _compute_document_hash_preview(self):
        for rec in self:
            if rec.res_model and rec.res_id and rec.signature_line_id:
                try:
                    record = self.env[rec.res_model].browse(rec.res_id)
                    if record.exists():
                        doc_hash = self.env['pki.signature.line']._compute_document_hash(
                            record, rec.signature_line_id.rule_id)
                        rec.document_hash_preview = doc_hash[:16] + '...'
                    else:
                        rec.document_hash_preview = False
                except Exception:
                    rec.document_hash_preview = False
            else:
                rec.document_hash_preview = False

    def action_sign(self):
        """Sign the document with the user's PKI certificate."""
        self.ensure_one()
        if not self.password:
            raise UserError(_("Please enter your password."))

        # Get user's active certificate
        cert = self.env.user.pki_active_certificate_id
        if not cert:
            raise UserError(_(
                "You do not have an active PKI certificate. "
                "Please contact your administrator."
            ))
        if not cert.is_valid():
            raise UserError(_(
                "Your PKI certificate is not valid (state: %s)."
            ) % cert.state)

        # Decrypt private key with password
        private_key = cert.load_private_key(self.password)

        # Sign the approval line
        self.signature_line_id.sign(
            private_key=private_key,
            certificate=cert,
            password=self.password,
            visual_signature=self.visual_signature,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Signed"),
                'message': _("Document signed successfully by %s.") % self.env.user.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }


class PkiRejectWizard(models.TransientModel):
    _name = 'pki.reject.wizard'
    _description = 'PKI Rejection Wizard'

    signature_line_id = fields.Many2one(
        'pki.signature.line', string="Approval Step", required=True)
    rejection_reason = fields.Text(string="Reason", required=True)

    def action_reject(self):
        """Reject the approval step."""
        self.ensure_one()
        self.signature_line_id.reject(self.rejection_reason)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Rejected"),
                'message': _("Approval step rejected."),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
