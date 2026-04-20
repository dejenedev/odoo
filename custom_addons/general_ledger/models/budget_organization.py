# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetOrganization(models.Model):
    _name = 'budget.organization'
    _description = 'Budget Organization'
    _order = 'code'

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True)
    company_id = fields.Many2one('res.company', string="Company",
                                  required=True, ondelete='cascade', index=True)
    active = fields.Boolean(default=True)
    is_paying_org = fields.Boolean(
        string="Is Paying Organization",
        help="If checked, this organization consolidates payments "
             "from all other organizations and sends to the bank.")
    segment_value_ids = fields.Many2many(
        'budget.segment.value',
        'budget_org_segment_value_rel',
        'organization_id', 'segment_value_id',
        string="Organization Segment Values",
        help="Allowed organization segment codes for this organization's transactions.")
    bank_account_ids = fields.Many2many(
        'res.partner.bank',
        'budget_org_bank_rel',
        'organization_id', 'bank_id',
        string="Bank Accounts",
        help="Bank accounts available for consolidated payments.")
    payment_journal_id = fields.Many2one(
        'account.journal', string="Payment Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="Default journal for consolidated payments.")
    clearing_account_id = fields.Many2one(
        'account.account', string="Inter-Company Clearing Account",
        domain="[('company_ids', 'in', company_id)]",
        help="Account used for inter-company clearing entries. "
             "E.g. 'Due to/from Paying Organization'.")
    clearing_journal_id = fields.Many2one(
        'account.journal', string="Clearing Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help="Journal used for inter-company clearing entries.")
    notes = fields.Text(string="Notes")

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)',
         'Only one organization can be linked to a company.'),
        ('code_uniq', 'unique(code)',
         'Organization code must be unique.'),
    ]

    @api.constrains('is_paying_org')
    def _check_single_paying_org(self):
        for rec in self:
            if rec.is_paying_org:
                existing = self.search([
                    ('is_paying_org', '=', True),
                    ('id', '!=', rec.id),
                ])
                if existing:
                    raise ValidationError(
                        _("Only one organization can be the Paying Organization. "
                          "'%s' is already designated.") % existing[0].name
                    )

    def action_sync_coa(self):
        """Sync Chart of Accounts to this organization's company.

        Adds this company to the company_ids of all accounts that were
        created through economic segment values, making them accessible.
        """
        self.ensure_one()
        # Find all accounts linked to economic segment values
        eco_values = self.env['budget.segment.value'].sudo().search([
            ('is_economic', '=', True),
            ('account_id', '!=', False),
        ])
        accounts = eco_values.mapped('account_id')
        synced = 0
        created = 0
        company = self.company_id
        # Account types that Odoo does not allow to share between companies
        no_share_types = ('asset_cash',)
        for account in accounts:
            if company not in account.company_ids:
                original_code = account.with_company(
                    account.company_ids[:1]).code
                if account.account_type in no_share_types:
                    # Create a separate account for this company
                    existing = self.env['account.account'].with_company(
                        company).sudo().search([
                            ('code', '=', original_code),
                            ('company_ids', 'in', [company.id]),
                        ], limit=1)
                    if not existing:
                        new_account = self.env['account.account'].with_company(
                            company).sudo().create({
                                'code': original_code,
                                'name': account.name,
                                'account_type': account.account_type,
                                'reconcile': account.reconcile,
                                'company_ids': [(6, 0, [company.id])],
                            })
                        created += 1
                else:
                    # Share the account across companies
                    account.with_company(company).sudo().write({
                        'company_ids': [(4, company.id)],
                        'code': original_code,
                    })
                    synced += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("COA Sync Complete"),
                'message': _("%d account(s) shared, %d account(s) created for %s.") % (
                    synced, created, self.company_id.name),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.constrains('segment_value_ids')
    def _check_segment_values_organization_type(self):
        for rec in self:
            for val in rec.segment_value_ids:
                if not val.segment_type_id.is_organization:
                    raise ValidationError(
                        _("Segment value '%s' does not belong to an Organization segment type.")
                        % val.display_name
                    )
