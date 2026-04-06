# -*- coding: utf-8 -*-
import base64
import hashlib
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, utils

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PkiSignatureLine(models.Model):
    _name = 'pki.signature.line'
    _description = 'PKI Signature Line'
    _order = 'sequence, id'

    rule_id = fields.Many2one(
        'pki.approval.rule', string="Approval Rule",
        required=True, ondelete='cascade')
    rule_name = fields.Char(related='rule_id.name', string="Step")
    res_model = fields.Char(string="Document Model", required=True, index=True)
    res_id = fields.Integer(string="Document ID", required=True, index=True)
    sequence = fields.Integer(
        related='rule_id.sequence', string="Step Order", store=True)
    group_id = fields.Many2one(
        related='rule_id.group_id', string="Required Role", store=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('signed', 'Signed'),
        ('rejected', 'Rejected'),
    ], string="Status", default='pending', required=True)
    signer_id = fields.Many2one(
        'res.users', string="Signed By", readonly=True)
    certificate_id = fields.Many2one(
        'pki.user.certificate', string="Certificate Used", readonly=True)
    signature_date = fields.Datetime(string="Signed On", readonly=True)
    document_hash = fields.Char(
        string="Document Hash", readonly=True,
        help="SHA-256 hash of the document data at signing time.")
    digital_signature = fields.Binary(
        string="Digital Signature", readonly=True, attachment=True,
        help="RSA-PKCS1v15 signature of the document hash.")
    visual_signature = fields.Binary(
        string="Visual Signature", attachment=True,
        help="Hand-drawn signature image for display on reports.")
    signed_by_name = fields.Char(string="Signer Name", readonly=True)
    rejection_reason = fields.Text(string="Rejection Reason")
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)
    is_hash_valid = fields.Boolean(
        string="Hash Valid", compute='_compute_is_hash_valid',
        help="True if document has not been tampered with since signing.")
    is_signature_valid = fields.Boolean(
        string="Signature Valid", compute='_compute_is_signature_valid',
        help="True if cryptographic signature verification passes.")

    def _compute_is_hash_valid(self):
        for line in self:
            if line.status != 'signed' or not line.document_hash:
                line.is_hash_valid = False
                continue
            try:
                record = self.env[line.res_model].browse(line.res_id)
                if not record.exists():
                    line.is_hash_valid = False
                    continue
                current_hash = self._compute_document_hash(record, line.rule_id)
                line.is_hash_valid = (current_hash == line.document_hash)
            except Exception:
                line.is_hash_valid = False

    def _compute_is_signature_valid(self):
        for line in self:
            if line.status != 'signed' or not line.digital_signature:
                line.is_signature_valid = False
                continue
            try:
                line.is_signature_valid = line._verify_signature()
            except Exception:
                line.is_signature_valid = False

    @staticmethod
    def _compute_document_hash(record, rule):
        """Compute SHA-256 hash of configured document fields.

        :param record: the document record
        :param rule: pki.approval.rule with field_ids
        :returns: hex digest string
        """
        data = {}
        if rule.field_ids:
            for field in rule.field_ids.sorted('name'):
                value = record[field.name]
                if hasattr(value, 'id'):
                    value = value.id
                elif hasattr(value, 'ids'):
                    value = sorted(value.ids)
                data[field.name] = value
        else:
            # Fallback: hash key business fields if no fields configured
            for fname in ('name', 'amount_total', 'amount_untaxed',
                          'partner_id', 'date', 'invoice_date',
                          'date_order', 'state'):
                if fname in record._fields:
                    value = record[fname]
                    if hasattr(value, 'id'):
                        value = value.id
                    data[fname] = value

        data_bytes = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(data_bytes).hexdigest()

    def sign(self, private_key, certificate, password, visual_signature=None):
        """Cryptographically sign this approval line.

        :param private_key: RSA private key object
        :param certificate: pki.user.certificate record
        :param password: not used here (key already decrypted)
        :param visual_signature: optional base64 encoded signature image
        """
        self.ensure_one()
        if self.status != 'pending':
            raise UserError(_("This step has already been processed."))

        # Check user has required role
        user = self.env.user
        if not user.has_group(self.group_id.get_external_id()[self.group_id.id]
                              if self.group_id.get_external_id().get(self.group_id.id)
                              else ''):
            # Fallback: check group membership directly
            if self.group_id not in user.groups_id:
                raise UserError(_(
                    "You do not have the required role '%s' to sign this step."
                ) % self.group_id.full_name)

        # Check previous steps are signed
        prev_lines = self.search([
            ('res_model', '=', self.res_model),
            ('res_id', '=', self.res_id),
            ('sequence', '<', self.sequence),
            ('status', '!=', 'signed'),
        ])
        if prev_lines:
            raise UserError(_(
                "Previous approval step(s) must be signed first."
            ))

        # Compute document hash
        record = self.env[self.res_model].browse(self.res_id)
        doc_hash = self._compute_document_hash(record, self.rule_id)
        doc_hash_bytes = doc_hash.encode()

        # Sign the hash with RSA-PKCS1v15
        signature = private_key.sign(
            doc_hash_bytes,
            padding.PKCS1v15(),
            utils.Prehashed(hashes.SHA256()),
        )

        vals = {
            'status': 'signed',
            'signer_id': user.id,
            'certificate_id': certificate.id,
            'signature_date': fields.Datetime.now(),
            'document_hash': doc_hash,
            'digital_signature': base64.b64encode(signature),
            'signed_by_name': user.name,
        }
        if visual_signature:
            vals['visual_signature'] = visual_signature

        self.write(vals)

    def reject(self, reason):
        """Reject this approval step."""
        self.ensure_one()
        if self.status != 'pending':
            raise UserError(_("This step has already been processed."))
        self.write({
            'status': 'rejected',
            'signer_id': self.env.user.id,
            'signature_date': fields.Datetime.now(),
            'signed_by_name': self.env.user.name,
            'rejection_reason': reason,
        })

    def _verify_signature(self):
        """Verify the cryptographic signature.

        :returns: True if signature is valid
        """
        self.ensure_one()
        if not self.digital_signature or not self.certificate_id:
            return False

        cert = self.certificate_id.load_certificate()
        public_key = cert.public_key()
        sig_bytes = base64.b64decode(self.digital_signature)
        doc_hash_bytes = self.document_hash.encode()

        try:
            public_key.verify(
                sig_bytes,
                doc_hash_bytes,
                padding.PKCS1v15(),
                utils.Prehashed(hashes.SHA256()),
            )
            return True
        except Exception:
            return False
