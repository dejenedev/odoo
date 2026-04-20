# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, datetime as se_datetime, dateutil as se_dateutil, time as se_time

_logger = logging.getLogger(__name__)


class AmeAttribute(models.Model):
    _name = 'ame.attribute'
    _description = 'AME Attribute'
    _order = 'transaction_type_id, name'

    name = fields.Char(string="Technical Name", required=True,
                       help="e.g. 'po_total_amount', 'vendor_country'")
    display_name_custom = fields.Char(string="Display Name",
                                      help="User-friendly label")
    description = fields.Text()
    transaction_type_id = fields.Many2one(
        'ame.transaction.type', string="Transaction Type",
        required=True, ondelete='cascade')
    model_id = fields.Many2one(
        related='transaction_type_id.model_id', store=True)
    active = fields.Boolean(default=True)

    attribute_type = fields.Selection([
        ('static', 'Static Field'),
        ('relational', 'Relational Field (Dot Notation)'),
        ('computed', 'Computed (Python Expression)'),
        ('line_item', 'Line-Item Aggregate'),
    ], required=True, default='static')

    # For static type
    field_id = fields.Many2one(
        'ir.model.fields', string="Field",
        domain="[('model_id', '=', model_id), ('store', '=', True)]")

    # For relational type
    field_path = fields.Char(
        string="Field Path",
        help="Dot-notation path, e.g. 'partner_id.country_id.code'")

    # For computed type
    python_expression = fields.Text(
        string="Python Expression",
        help="Expression evaluated via safe_eval. "
             "Available: record, user, datetime, dateutil, time. "
             "Must return a value. E.g.: sum(l.price_subtotal for l in record.order_line)")

    # For line_item type
    line_field_id = fields.Many2one(
        'ir.model.fields', string="Lines Field",
        domain="[('model_id', '=', model_id), ('ttype', '=', 'one2many')]",
        help="One2many field pointing to line items")
    line_model_id = fields.Many2one(
        'ir.model', string="Line Model",
        compute='_compute_line_model_id')
    line_item_field_id = fields.Many2one(
        'ir.model.fields', string="Line Item Field",
        domain="[('model_id', '=', line_model_id), ('store', '=', True), "
               "('ttype', 'not in', ('one2many', 'many2many', 'binary'))]",
        help="Field on each line item to aggregate")
    line_item_field_path = fields.Char(
        string="Line Item Path",
        compute='_compute_line_item_field_path', store=True, readonly=False,
        help="Auto-populated from Line Item Field selection")
    line_aggregate = fields.Selection([
        ('sum', 'Sum'),
        ('min', 'Minimum'),
        ('max', 'Maximum'),
        ('avg', 'Average'),
        ('any', 'Any (Boolean OR)'),
        ('all', 'All (Boolean AND)'),
        ('count', 'Count'),
    ], string="Aggregation", default='sum')

    @api.depends('line_field_id')
    def _compute_line_model_id(self):
        for rec in self:
            if rec.line_field_id and rec.line_field_id.relation:
                line_model = self.env['ir.model']._get(rec.line_field_id.relation)
                rec.line_model_id = line_model.id if line_model else False
            else:
                rec.line_model_id = False

    @api.depends('line_item_field_id')
    def _compute_line_item_field_path(self):
        for rec in self:
            rec.line_item_field_path = rec.line_item_field_id.name if rec.line_item_field_id else False

    # Return type
    value_type = fields.Selection([
        ('float', 'Numeric'),
        ('char', 'Text'),
        ('boolean', 'Boolean'),
        ('date', 'Date'),
    ], required=True, default='float')

    def evaluate(self, record):
        """Extract the runtime value of this attribute from a document record.

        :param record: Odoo record (the document)
        :returns: extracted value (typed)
        """
        self.ensure_one()
        try:
            if self.attribute_type == 'static':
                return record[self.field_id.name] if self.field_id else False

            elif self.attribute_type == 'relational':
                value = record
                for part in (self.field_path or '').split('.'):
                    if not part or not value:
                        return False
                    value = value[part]
                # Convert recordset to ID for Many2one
                if hasattr(value, 'id') and hasattr(value, '_name'):
                    value = value.id
                return value

            elif self.attribute_type == 'computed':
                eval_context = {
                    'record': record.sudo(),
                    'user': self.env.user,
                    'datetime': se_datetime,
                    'dateutil': se_dateutil,
                    'time': se_time,
                }
                return safe_eval(
                    (self.python_expression or '').strip(),
                    eval_context,
                    filename='ame.attribute(%s)' % self.id,
                )

            elif self.attribute_type == 'line_item':
                if not self.line_field_id:
                    return False
                lines = record[self.line_field_id.name]
                values = []
                for line in lines:
                    val = line
                    for part in (self.line_item_field_path or '').split('.'):
                        if not part or not val:
                            break
                        val = val[part]
                    if hasattr(val, 'id') and hasattr(val, '_name'):
                        val = val.id
                    values.append(val)

                agg = self.line_aggregate
                if not values:
                    return 0 if agg in ('sum', 'min', 'max', 'avg', 'count') else False
                if agg == 'sum':
                    return sum(values)
                elif agg == 'min':
                    return min(values)
                elif agg == 'max':
                    return max(values)
                elif agg == 'avg':
                    return sum(values) / len(values)
                elif agg == 'any':
                    return any(values)
                elif agg == 'all':
                    return all(values)
                elif agg == 'count':
                    return len(values)

        except Exception as e:
            _logger.warning("AME attribute '%s' evaluation failed: %s", self.name, e)
            return False

        return False

    @api.constrains('python_expression', 'attribute_type')
    def _check_expression(self):
        for rec in self:
            if rec.attribute_type == 'computed' and not rec.python_expression:
                raise ValidationError(
                    _("Python expression is required for computed attributes."))
