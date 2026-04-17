# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import models

_logger = logging.getLogger(__name__)

try:
    from odoo.tools.pdf.signature import PdfSigner
    from cryptography.hazmat.primitives.serialization import Encoding
    HAS_PDF_SIGNER = True
except (ImportError, AttributeError):
    HAS_PDF_SIGNER = False


class PkiPdfSigner(PdfSigner):
    """PdfSigner subclass that uses PKI module certificates."""

    def __init__(self, stream, private_key, certificate, **kwargs):
        """Initialize with explicit key and certificate.

        :param stream: PDF BytesIO stream
        :param private_key: RSA private key object (already decrypted)
        :param certificate: cryptography x509.Certificate object
        """
        self._pki_private_key = private_key
        self._pki_certificate = certificate
        # Call parent without company — we override _load_key_and_certificate
        super().__init__(stream, company=None, **kwargs)
        # Re-set company to None after parent init
        self.company = None

    def _load_key_and_certificate(self):
        """Override to return PKI module's key and certificate."""
        return self._pki_private_key, self._pki_certificate

    def sign_pdf(self, visible_signature=False, field_name="PKI Signature", signer=None):
        """Override to bypass the company check."""
        if not self._pki_private_key or not self._pki_certificate:
            return None

        dummy, sig_field_value = self._setup_form(visible_signature, field_name, signer)

        if not self._perform_signature(sig_field_value):
            return None

        out_stream = io.BytesIO()
        self.writer.write_stream(out_stream)
        return out_stream


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """Override to sign PDFs with PKI certificates for fully-signed documents."""
        pdf_content, report_type = super()._render_qweb_pdf(
            report_ref, res_ids=res_ids, data=data)

        if report_type != 'pdf' or not HAS_PDF_SIGNER or not res_ids:
            return pdf_content, report_type

        # Check if the report's model uses PKI signatures
        report_sudo = self._get_report(report_ref)
        model_name = report_sudo.model
        if not model_name:
            return pdf_content, report_type

        try:
            Model = self.env[model_name]
            if 'pki.signature.mixin' not in getattr(Model, '_inherit', []) \
                    and not hasattr(Model, 'pki_is_fully_signed'):
                return pdf_content, report_type
        except KeyError:
            return pdf_content, report_type

        # Get the records
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        records = self.env[model_name].browse(res_ids)

        # Find a fully-signed record to get the signing certificate
        signed_record = None
        for rec in records:
            if hasattr(rec, 'pki_is_fully_signed') and rec.pki_is_fully_signed:
                signed_record = rec
                break

        if not signed_record:
            return pdf_content, report_type

        # Get the last signer's certificate (most authoritative)
        last_sig = signed_record.pki_signature_line_ids.filtered(
            lambda l: l.status == 'signed'
        ).sorted('sequence', reverse=True)[:1]

        if not last_sig or not last_sig.certificate_id:
            return pdf_content, report_type

        cert_record = last_sig.certificate_id
        try:
            certificate = cert_record.load_certificate()
            # We need the CA private key to sign the PDF, but we don't have the
            # user's password at report time. Instead, use the CA certificate
            # to sign the PDF, which proves it came from our trusted system.
            ca = cert_record.ca_id
            ca_private_key = ca._load_ca_private_key()
            ca_certificate = ca._load_ca_certificate()
        except Exception as e:
            _logger.warning("PKI PDF signing failed: %s", e)
            return pdf_content, report_type

        # Sign the PDF
        try:
            pdf_stream = io.BytesIO(pdf_content)
            signer = PkiPdfSigner(
                pdf_stream,
                private_key=ca_private_key,
                certificate=ca_certificate,
            )
            signed_stream = signer.sign_pdf(
                visible_signature=True,
                field_name="PKI Digital Signature",
                signer=last_sig.signer_id,
            )
            if signed_stream:
                pdf_content = signed_stream.getvalue()
                _logger.info(
                    "PDF digitally signed for %s record(s) %s",
                    model_name, res_ids,
                )
        except Exception as e:
            _logger.warning("PKI PDF signing error: %s", e)

        return pdf_content, report_type
