# -*- coding: utf-8 -*-
{
    'name': "Trading",
    'summary': "Manage trading operations and related processes",
    'description': """
    Trading Module
    This module provides comprehensive features for managing trading operations, including:
    - Trade management: Create and manage trade records, including details such as trade type, products involved, quantities, and values.
    - Partner management: Manage trading partners, including suppliers and customers, with detailed contact information and trade history.
    - Trade documentation: Generate and manage trade-related documents such as invoices, delivery notes, and contracts.
    - Reporting and analytics: Access detailed reports and analytics on trading activities, including trade performance, partner analysis, and financial insights.
    """,
    'author': "Your Company",
    'website': "https://www.yourcompany.com",
    'category': 'Sales',
    'version': '1.0.0',

    # Dependencies
    'depends': [
        'base', 'stock', 'sale', 'purchase', 'operations', 'hr_expense'
    ],

    # Data files loaded at installation
    'data': [
        'security/ir.model.access.csv',

        'data/sequence.xml',

        'views/trading_trade_views.xml',
        # 'views/trading_trade_budget_views.xml',
        'views/menu.xml',
        'views/trading_futures_views.xml',
        'views/purchase_order.xml',
        'views/stock_views.xml',
        'views/sale_view.xml',
        'views/account_move_line_view.xml',
        'views/product_template.xml',
        # 'views/hr_expense_views.xml',
        'views/res_config_settings_view.xml',
    ],

    # Demo data (optional, can be omitted if not needed)
    # 'demo': [
    #     'demo/demo.xml',
    # ],

    # 'assets': {
    #     'web.assets_backend': [
    #         'omni_quotation/static/src/css/omnifreight_custom_css.scss',
    #     ],
    # },
    # 'post_init_hook': 'set_default_container_type',

    # Installation settings
    'installable': True,
    'application': True,
    'license': 'LGPL-3'
}