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

    @api.constrains('condition_ids')
    def _check_mutually_exclusive_conditions(self):
        """Validate that conditions within a rule are not mutually exclusive."""
        for rule in self:
            if len(rule.condition_ids) < 2:
                continue

            # Group conditions by attribute
            by_attr = {}
            for cond in rule.condition_ids:
                by_attr.setdefault(cond.attribute_id.id, [])
                by_attr[cond.attribute_id.id].append(cond)

            for attr_id, conds in by_attr.items():
                if len(conds) < 2:
                    continue

                # Check numeric conditions on same attribute for mutual exclusion
                numeric_conds = [c for c in conds if c.attribute_id.value_type == 'float']
                if len(numeric_conds) < 2:
                    continue

                for i, c1 in enumerate(numeric_conds):
                    for c2 in numeric_conds[i + 1:]:
                        if self._are_mutually_exclusive(c1, c2):
                            raise ValidationError(_(
                                "Rule '%s' has mutually exclusive conditions "
                                "that can never both be true (AND logic):\n\n"
                                "  - %s\n"
                                "  - %s\n\n"
                                "These conditions contradict each other. "
                                "If you need OR logic, create separate rules instead."
                            ) % (rule.name, c1.name, c2.name))

    @staticmethod
    def _are_mutually_exclusive(c1, c2):
        """Check if two numeric conditions on the same attribute are mutually exclusive.

        Returns True if both conditions can never be true simultaneously.
        """
        # Get the effective ranges for each condition
        r1 = AmeRule._get_numeric_range(c1)
        r2 = AmeRule._get_numeric_range(c2)
        if r1 is None or r2 is None:
            return False

        # Check if ranges overlap
        low1, high1 = r1
        low2, high2 = r2
        return high1 < low2 or high2 < low1

    @staticmethod
    def _get_numeric_range(cond):
        """Return (low, high) range that a condition represents.

        Returns None if the condition doesn't define a clear numeric range.
        """
        op = cond.operator
        val = cond.value_float
        val2 = cond.value_float_2
        INF = float('inf')

        if op == '=':
            return (val, val)
        elif op == '>':
            return (val + 0.01, INF)
        elif op == '>=':
            return (val, INF)
        elif op == '<':
            return (-INF, val - 0.01)
        elif op == '<=':
            return (-INF, val)
        elif op == 'between':
            return (val, val2)
        elif op == '!=':
            return None  # Can't determine a range for !=
        return None

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
