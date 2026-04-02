# -*- coding: utf-8 -*-
{
    'name': "Omnifreight Quotation",
    'summary': "Manage quotations and shipments for Omnifreight",
    'description': """
    Omnifreight Quotation Module
    ----------------------------
    This module extends the functionality of the Sales module to include:
    - Omnifreight-specific quotations
    - Shipment management as a submenu under Omnifreight Quotation
    """,
    'author': "Your Company",
    'website': "https://www.yourcompany.com",
    'category': 'Sales',
    'version': '1.0.0',

    # Dependencies
    'depends': [
        'base',
        'sale',
        'contacts',
        'sale_management',
        # 'sale_subscription',
        # 'sale_mrp',
        'hr',  
        'mrp', 
    ],

    # Data files loaded at installation
    'data': [
        # Security access rules
        'security/ir.model.access.csv',

        # Menu and view definitions
        'views/omnifreight_quotation.xml',
        'views/menu.xml',
        'views/route_price_view.xml',
        'views/distance_ranges_view.xml',
        'views/un_subregions_views.xml',
        'views/omnifreight_carrier.xml',
        'views/omnifreight_package_details.xml',
        'views/port_view.xml',
        'views/haulier_region_view.xml',
        'views/route_days_view.xml',
        'views/transport_costs_view.xml',
        'views/known_price.xml',
        'views/res_partner_subregion_views.xml',
        'views/geographical_menu_actions.xml',
        'views/customer_routes.xml',
        'views/omnifreight_sale_tabs.xml',
        'views/omnifreight_service_sections.xml',
        'views/contacts_kanban_view.xml',
        'views/sale_order_known_price_form.xml',
        'views/sale_order_transport_rate.xml',
        'views/sale_order_lod_transport_rate.xml',
        'views/pricing-tab-view.xml',
        'views/omni_special_costs_view.xml',
        'views/hide_quotation_template.xml',
        'views/rename_views.xml',
        'views/omnifreight_shipment_route.xml',

        # Saved system data 
        'data/container_data.xml',
        'data/specialty_data.xml',
        'data/omnifreight_segments.xml',
        'data/omnifreight_segment_two.xml',
        'data/target_data.xml',
        'data/roles_data.xml',
        'data/subcategories.xml',
        'data/content.xml'
    ],

    # Demo data (optional, can be omitted if not needed)
    'demo': [
        'demo/demo.xml',
    ],

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
