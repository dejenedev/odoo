# -*- coding: utf-8 -*-
import base64
import datetime
import hashlib
import logging

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.x509.oid import NameOID

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PkiUserCertificate(models.Model):
    _name = 'pki.user.certificate'
    _description = 'PKI User Certificate'
    _order = 'create_date desc'

    user_id = fields.Many2one(
        'res.users', string="User", required=True, ondelete='cascade')
    ca_id = fields.Many2one(
        'pki.certificate.authority', string="Certificate Authority",
        required=True, domain="[('state', '=', 'active')]")
    private_key_enc = fields.Binary(
        string="Private Key (Encrypted)", attachment=False,
        help="RSA private key encrypted with user's Odoo password.")
    certificate_pem = fields.Binary(
        string="Certificate", attachment=False,
        help="X.509 certificate signed by the CA.")
    certificate_text = fields.Text(
        string="Certificate Details")
    serial_number = fields.Char(string="Serial Number", readonly=True)
    valid_from = fields.Datetime(string="Valid From", readonly=True)
    valid_to = fields.Datetime(string="Valid To", readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    ], string="Status", default='draft', required=True)
    revocation_reason = fields.Text(string="Revocation Reason")
    fingerprint = fields.Char(
        string="Fingerprint (SHA-256)", readonly=True,
        help="SHA-256 fingerprint of the certificate for quick lookup.")
    company_id = fields.Many2one(
        'res.company', string="Company",
        help="Optional. Leave empty for a certificate valid across all companies.")
    key_salt = fields.Char(
        string="Key Salt", readonly=True,
        help="Salt used for password-based key derivation.")

    _sql_constraints = [
        ('serial_uniq', 'unique(serial_number)',
         'Certificate serial number must be unique.'),
    ]


    @staticmethod
    def _derive_key_from_password(password, salt):
        """Derive encryption key from user's Odoo password."""
        if isinstance(password, str):
            password = password.encode()
        if isinstance(salt, str):
            salt = salt.encode()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password)

    def action_issue_certificate(self, password):
        """Generate user key pair and issue CA-signed certificate.

        :param password: User's Odoo password (used to encrypt private key)
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Certificate can only be issued in Draft state."))
        if self.ca_id.state != 'active':
            raise UserError(_("CA '%s' is not active.") % self.ca_id.name)

        # Generate user RSA-2048 key pair
        user_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Load CA key and certificate
        ca_key = self.ca_id._load_ca_private_key()
        ca_cert = self.ca_id._load_ca_certificate()

        # Build user certificate signed by CA
        now = datetime.datetime.now(datetime.timezone.utc)
        user_name = self.user_id.name or 'User'
        user_email = self.user_id.email or ''

        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, user_name),
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, user_email),
            x509.NameAttribute(
                NameOID.ORGANIZATION_NAME,
                self.company_id.name or 'Organization'),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(user_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        # Encrypt user private key with password-derived key
        import secrets
        salt = secrets.token_hex(16)
        derived = self._derive_key_from_password(password, salt)

        private_pem = user_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(derived),
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        # Compute fingerprint
        fingerprint = hashlib.sha256(cert_pem).hexdigest().upper()

        self.write({
            'private_key_enc': base64.b64encode(private_pem),
            'certificate_pem': base64.b64encode(cert_pem),
            'serial_number': str(cert.serial_number),
            'valid_from': cert.not_valid_before_utc.replace(tzinfo=None),
            'valid_to': cert.not_valid_after_utc.replace(tzinfo=None),
            'fingerprint': fingerprint,
            'key_salt': salt,
            'certificate_text': self.env['pki.certificate.authority']._format_certificate_text(
                cert, fingerprint),
            'state': 'active',
        })

    def action_open_issue_wizard(self):
        """Open wizard to capture user password and issue certificate."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Issue Certificate'),
            'res_model': 'pki.issue.cert.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_certificate_id': self.id,
            },
        }

    @staticmethod
    def _decode_binary(value):
        """Decode an Odoo Binary field (attachment=False) to raw bytes."""
        if not value:
            return None
        return base64.b64decode(value)

    def load_private_key(self, password):
        """Decrypt and return the user's private key.

        :param password: User's Odoo password
        :returns: RSA private key object
        """
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Certificate is not active (state: %s).") % self.state)

        pem_bytes = self._decode_binary(self.private_key_enc)
        if not pem_bytes:
            raise UserError(_("No private key found for this certificate."))

        derived = self._derive_key_from_password(password, self.key_salt)
        try:
            return serialization.load_pem_private_key(pem_bytes, password=derived)
        except (ValueError, TypeError):
            raise UserError(_("Invalid password. Cannot decrypt private key."))

    def load_certificate(self):
        """Load and return the X.509 certificate object."""
        self.ensure_one()
        cert_bytes = self._decode_binary(self.certificate_pem)
        if not cert_bytes:
            raise UserError(_("No certificate found."))
        return x509.load_pem_x509_certificate(cert_bytes)

    def re_encrypt_private_key(self, old_password, new_password):
        """Re-encrypt private key when user changes their Odoo password.

        :param old_password: Previous Odoo password
        :param new_password: New Odoo password
        """
        self.ensure_one()
        if self.state != 'active':
            return

        # Decrypt with old password
        private_key = self.load_private_key(old_password)

        # Re-encrypt with new password
        import secrets
        new_salt = secrets.token_hex(16)
        new_derived = self._derive_key_from_password(new_password, new_salt)

        new_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(new_derived),
        )
        self.write({
            'private_key_enc': base64.b64encode(new_pem),
            'key_salt': new_salt,
        })

    def action_suspend(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Only active certificates can be suspended."))
        self.state = 'suspended'

    def action_reactivate(self):
        self.ensure_one()
        if self.state != 'suspended':
            raise UserError(_("Only suspended certificates can be reactivated."))
        self.state = 'active'

    def action_revoke(self):
        self.ensure_one()
        if self.state not in ('active', 'suspended'):
            raise UserError(_("Certificate cannot be revoked from state '%s'.") % self.state)
        self.state = 'revoked'

    def is_valid(self):
        """Check if certificate is currently valid."""
        self.ensure_one()
        if self.state != 'active':
            return False
        now = fields.Datetime.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        return True
