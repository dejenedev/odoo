# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AmeRule(models.Model):
    _name = 'ame.rule'
    _description = 'AME Rule'
    _order = 'transaction_type_id, priority, sequence'

    name = fields.Char(string="Rule Name", required=True)
    description = fields.Text()
    transaction_type_id = fields.Many2one(
        'ame.transaction.type', string="Transaction Type",
        required=True, ondelete='cascade')
    active = fields.Boolean(default=True)

    sequence = fields.Integer(default=10, help="Ordering within same priority")
    priority = fields.Integer(
        default=10,
        help="Approval level. Lower numbers go first. "
             "Same priority = parallel within that level.")

    # Conditions (AND logic within a rule)
    condition_ids = fields.Many2many(
        'ame.condition', 'ame_rule_condition_rel',
        'rule_id', 'condition_id', string="Conditions (AND)")

    # Approver action
    approver_action_id = fields.Many2one(
        'ame.approver.action', string="Approver Action",
        required=True, ondelete='restrict')

    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company, required=True)

    # Validity period
    start_date = fields.Date(string="Effective From")
    end_date = fields.Date(string="Effective Until")

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError(
                    _("Effective From must be before Effective Until."))

    def evaluate(self, record):
        """Evaluate all conditions against a record.

        :param record: the document record
        :returns: True if all conditions pass (AND logic). Empty conditions = unconditional.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False

        if not self.condition_ids:
            return True  # No conditions = unconditional rule

        return all(cond.evaluate(record) for cond in self.condition_ids)
