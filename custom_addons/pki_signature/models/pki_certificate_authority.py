# -*- coding: utf-8 -*-
import base64
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.x509.oid import NameOID

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PkiCertificateAuthority(models.Model):
    _name = 'pki.certificate.authority'
    _description = 'PKI Certificate Authority'
    _order = 'create_date desc'

    name = fields.Char(string="CA Name", required=True)
    private_key_pem = fields.Binary(
        string="CA Private Key (Encrypted)", attachment=True,
        help="RSA-2048 private key encrypted with system master key.")
    public_key_pem = fields.Binary(
        string="CA Public Key", attachment=True)
    certificate_pem = fields.Binary(
        string="CA Certificate", attachment=True,
        help="Self-signed X.509 CA certificate.")
    certificate_text = fields.Text(
        string="Certificate Details", compute='_compute_certificate_text')
    serial_number = fields.Char(string="Serial Number", readonly=True)
    valid_from = fields.Datetime(string="Valid From", readonly=True)
    valid_to = fields.Datetime(string="Valid To", readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    ], string="Status", default='draft', required=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        help="Leave empty for a system-wide CA shared across all companies/ministries.")
    issued_count = fields.Integer(
        string="Certificates Issued", compute='_compute_issued_count')
    key_size = fields.Integer(string="Key Size", default=2048, readonly=True)

    @api.depends('certificate_pem')
    def _compute_certificate_text(self):
        for rec in self:
            if rec.certificate_pem:
                try:
                    cert_bytes = base64.b64decode(rec.certificate_pem)
                    cert = x509.load_pem_x509_certificate(cert_bytes)
                    rec.certificate_text = (
                        "Subject: %s\n"
                        "Issuer: %s\n"
                        "Serial: %s\n"
                        "Valid: %s to %s\n"
                        "Algorithm: %s"
                    ) % (
                        cert.subject.rfc4514_string(),
                        cert.issuer.rfc4514_string(),
                        cert.serial_number,
                        cert.not_valid_before_utc,
                        cert.not_valid_after_utc,
                        cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else 'N/A',
                    )
                except Exception:
                    rec.certificate_text = _("Unable to parse certificate")
            else:
                rec.certificate_text = False

    def _compute_issued_count(self):
        for rec in self:
            rec.issued_count = self.env['pki.user.certificate'].search_count([
                ('ca_id', '=', rec.id),
            ])

    @api.constrains('state')
    def _check_single_active_ca(self):
        for rec in self:
            if rec.state == 'active':
                existing = self.search([
                    ('state', '=', 'active'),
                    ('id', '!=', rec.id),
                ])
                if existing:
                    raise ValidationError(_(
                        "Only one active CA is allowed in the system. "
                        "'%s' is already active."
                    ) % existing[0].name)

    def _get_master_key(self):
        """Get or generate the system master key for encrypting CA private keys."""
        ICP = self.env['ir.config_parameter'].sudo()
        master_key = ICP.get_param('pki_signature.master_key')
        if not master_key:
            import secrets
            master_key = secrets.token_hex(32)
            ICP.set_param('pki_signature.master_key', master_key)
        return master_key.encode()

    def _derive_key(self, password, salt):
        """Derive an encryption key from a password using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password)

    def action_generate_ca(self):
        """Generate CA key pair and self-signed certificate."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("CA can only be generated in Draft state."))

        # Generate RSA-2048 key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Build self-signed CA certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                               self.company_id.name or 'Organization'),
            x509.NameAttribute(NameOID.COMMON_NAME, self.name),
        ])

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))  # 10 years
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Encrypt private key with system master key
        master_key = self._get_master_key()
        salt = b'pki_ca_salt_' + str(self.id).encode()
        derived = self._derive_key(master_key, salt)

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(derived),
        )
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        self.write({
            'private_key_pem': base64.b64encode(private_pem),
            'public_key_pem': base64.b64encode(public_pem),
            'certificate_pem': base64.b64encode(cert_pem),
            'serial_number': str(cert.serial_number),
            'valid_from': cert.not_valid_before_utc,
            'valid_to': cert.not_valid_after_utc,
            'state': 'active',
            'key_size': 2048,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("CA Generated"),
                'message': _("Certificate Authority '%s' has been generated and activated.") % self.name,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_revoke(self):
        """Revoke this CA."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Only active CAs can be revoked."))
        self.state = 'revoked'

    def _load_ca_private_key(self):
        """Load and decrypt the CA private key."""
        self.ensure_one()
        if not self.private_key_pem:
            raise UserError(_("CA private key not found."))
        master_key = self._get_master_key()
        salt = b'pki_ca_salt_' + str(self.id).encode()
        derived = self._derive_key(master_key, salt)
        pem_bytes = base64.b64decode(self.private_key_pem)
        return serialization.load_pem_private_key(pem_bytes, password=derived)

    def _load_ca_certificate(self):
        """Load the CA X.509 certificate."""
        self.ensure_one()
        if not self.certificate_pem:
            raise UserError(_("CA certificate not found."))
        cert_bytes = base64.b64decode(self.certificate_pem)
        return x509.load_pem_x509_certificate(cert_bytes)
