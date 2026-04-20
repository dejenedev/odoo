# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    budget_auto_create_combination = fields.Selection(
        [('block', 'Block - Only allow existing combinations'),
         ('auto', 'Auto-create - Create new combination if not found')],
        string="Budget Code Combination Mode",
        default='block',
        config_parameter='general_ledger.auto_create_combination',
        help="Controls what happens when a user selects segments that don't match "
             "any existing code combination.\n"
             "Block: Show a warning and do not assign.\n"
             "Auto-create: Automatically create the new combination."
    )
    metabase_url = fields.Char(
        string="Metabase URL",
        config_parameter='general_ledger.metabase_url',
        default='http://localhost:3000',
        help="Base URL of the Metabase instance (e.g. http://localhost:3000).")
    metabase_dashboard_id = fields.Char(
        string="Dashboard Public UUID",
        config_parameter='general_ledger.metabase_dashboard_id',
        help="Public UUID of the Metabase dashboard to embed in Odoo.")
