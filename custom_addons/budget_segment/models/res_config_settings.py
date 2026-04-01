# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    budget_auto_create_combination = fields.Selection(
        [('block', 'Block - Only allow existing combinations'),
         ('auto', 'Auto-create - Create new combination if not found')],
        string="Budget Code Combination Mode",
        default='block',
        config_parameter='budget_segment.auto_create_combination',
        help="Controls what happens when a user selects segments that don't match "
             "any existing code combination.\n"
             "Block: Show a warning and do not assign.\n"
             "Auto-create: Automatically create the new combination."
    )
