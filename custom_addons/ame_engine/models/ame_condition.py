# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AmeCondition(models.Model):
    _name = 'ame.condition'
    _description = 'AME Condition'
    _order = 'attribute_id, id'

    name = fields.Char(compute='_compute_name', store=True)
    attribute_id = fields.Many2one(
        'ame.attribute', string="Attribute", required=True, ondelete='cascade')
    attribute_value_type = fields.Selection(
        related='attribute_id.value_type', string="Attribute Data Type")
    transaction_type_id = fields.Many2one(
        related='attribute_id.transaction_type_id', store=True)
    active = fields.Boolean(default=True)

    operator = fields.Selection([
        ('=', 'Equals (=)'),
        ('!=', 'Not Equals (!=)'),
        ('>', 'Greater Than (>)'),
        ('<', 'Less Than (<)'),
        ('>=', 'Greater or Equal (>=)'),
        ('<=', 'Less or Equal (<=)'),
        ('in', 'In List'),
        ('not_in', 'Not In List'),
        ('between', 'Between'),
        ('contains', 'Contains'),
    ], required=True, default='=')

    # Comparison values
    value_float = fields.Float(string="Numeric Value")
    value_char = fields.Char(string="Text Value",
                             help="For 'in'/'not_in': comma-separated list")
    value_float_2 = fields.Float(string="Upper Bound",
                                 help="Used for 'between' operator")

    @api.depends('attribute_id.name', 'operator', 'value_char', 'value_float', 'value_float_2')
    def _compute_name(self):
        for rec in self:
            attr = rec.attribute_id.display_name_custom or rec.attribute_id.name or '?'
            op = dict(rec._fields['operator'].selection).get(rec.operator, '?')
            if rec.attribute_id.value_type == 'float':
                if rec.operator == 'between':
                    val = '{:,.2f} - {:,.2f}'.format(rec.value_float, rec.value_float_2)
                else:
                    val = '{:,.2f}'.format(rec.value_float)
            else:
                val = rec.value_char or ''
            rec.name = '%s %s %s' % (attr, op, val)

    def evaluate(self, record):
        """Evaluate this condition against a record.

        :param record: the document record
        :returns: True if condition is met, False otherwise
        """
        self.ensure_one()
        try:
            attr_value = self.attribute_id.evaluate(record)
            return self._compare(attr_value)
        except Exception as e:
            _logger.warning(
                "AME condition '%s' evaluation failed: %s", self.name, e)
            return False

    def _compare(self, attr_value):
        """Compare extracted attribute value against condition's threshold."""
        op = self.operator
        vtype = self.attribute_id.value_type

        # Get comparison value based on attribute type
        if vtype == 'float':
            comp_val = self.value_float
            try:
                attr_value = float(attr_value or 0)
            except (ValueError, TypeError):
                attr_value = 0.0
        elif vtype == 'boolean':
            comp_val = self.value_char and self.value_char.lower() in ('true', '1', 'yes')
            attr_value = bool(attr_value)
        else:
            comp_val = self.value_char or ''
            attr_value = str(attr_value) if attr_value else ''

        if op == '=':
            return attr_value == comp_val
        elif op == '!=':
            return attr_value != comp_val
        elif op == '>':
            return attr_value > comp_val
        elif op == '<':
            return attr_value < comp_val
        elif op == '>=':
            return attr_value >= comp_val
        elif op == '<=':
            return attr_value <= comp_val
        elif op == 'in':
            val_list = [v.strip() for v in (self.value_char or '').split(',')]
            return str(attr_value) in val_list
        elif op == 'not_in':
            val_list = [v.strip() for v in (self.value_char or '').split(',')]
            return str(attr_value) not in val_list
        elif op == 'between':
            try:
                return self.value_float <= float(attr_value) <= self.value_float_2
            except (ValueError, TypeError):
                return False
        elif op == 'contains':
            return (self.value_char or '') in str(attr_value)

        return False
