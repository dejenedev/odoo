# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PkiVerifyWizard(models.TransientModel):
    _name = 'pki.verify.wizard'
    _description = 'PKI Signature Verification'

    res_model = fields.Char(string="Document Model", required=True)
    res_id = fields.Integer(string="Document ID", required=True)
    line_ids = fields.One2many(
        'pki.verify.wizard.line', 'wizard_id', string="Verification Results")
    overall_status = fields.Selection([
        ('valid', 'All Valid'),
        ('invalid', 'Tampering Detected'),
        ('partial', 'Partially Signed'),
        ('none', 'No Signatures'),
    ], string="Overall Status", compute='_compute_overall_status')

    @api.depends('line_ids.hash_valid', 'line_ids.signature_valid')
    def _compute_overall_status(self):
        for rec in self:
            if not rec.line_ids:
                rec.overall_status = 'none'
            elif all(l.hash_valid and l.signature_valid for l in rec.line_ids if l.status == 'signed'):
                signed = rec.line_ids.filtered(lambda l: l.status == 'signed')
                if len(signed) == len(rec.line_ids):
                    rec.overall_status = 'valid'
                else:
                    rec.overall_status = 'partial'
            else:
                rec.overall_status = 'invalid'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get('res_model') and res.get('res_id'):
            lines = self.env['pki.signature.line'].search([
                ('res_model', '=', res['res_model']),
                ('res_id', '=', res['res_id']),
            ], order='sequence')
            line_vals = []
            for line in lines:
                hash_valid = False
                sig_valid = False
                cert_valid = False
                if line.status == 'signed':
                    try:
                        record = self.env[line.res_model].browse(line.res_id)
                        current_hash = self.env['pki.signature.line']._compute_document_hash(
                            record, line.rule_id)
                        hash_valid = (current_hash == line.document_hash)
                    except Exception:
                        pass
                    sig_valid = line._verify_signature()
                    cert_valid = line.certificate_id.is_valid() if line.certificate_id else False

                line_vals.append((0, 0, {
                    'signature_line_id': line.id,
                    'step_name': line.rule_name,
                    'sequence': line.sequence,
                    'status': line.status,
                    'signer_name': line.signed_by_name or '',
                    'signature_date': line.signature_date,
                    'hash_valid': hash_valid,
                    'signature_valid': sig_valid,
                    'certificate_valid': cert_valid,
                    'certificate_fingerprint': line.certificate_id.fingerprint if line.certificate_id else '',
                }))
            res['line_ids'] = line_vals
        return res


class PkiVerifyWizardLine(models.TransientModel):
    _name = 'pki.verify.wizard.line'
    _description = 'PKI Verification Result Line'
    _order = 'sequence'

    wizard_id = fields.Many2one(
        'pki.verify.wizard', string="Wizard",
        required=True, ondelete='cascade')
    signature_line_id = fields.Many2one(
        'pki.signature.line', string="Signature Line")
    step_name = fields.Char(string="Step")
    sequence = fields.Integer(string="Order")
    status = fields.Selection([
        ('pending', 'Pending'),
        ('signed', 'Signed'),
        ('rejected', 'Rejected'),
    ], string="Status")
    signer_name = fields.Char(string="Signed By")
    signature_date = fields.Datetime(string="Date")
    hash_valid = fields.Boolean(string="Data Intact")
    signature_valid = fields.Boolean(string="Signature Valid")
    certificate_valid = fields.Boolean(string="Certificate Valid")
    certificate_fingerprint = fields.Char(string="Cert Fingerprint")
