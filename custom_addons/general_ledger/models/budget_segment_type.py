# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetSegmentType(models.Model):
    _name = 'budget.segment.type'
    _description = 'Budget Segment Type'
    _order = 'sequence, id'

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True)
    sequence = fields.Integer(string="Display Order", default=10,
                              help="Determines the order of segments in code combinations and forms.")
    total_digits = fields.Integer(string="Total Digits", required=True,
                                  help="Total number of digits in this segment code.")
    is_economic = fields.Boolean(string="Is Economic Segment",
                                 help="If checked, this segment uses the Odoo Chart of Accounts "
                                      "instead of custom segment values.")
    is_organization = fields.Boolean(string="Is Organization Segment",
                                      help="If checked, this segment represents organizational units. "
                                           "Values can be assigned to budget organizations.")
    level_ids = fields.One2many('budget.segment.level', 'segment_type_id', string="Levels")
    value_ids = fields.One2many('budget.segment.value', 'segment_type_id', string="Values")
    active = fields.Boolean(default=True)
    separator = fields.Char(string="Code Separator", default="-",
                            help="Character used to separate levels in the segment code display.")
    company_id = fields.Many2one('res.company', string="Company")

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'Segment type code must be unique per company.',
    )

    @api.constrains('total_digits', 'level_ids')
    def _check_total_digits(self):
        for rec in self:
            level_sum = sum(rec.level_ids.mapped('digit_count'))
            if level_sum and level_sum > rec.total_digits:
                raise ValidationError(
                    _("The sum of digits across levels (%d) exceeds "
                      "the total digits (%d) for segment '%s'. "
                      "Remove a level or increase Total Digits.")
                    % (level_sum, rec.total_digits, rec.name)
                )
            if level_sum and level_sum != rec.total_digits:
                raise ValidationError(
                    _("The sum of digits across levels (%d) does not match "
                      "the total digits (%d) for segment '%s'.")
                    % (level_sum, rec.total_digits, rec.name)
                )


class BudgetSegmentLevel(models.Model):
    _name = 'budget.segment.level'
    _description = 'Budget Segment Level'
    _order = 'segment_type_id, level_number'

    segment_type_id = fields.Many2one('budget.segment.type', string="Segment Type",
                                      required=True, ondelete='cascade')
    level_number = fields.Integer(string="Level", required=True)
    name = fields.Char(string="Level Name", required=True, translate=True)
    digit_count = fields.Integer(string="Number of Digits", required=True)
    is_leaf = fields.Boolean(string="Is Leaf", compute='_compute_is_leaf', store=True)

    _level_uniq = models.Constraint(
        'unique(segment_type_id, level_number)',
        'Level number must be unique within a segment type.',
    )

    @api.depends('level_number', 'segment_type_id.level_ids', 'segment_type_id.level_ids.level_number')
    def _compute_is_leaf(self):
        for rec in self:
            if rec.segment_type_id and rec.segment_type_id.level_ids:
                max_level = max(rec.segment_type_id.level_ids.mapped('level_number'))
                rec.is_leaf = (rec.level_number == max_level)
            else:
                rec.is_leaf = False
