# -*- coding: utf-8 -*-
{
    'name': 'General Ledger',
    'version': '19.0.2.0.0',
    'category': 'Accounting',
    'summary': 'General Ledger with budget segments, payment consolidation, and BI dashboard',
    'description': """
        General Ledger module for Odoo 19:
        - Multi-segment budget code combinations (Organization, Fund Source, Economic, etc.)
        - Hierarchical segment values with Chart of Accounts integration
        - Organization management with inter-company payment consolidation
        - Payment submission workflow with approval integration (AME)
        - Trial Balance by Segment and by Code Combination
        - Embedded Metabase BI dashboard
    """,
    'author': 'dejenedev',
    'license': 'LGPL-3',
    'depends': ['account', 'ame_engine'],
    'data': [
        'data/metabase_defaults.xml',
        'security/ir.model.access.csv',
        'wizard/budget_combination_wizard_views.xml',
        'wizard/budget_payment_consolidation_views.xml',
        'views/budget_organization_views.xml',
        'views/budget_segment_type_views.xml',
        'views/budget_segment_value_views.xml',
        'views/budget_code_combination_views.xml',
        'views/account_account_views.xml',
        'views/budget_trial_balance_views.xml',
        'views/budget_trial_balance_combination_views.xml',
        'views/budget_consolidated_payment_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'general_ledger/static/src/js/metabase_action.js',
        ],
    },
    'installable': True,
    'application': True,
}
