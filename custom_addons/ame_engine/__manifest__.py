# -*- coding: utf-8 -*-
{
    'name': 'Approval Management Engine (AME)',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Rule-based approval workflow engine inspired by Oracle AME',
    'description': """
        Centralized approval management engine for Odoo:
        - Configurable transaction types, attributes, conditions, and rules
        - Dynamic approver resolution (hierarchy, groups, specific users, Python)
        - Serial, parallel, and hybrid approval flow patterns
        - Runtime approval tracking with full audit trail
        - Delegation, substitution, and escalation
        - Mixin for any Odoo model to integrate
        - Chatter, email notifications, and activity scheduling
    """,
    'author': 'dejenedev',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ame_security.xml',
        'security/ir.model.access.csv',
        'data/ame_activity_type_data.xml',
        'data/ame_cron_data.xml',
        'wizard/ame_approve_wizard_views.xml',
        'wizard/ame_delegate_wizard_views.xml',
        'views/ame_transaction_type_views.xml',
        'views/ame_attribute_views.xml',
        'views/ame_condition_views.xml',
        'views/ame_rule_views.xml',
        'views/ame_approver_action_views.xml',
        'views/ame_approval_group_views.xml',
        'views/ame_approval_instance_views.xml',
        'views/ame_delegation_views.xml',
        'views/ame_substitution_views.xml',
        'views/ame_dashboard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
