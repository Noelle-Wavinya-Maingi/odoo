# -*- coding: utf-8 -*-
{
    'name': "Operations",
    'summary': "Multi industry operations management module",
    'description': """
    Operations Module
    -----------------
    This module provides operations management capabilities for multiple industries.
    It includes features for managing operations across different sectors and industries.

    """,
    'author': "Your Company",
    'website': "https://www.yourcompany.com",
    'category': 'Sales',
    'version': '1.0.0',

    # Dependencies
    'depends': [
        'base', 'mail', 'account', 'hr_expense'

    ],
    'assets': {
        'web.assets_backend': [
            'operations/static/src/js/settings_patch.js',
            'operations/static/src/css/settings.css',
            'operations/static/src/css/budget_decoration.css',
        ],
    },

    # Data files loaded at installation
    'data': [
        # Security access rules
        'security/ir.model.access.csv',
        
        'views/settings_view.xml',
    ],

    # Demo data (optional, can be omitted if not needed)
    'demo': [
    ],

   
    # 'post_init_hook': 'set_default_container_type',
    
    # Installation settings
    'installable': True,
    'application': True,
    'license': 'LGPL-3'
}
