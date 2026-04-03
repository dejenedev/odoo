# -*- coding: utf-8 -*-
{
    'name': 'Budget Segment Code Combination',
    'version': '19.0.1.3.0',
    'category': 'Accounting/Budget',
    'summary': 'Multi-segment budget code combination for chart of accounts',
    'description': """
        Define configurable budget segments (Organization, Geographic, Program,
        Project, Fund Source, Economic, Counterparty, etc.) with hierarchical
        values, and create code combinations for budget tracking on transactions.
    """,
    'author': 'dejenedev',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/budget_combination_wizard_views.xml',
        'wizard/budget_payment_consolidation_views.xml',
        'views/budget_organization_views.xml',
        'views/budget_segment_type_views.xml',
        'views/budget_segment_value_views.xml',
        'views/budget_code_combination_views.xml',
        'views/account_account_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
