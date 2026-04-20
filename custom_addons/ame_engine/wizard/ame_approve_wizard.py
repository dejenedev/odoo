# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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

    # PKI Digital Signature fields
    pki_available = fields.Boolean(
        compute='_compute_pki_available')
    password = fields.Char(
        string="Password",
        help="Enter your Odoo password to digitally sign this approval.")
    visual_signature = fields.Binary(
        string="Signature", help="Draw your signature")

    @api.depends('action_type', 'line_id')
    def _compute_pki_available(self):
        has_pki = 'pki.signing.config' in self.env
        for rec in self:
            if not has_pki or rec.action_type != 'approve' or not rec.line_id:
                rec.pki_available = False
                continue
            # Check if model is configured for digital signing
            config = self.env['pki.signing.config'].get_config_for_model(
                rec.line_id.res_model)
            if not config:
                rec.pki_available = False
                continue
            # Check if user has an active certificate
            cert = self.env['pki.user.certificate'].search([
                ('user_id', '=', self.env.user.id),
                ('state', '=', 'active'),
            ], limit=1)
            rec.pki_available = bool(cert)

    def action_confirm(self):
        self.ensure_one()
        if self.action_type == 'approve':
            # PKI digital signature
            if self.pki_available:
                if not self.password:
                    raise UserError(_(
                        "Please enter your password to digitally sign this approval."))
                self._sign_with_pki()

            self.line_id.action_approve(self.comment or '')
            msg = _("Approved and digitally signed.") if self.pki_available else _("Approved.")
            msg_type = 'success'
        else:
            if not self.comment:
                raise UserError(_("Please provide a reason for rejection."))
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

    def _sign_with_pki(self):
        """Cryptographically sign the approval using PKI certificate."""
        self.ensure_one()
        cert = self.env['pki.user.certificate'].search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'active'),
        ], limit=1)
        if not cert:
            raise UserError(_("No active PKI certificate found."))

        # Validate password and decrypt private key
        private_key = cert.load_private_key(self.password)

        try:
            from cryptography.hazmat.primitives.asymmetric import padding, utils
            from cryptography.hazmat.primitives import hashes

            # Compute document hash using configured fields
            config = self.env['pki.signing.config'].get_config_for_model(
                self.line_id.res_model)
            record = self.env[self.line_id.res_model].browse(self.line_id.res_id)
            data = {
                'model': self.line_id.res_model,
                'id': self.line_id.res_id,
                'approver': self.env.user.id,
            }
            if config and config.field_ids and record.exists():
                for field in config.field_ids.sorted('name'):
                    value = record[field.name]
                    if hasattr(value, 'id'):
                        value = value.id
                    elif hasattr(value, 'ids'):
                        value = sorted(value.ids)
                    data[field.name] = value
            data_bytes = json.dumps(data, sort_keys=True, default=str).encode()
            doc_hash_bytes = hashlib.sha256(data_bytes).digest()
            doc_hash = hashlib.sha256(data_bytes).hexdigest()

            # Sign the raw hash bytes with RSA-PKCS1v15
            signature = private_key.sign(
                doc_hash_bytes,
                padding.PKCS1v15(),
                utils.Prehashed(hashes.SHA256()),
            )

            self.line_id.write({
                'pki_certificate_id': cert.id,
                'pki_document_hash': doc_hash,
                'pki_digital_signature': base64.b64encode(signature),
                'pki_visual_signature': self.visual_signature,
                'pki_signed_by_name': self.env.user.name,
            })
            _logger.info("PKI signature stored on approval line %s", self.line_id.id)

        except Exception as e:
            _logger.error("PKI signing failed: %s", e)
            raise UserError(_("Digital signing failed: %s") % str(e))
