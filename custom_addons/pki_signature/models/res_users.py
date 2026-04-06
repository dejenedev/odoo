# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    pki_certificate_ids = fields.One2many(
        'pki.user.certificate', 'user_id',
        string="PKI Certificates")
    pki_active_certificate_id = fields.Many2one(
        'pki.user.certificate', string="Active Certificate",
        compute='_compute_pki_active_certificate')

    def _compute_pki_active_certificate(self):
        for user in self:
            cert = self.env['pki.user.certificate'].search([
                ('user_id', '=', user.id),
                ('state', '=', 'active'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            user.pki_active_certificate_id = cert

    def _pki_re_encrypt_on_password_change(self, old_password, new_password):
        """Re-encrypt all active certificates when user changes password."""
        for user in self:
            certs = self.env['pki.user.certificate'].sudo().search([
                ('user_id', '=', user.id),
                ('state', '=', 'active'),
            ])
            for cert in certs:
                try:
                    cert.re_encrypt_private_key(old_password, new_password)
                except Exception as e:
                    _logger.warning(
                        "Failed to re-encrypt certificate %s for user %s: %s",
                        cert.id, user.login, e
                    )
