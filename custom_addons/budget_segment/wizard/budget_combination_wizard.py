# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BudgetCombinationWizard(models.TransientModel):
    _name = 'budget.combination.wizard'
    _description = 'Budget Code Combination Selector'

    move_line_id = fields.Many2one('account.move.line', string="Journal Item")
    account_id = fields.Many2one('account.account', string="Account",
                                 readonly=True)
    combination_id = fields.Many2one('budget.code.combination',
                                     string="Matched Combination", readonly=True)
    combination_code = fields.Char(related='combination_id.combination_code',
                                   string="Code Combination")
    line_ids = fields.One2many('budget.combination.wizard.line', 'wizard_id',
                               string="Segments")
    state = fields.Selection([('select', 'Select'), ('found', 'Found'), ('not_found', 'Not Found')],
                             default='select')
    message = fields.Char(string="Message", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_move_line_id')
        if active_id:
            move_line = self.env['account.move.line'].browse(active_id)
            res['move_line_id'] = move_line.id
            res['account_id'] = move_line.account_id.id
            existing_combo = move_line.budget_combination_id
            # Get ALL segment types ordered by sequence
            all_seg_types = self.env['budget.segment.type'].search(
                [('active', '=', True),
                 ('company_id', 'in', [move_line.company_id.id, False])],
                order='sequence'
            )
            lines = []
            for seg_type in all_seg_types:
                vals = {
                    'segment_type_id': seg_type.id,
                    'segment_name': seg_type.name,
                    'is_economic': seg_type.is_economic,
                }
                if seg_type.is_economic:
                    # For economic segment, pre-select the value matching the account
                    if move_line.account_id:
                        _logger.info("BUDGET WIZARD: account_id=%s, code=%s, seg_type=%s",
                                     move_line.account_id.id, move_line.account_id.code, seg_type.id)
                        # First try matching by linked account_id
                        eco_value = self.env['budget.segment.value'].search([
                            ('segment_type_id', '=', seg_type.id),
                            ('account_id', '=', move_line.account_id.id),
                            ('is_last_level', '=', True),
                        ], limit=1)
                        # Fallback: match by full_code = account code
                        if not eco_value:
                            eco_value = self.env['budget.segment.value'].search([
                                ('segment_type_id', '=', seg_type.id),
                                ('full_code', '=', move_line.account_id.code),
                                ('is_last_level', '=', True),
                            ], limit=1)
                        _logger.info("BUDGET WIZARD: eco_value found=%s", eco_value)
                        if eco_value:
                            vals['segment_value_id'] = eco_value.id
                            vals['value_code'] = eco_value.full_code or ''
                            vals['value_description'] = eco_value.name or ''
                        else:
                            # Account exists but no matching segment value
                            _logger.info("BUDGET WIZARD: NO MATCH for account %s", move_line.account_id.id)
                            vals['value_code'] = move_line.account_id.code or ''
                            vals['value_description'] = '%s %s' % (
                                move_line.account_id.code or '',
                                move_line.account_id.name or ''
                            )
                elif existing_combo:
                    existing_line = existing_combo.line_ids.filtered(
                        lambda l: l.segment_type_id.id == seg_type.id
                    )
                    if existing_line:
                        vals['segment_value_id'] = existing_line.segment_value_id.id
                        vals['value_code'] = existing_line.segment_value_id.full_code or ''
                        vals['value_description'] = existing_line.segment_value_id.name or ''
                lines.append((0, 0, vals))
            res['line_ids'] = lines
        return res

    def action_search(self):
        """Search for a matching code combination based on selected segments."""
        self.ensure_one()
        # Build segment map for ALL segments
        segment_values = {}
        for line in self.line_ids:
            if not line.segment_value_id:
                if line.is_economic:
                    raise UserError(
                        _("No matching economic segment value found for the account on this line. "
                          "Please create the account through Segment Values first.")
                    )
                raise UserError(
                    _("Please select a value for segment '%s'.") % line.segment_name
                )
            segment_values[line.segment_type_id.id] = line.segment_value_id.id

        # Search for exact match
        combo = self.env['budget.code.combination'].find_combination(segment_values)

        if combo:
            self.write({
                'combination_id': combo.id,
                'state': 'found',
                'message': _("Matching code combination found."),
            })
        else:
            auto_mode = self.env['ir.config_parameter'].sudo().get_param(
                'budget_segment.auto_create_combination', 'block'
            )
            if auto_mode == 'auto':
                combo_vals = {
                    'company_id': self.move_line_id.company_id.id,
                    'line_ids': [
                        (0, 0, {
                            'segment_type_id': line.segment_type_id.id,
                            'segment_value_id': line.segment_value_id.id,
                        })
                        for line in self.line_ids if line.segment_value_id
                    ],
                }
                combo = self.env['budget.code.combination'].create(combo_vals)
                self.write({
                    'combination_id': combo.id,
                    'state': 'found',
                    'message': _("New code combination created automatically."),
                })
            else:
                self.write({
                    'state': 'not_found',
                    'message': _("No matching code combination found. "
                                 "Auto-creation is disabled. Please create "
                                 "the combination first in Configuration > Code Combinations."),
                })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'budget.combination.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        """Assign the found combination to the journal item."""
        self.ensure_one()
        if self.combination_id and self.move_line_id:
            self.move_line_id.write({
                'budget_combination_id': self.combination_id.id,
            })
        return {'type': 'ir.actions.act_window_close'}

    def action_clear(self):
        """Clear the budget combination from the journal item."""
        self.ensure_one()
        if self.move_line_id:
            self.move_line_id.write({
                'budget_combination_id': False,
            })
        return {'type': 'ir.actions.act_window_close'}


class BudgetCombinationWizardLine(models.TransientModel):
    _name = 'budget.combination.wizard.line'
    _description = 'Budget Combination Wizard Line'
    _order = 'segment_sequence, id'

    wizard_id = fields.Many2one('budget.combination.wizard', string="Wizard",
                                required=True, ondelete='cascade')
    segment_type_id = fields.Many2one('budget.segment.type', string="Segment Type")
    segment_name = fields.Char(string="Segment")
    segment_sequence = fields.Integer(related='segment_type_id.sequence', store=True)
    is_economic = fields.Boolean(string="Is Economic", default=False)
    segment_value_id = fields.Many2one('budget.segment.value', string="Value",
                                       domain="[('segment_type_id', '=', segment_type_id), "
                                              "('is_last_level', '=', True)]")
    value_code = fields.Char(string="Code")
    value_description = fields.Char(string="Description")

    @api.onchange('segment_value_id')
    def _onchange_segment_value_id(self):
        if self.segment_value_id:
            self.value_code = self.segment_value_id.full_code or ''
            self.value_description = self.segment_value_id.name or ''
        elif not self.is_economic:
            self.value_code = ''
            self.value_description = ''
