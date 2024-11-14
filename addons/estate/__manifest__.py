# /home/$USER/src/tutorials/estate/__manifest__.py

{
    'name': 'Estate',
    'version': '1.0',
    'category': 'Real Estate',
    'summary': 'A module to manage real estate properties',
    'description': """
        Estate Module
        ==================
        This module is designed to help manage real estate properties,
        including listings, client management, and more.
    """,
    'author': 'Noelle Maingi',
    'depends': ['base'],  
    'data': [
        'security/ir.model.access.csv',
        'views/estate_property_views.xml',
        'views/estate_menus.xml'
        ],
    'installable': True,
    'application': True,
}
