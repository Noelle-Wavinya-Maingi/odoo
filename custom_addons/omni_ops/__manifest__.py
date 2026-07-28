# -*- coding: utf-8 -*-
{
    'name': "Accounting & Budgetting",

    'summary': "Custom module for accounting and budgetting",

    'description': """This module delivers custom freight handling functionality for Omnifreight.
        LIS functionality is extended upon and better shipment processing is implemented.
        Integrates freight operations with the manufacturing module for work order management.
    """,

    'author': "Elewa Company",
    'website': "https://www.elewa.ke",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Logistics',
    'version': '1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'product', 'mrp', 'quotation', 'account', 'hr_expense', 'operations', 'stock'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/field_renames.xml',
        'data/omni_mrp_budget_sequence.xml',
        'data/omni_mrp_production_sequence.xml',
        "views/rename_views.xml",
        'views/title_overrides.xml',
        'views/omni_service_template_views.xml',
        'views/omni_bom_views.xml',
        'views/omni_ops_layout.xml',
        'views/omni_mrp_production.xml',
        'views/omni_mrp_budget_views.xml',
        'views/omni_hr_expense_views.xml',
        'views/additional_file_operations_views.xml',
        'views/omnifreight-documents_view.xml',
        'views/omni_vessels_view.xml',
        'views/account_move_views.xml',
        'views/omni_bank_statement.xml',
    ],

    'application': True,
    'installable': True,
    'license': 'LGPL-3',

    # The expense-submitted decoration CSS is now provided generically by the
    # `operations` module (shared budget line UI), so no module-local asset is needed.
}

