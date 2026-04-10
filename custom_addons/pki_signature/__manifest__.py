# -*- coding: utf-8 -*-
{
    'name': 'PKI Digital Signature',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Cryptographic digital signatures with PKI certificate management',
    'description': """
        Self-managed PKI infrastructure for Odoo:
        - Certificate Authority (CA) management
        - Per-user RSA-2048 certificate issuance
        - Configurable multi-level approval chains
        - Cryptographic document signing with tamper detection
        - PDF report signing (PKCS#7)
        - Visual signature capture
        - Signature verification
    """,
    'author': 'dejenedev',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'external_dependencies': {
        'python': ['cryptography', 'asn1crypto'],
    },
    'data': [
        'security/pki_security.xml',
        'security/ir.model.access.csv',
        'wizard/pki_issue_cert_wizard_views.xml',
        'wizard/pki_sign_wizard_views.xml',
        'wizard/pki_verify_wizard_views.xml',
        'views/pki_ca_views.xml',
        'views/pki_user_certificate_views.xml',
        'views/pki_approval_rule_views.xml',
        'views/pki_signature_line_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
