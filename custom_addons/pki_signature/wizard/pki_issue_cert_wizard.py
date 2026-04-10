# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class PkiIssueCertWizard(models.TransientModel):
    _name = 'pki.issue.cert.wizard'
    _description = 'Issue User Certificate'

    certificate_id = fields.Many2one(
        'pki.user.certificate', string="Certificate", required=True)
    user_password = fields.Char(
        string="User's Password", required=True,
        help="The Odoo login password of the user receiving the certificate. "
             "This is used to encrypt their private signing key.")

    def _verify_password(self, user, password):
        """Verify a user's password against the stored hash."""
        self.env.cr.execute(
            "SELECT COALESCE(password, '') FROM res_users WHERE id=%s",
            [user.id]
        )
        [hashed] = self.env.cr.fetchone()
        if not hashed:
            return False
        valid, _replacement = self.env['res.users']._crypt_context()\
            .verify_and_update(password, hashed)
        return valid

    def action_issue(self):
        self.ensure_one()
        if not self.user_password:
            raise UserError(_("Password is required."))

        user = self.certificate_id.user_id
        if not self._verify_password(user, self.user_password):
            raise UserError(_(
                "Invalid password for user '%s'. "
                "Please enter the correct Odoo login password."
            ) % user.name)

        self.certificate_id.action_issue_certificate(self.user_password)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Certificate Issued"),
                'message': _("Certificate issued for %s.") % user.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
