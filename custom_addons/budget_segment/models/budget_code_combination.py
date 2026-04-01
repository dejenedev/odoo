# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetCodeCombination(models.Model):
    _name = 'budget.code.combination'
    _description = 'Budget Code Combination'
    _order = 'combination_code'
    _rec_name = 'combination_code'

    combination_code = fields.Char(string="Code Combination",
                                   compute='_compute_combination_code',
                                   store=True, index=True)
    segment_summary = fields.Html(string="Segment Details",
                                  compute='_compute_segment_summary')
    line_ids = fields.One2many('budget.code.combination.line', 'combination_id',
                               string="Segment Values")
    account_id = fields.Many2one('account.account', string="Account (Economic Segment)",
                                 compute='_compute_account_id', store=True,
                                 help="Auto-populated from the economic segment value.")
    date_from = fields.Date(string="Effective Date",
                            help="Start date from which this combination can be used.")
    date_to = fields.Date(string="End Date",
                          help="End date after which this combination can no longer be used.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string="Company",
                                 default=lambda self: self.env.company, required=True)
    notes = fields.Text(string="Notes")

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(
                    _("Effective Date must be before End Date.")
                )

    @api.depends('line_ids.segment_value_id.account_id')
    def _compute_account_id(self):
        for rec in self:
            eco_line = rec.line_ids.filtered(lambda l: l.segment_type_id.is_economic)
            if eco_line and eco_line[0].segment_value_id.account_id:
                rec.account_id = eco_line[0].segment_value_id.account_id
            else:
                rec.account_id = False

    @api.depends('line_ids.segment_value_id', 'line_ids.segment_type_id')
    def _compute_segment_summary(self):
        for rec in self:
            rows = []
            sorted_lines = rec.line_ids.sorted(
                key=lambda l: l.segment_type_id.sequence
            )
            for line in sorted_lines:
                code = line.segment_value_id.full_code or ''
                name = line.segment_value_id.name or ''
                rows.append(
                    '<tr>'
                    '<td style="padding:4px 12px 4px 0;font-weight:bold;">%s</td>'
                    '<td style="padding:4px 12px;">%s</td>'
                    '<td style="padding:4px 12px;">%s</td>'
                    '</tr>' % (line.segment_type_id.name, code, name)
                )
            if rows:
                html = (
                    '<table style="width:100%%;">'
                    '<tr style="border-bottom:1px solid #dee2e6;">'
                    '<th style="padding:4px 12px 4px 0;">Segment</th>'
                    '<th style="padding:4px 12px;">Code</th>'
                    '<th style="padding:4px 12px;">Description</th>'
                    '</tr>'
                    '%s'
                    '</table>'
                ) % ''.join(rows)
                rec.segment_summary = Markup(html)
            else:
                rec.segment_summary = False

    @api.depends('line_ids.segment_value_id.full_code',
                 'line_ids.segment_type_id.sequence')
    def _compute_combination_code(self):
        for rec in self:
            parts = []
            sorted_lines = rec.line_ids.sorted(
                key=lambda l: l.segment_type_id.sequence
            )
            for line in sorted_lines:
                if line.segment_value_id and line.segment_value_id.full_code:
                    parts.append(line.segment_value_id.full_code)
            rec.combination_code = '-'.join(parts) if parts else ''

    @api.constrains('line_ids')
    def _check_unique_combination(self):
        for rec in self:
            seg_types = rec.line_ids.mapped('segment_type_id')
            if len(seg_types) != len(set(seg_types.ids)):
                raise ValidationError(
                    _("Each segment type can only appear once in a code combination.")
                )

    @api.constrains('line_ids')
    def _check_all_segments_populated(self):
        all_types = self.env['budget.segment.type'].search([
            ('active', '=', True),
            ('company_id', 'in', [False] + self.env.company.ids),
        ])
        for rec in self:
            populated_types = rec.line_ids.mapped('segment_type_id')
            missing = all_types - populated_types
            if missing:
                names = ', '.join(missing.mapped('name'))
                raise ValidationError(
                    _("All segment types must be populated. Missing: %s") % names
                )
            for line in rec.line_ids:
                if not line.segment_value_id.is_last_level:
                    raise ValidationError(
                        _("Segment '%s' must be set to the lowest hierarchy level. "
                          "'%s' is not a last-level value.")
                        % (line.segment_type_id.name, line.segment_value_id.display_name)
                    )

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, rec.combination_code or _('New')))
        return result

    @api.model
    def find_combination(self, segment_values, account_id=None):
        """Search for an existing code combination matching the given segment values.

        :param segment_values: dict of {segment_type_id: segment_value_id}
        :param account_id: int (optional, for backward compat), the account.account id
        :return: recordset of budget.code.combination or empty
        """
        domain = [('company_id', '=', self.env.company.id)]
        if account_id:
            domain.append(('account_id', '=', account_id))
        candidates = self.search(domain)
        for combo in candidates:
            combo_map = {
                line.segment_type_id.id: line.segment_value_id.id
                for line in combo.line_ids
            }
            if combo_map == segment_values:
                return combo
        return self.browse()


class BudgetCodeCombinationLine(models.Model):
    _name = 'budget.code.combination.line'
    _description = 'Budget Code Combination Line'
    _order = 'segment_sequence, id'

    combination_id = fields.Many2one('budget.code.combination', string="Combination",
                                     required=True, ondelete='cascade')
    segment_type_id = fields.Many2one('budget.segment.type', string="Segment Type",
                                      required=True)
    segment_sequence = fields.Integer(related='segment_type_id.sequence', store=True)
    is_economic = fields.Boolean(related='segment_type_id.is_economic', store=True)
    segment_value_id = fields.Many2one('budget.segment.value', string="Segment Value",
                                       required=True,
                                       domain="[('segment_type_id', '=', segment_type_id), "
                                              "('is_last_level', '=', True)]")
    full_code = fields.Char(related='segment_value_id.full_code', string="Code")
    value_name = fields.Char(related='segment_value_id.name', string="Description")
    company_id = fields.Many2one(related='combination_id.company_id', store=True)
