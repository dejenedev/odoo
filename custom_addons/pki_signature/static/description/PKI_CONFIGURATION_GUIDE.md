# PKI Digital Signature — Configuration Guide

## Overview

The PKI Digital Signature module provides a self-managed Public Key Infrastructure (PKI) for cryptographically signing documents in Odoo. It supports multi-level approval chains, tamper detection, and visual signature capture.

---

## Prerequisites

- Odoo 19.0
- Python packages: `cryptography`, `asn1crypto` (included in Odoo dependencies)
- Admin access to Odoo

---

## Step 1: Assign PKI Security Groups

Before configuring PKI, assign the appropriate security groups to users.

1. Go to **Settings > Users & Companies > Users**
2. Open the user record
3. Under **Other** section, find **PKI Digital Signature**:
   - **PKI Signer** — Can sign documents when they are an approver
   - **PKI Administrator** — Can manage CAs, issue certificates, and configure rules
4. Assign **PKI Administrator** to the system admin
5. Assign **PKI Signer** to all users who will participate in approval workflows

---

## Step 2: Create a Certificate Authority (CA)

The CA is the root of trust. It issues and signs certificates for individual users.

1. Go to **Settings > PKI Digital Signature > Certificate Authorities**
2. Click **New**
3. Fill in:
   - **CA Name**: e.g., `Ministry of Finance CA` or `Budget System CA`
   - **Company**: Select the company this CA belongs to
4. Click **Save**
5. Click the **Generate CA** button
6. The system will:
   - Generate an RSA-2048 key pair
   - Create a self-signed X.509 certificate (valid for 10 years)
   - Encrypt the CA private key with a system master key
   - Set the CA status to **Active**

> **Note**: Only one CA can be active per company at a time.

### CA Details After Generation

| Field | Description |
|-------|-------------|
| Serial Number | Unique certificate serial |
| Valid From / To | Certificate validity period (10 years) |
| Key Size | 2048 bits (RSA) |
| Certificate Details | Shows Subject, Issuer, Serial, Algorithm |

---

## Step 3: Issue User Certificates

Each user who needs to sign documents must have a certificate issued by the CA.

### Method: Via PKI Administrator

1. Go to **Settings > PKI Digital Signature > User Certificates**
2. Click **New**
3. Fill in:
   - **User**: Select the Odoo user
   - **Certificate Authority**: Select the active CA
   - **Company**: Auto-filled
4. Click **Save**
5. The certificate is now in **Draft** state

### Issuing the Certificate

Certificate issuance requires the user's Odoo password (to encrypt their private key). This is done programmatically when the user first signs a document, or can be triggered by an admin via the technical interface.

**What happens during issuance:**
- RSA-2048 key pair generated for the user
- CA signs the user's public key → creates X.509 certificate
- User's private key encrypted with PBKDF2-derived key from their Odoo password
- Certificate valid for 1 year

### Certificate States

| State | Meaning |
|-------|---------|
| **Draft** | Created but not yet issued |
| **Active** | Issued and ready for signing |
| **Suspended** | Temporarily disabled (can be reactivated) |
| **Revoked** | Permanently disabled (cannot be undone) |
| **Expired** | Past the valid_to date |

### Certificate Actions

- **Suspend**: Temporarily disable (e.g., user on leave)
- **Reactivate**: Re-enable a suspended certificate
- **Revoke**: Permanently disable (e.g., user leaves the organization)

> **Important**: Revoking a certificate is permanent. Existing signatures remain verifiable, but the user cannot sign new documents.

---

## Step 4: Configure Approval Rules

Approval rules define which document types need signatures, how many levels of approval, and who can approve at each level.

1. Go to **Settings > PKI Digital Signature > Approval Rules**
2. Click **New**
3. Fill in:

| Field | Description | Example |
|-------|-------------|---------|
| **Step Name** | Descriptive name | "Department Head Approval" |
| **Document Type** | The Odoo model | `account.move` (Vendor Bills) or `purchase.order` |
| **Step Order** | Sequence in the chain (1 = first) | 1 |
| **Required Role** | Security group required to sign | "Accounting / Adviser" |
| **Minimum Amount** | Threshold (0 = all amounts) | 5000.00 |
| **Company** | Which company this rule applies to | Ministry of Finance |

### Example: Two-Level Approval for Vendor Bills

| Step | Name | Document Type | Order | Required Role | Min Amount |
|------|------|---------------|-------|---------------|------------|
| 1 | Department Head Review | Journal Entry (account.move) | 1 | Department Head | 0 |
| 2 | Finance Director Approval | Journal Entry (account.move) | 2 | Finance Director | 0 |
| 3 | CFO Sign-off (Large amounts) | Journal Entry (account.move) | 3 | CFO | 50,000 |

> Step 3 only applies when the document amount is >= 50,000.

### Fields to Hash

On the **Fields to Hash** tab, select which document fields should be included in the cryptographic hash. Changes to these fields after signing will be detected as **tampering**.

**Recommended fields for Vendor Bills (`account.move`):**
- `name` (Bill reference)
- `amount_total`
- `partner_id` (Vendor)
- `invoice_date`
- `state`

**Recommended fields for Purchase Orders (`purchase.order`):**
- `name`
- `amount_total`
- `partner_id`
- `date_order`
- `state`

> If no fields are selected, the system uses default business fields as fallback.

---

## Step 5: Using the Mixin (For Developers)

To enable PKI signatures on any Odoo model, inherit the mixin:

```python
class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'pki.signature.mixin']
```

Then add the following to the form view:

```xml
<!-- Header buttons -->
<button name="action_request_pki_approval"
        string="Request Approval"
        type="object"
        invisible="pki_approval_status not in ('none', 'rejected')"/>

<button name="action_open_sign_wizard"
        string="Approve &amp; Sign"
        type="object"
        class="btn-primary"
        invisible="not pki_is_current_approver"/>

<button name="action_open_verify_wizard"
        string="Verify Signatures"
        type="object"
        invisible="pki_approval_status == 'none'"/>

<!-- Approvals tab in notebook -->
<page string="Approvals" invisible="pki_approval_status == 'none'">
    <field name="pki_signature_line_ids" nolabel="1"/>
</page>
```

### Mixin Fields Available

| Field | Type | Description |
|-------|------|-------------|
| `pki_signature_line_ids` | One2many | All approval signature records |
| `pki_approval_status` | Selection | none / pending / signed / rejected |
| `pki_is_fully_signed` | Boolean | True when all steps are signed |
| `pki_current_step` | Char | Name of the next pending step |
| `pki_is_current_approver` | Boolean | True if current user can sign the next step |

### Mixin Methods Available

| Method | Description |
|--------|-------------|
| `action_request_pki_approval()` | Creates signature lines from applicable rules |
| `action_open_sign_wizard()` | Opens the signing dialog |
| `action_open_verify_wizard()` | Opens the verification dialog |
| `_pki_get_amount()` | Returns document amount (override for custom models) |

---

## Step 6: Signing Workflow

### For the Document Creator

1. Create and validate the document (e.g., post a vendor bill)
2. Click **"Request Approval"**
   - System creates pending signature lines based on applicable rules
   - Document status changes to "Awaiting Approval"

### For Approvers

1. Open the document
2. If you are the current approver, the **"Approve & Sign"** button is visible
3. Click **"Approve & Sign"**
4. In the dialog:
   - Your role is displayed (readonly)
   - The document hash preview is shown
   - Enter your **Odoo password** (to unlock your private key)
   - Draw or type your **visual signature**
   - Click **Sign**
5. The system:
   - Computes SHA-256 hash of configured document fields
   - Signs the hash with your RSA private key
   - Stores the digital signature, visual signature, and certificate reference
6. The next approver in the chain can now sign

### For Rejectors

1. Click **"Reject"** on the approval step
2. Enter a rejection reason
3. Document status changes to "Rejected"

---

## Step 7: Verifying Signatures

Anyone can verify the signatures on a document:

1. Open the document
2. Click **"Verify Signatures"**
3. The verification wizard shows:

| Column | Meaning |
|--------|---------|
| **Status** | Pending / Signed / Rejected |
| **Data Intact** | True if document hasn't been modified since signing |
| **Sig Valid** | True if RSA signature verification passes |
| **Cert Valid** | True if signer's certificate is active and not expired |

### Overall Status

| Status | Meaning |
|--------|---------|
| **All Valid** | All signatures pass all checks |
| **Tampering Detected** | Document was modified after signing (hash mismatch) |
| **Partially Signed** | Some steps still pending |
| **No Signatures** | No approval has been requested |

---

## Security Considerations

### Private Key Protection
- User private keys are encrypted with PBKDF2-derived keys (100,000 iterations, SHA-256)
- Encryption password = user's Odoo login password
- Keys are never stored in plaintext

### Password Changes
- When a user changes their Odoo password, the system should re-encrypt their private key
- Call `user._pki_re_encrypt_on_password_change(old_pw, new_pw)` in the password change flow

### Certificate Lifecycle
- **Issue** certificates only for active, verified users
- **Suspend** certificates when users go on extended leave
- **Revoke** immediately when users leave the organization
- **Monitor** expiry dates — certificates expire after 1 year by default

### Master Key
- The CA private key is encrypted with a system master key stored in `ir.config_parameter`
- Key: `pki_signature.master_key`
- **Back up this key** — losing it means you cannot issue new certificates from the CA
- Consider storing it in an environment variable for production

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No active PKI certificate" | Issue a certificate for the user (Step 3) |
| "Invalid password" on signing | User entered wrong Odoo password |
| "Required role" error | User is not in the security group required for this approval step |
| "Previous steps must be signed" | Approvals must happen in sequence order |
| Hash mismatch on verification | Someone modified the document after it was signed |
| CA generation fails | Check Python `cryptography` package is installed |

---

## Appendix: Architecture Diagram

```
┌─────────────────────────────────────────┐
│          Certificate Authority          │
│  (RSA-2048, self-signed X.509, 10yr)   │
│  Encrypted with system master key       │
└──────────────┬──────────────────────────┘
               │ signs
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│ User A │ │ User B │ │ User C │
│  Cert  │ │  Cert  │ │  Cert  │
│ (1yr)  │ │ (1yr)  │ │ (1yr)  │
└───┬────┘ └───┬────┘ └───┬────┘
    │          │          │
    ▼          ▼          ▼
┌─────────────────────────────────────────┐
│           Approval Rules                │
│  Model: account.move                    │
│  Step 1: Dept Head (seq=1)              │
│  Step 2: Finance Dir (seq=2)            │
│  Fields: amount_total, partner_id, ...  │
└──────────────┬──────────────────────────┘
               │ creates
               ▼
┌─────────────────────────────────────────┐
│        Signature Lines (per doc)        │
│  Line 1: Pending → Signed (User A)     │
│    - document_hash: SHA-256             │
│    - digital_signature: RSA-PKCS1v15    │
│    - visual_signature: image            │
│  Line 2: Pending → Signed (User B)     │
└─────────────────────────────────────────┘
```
