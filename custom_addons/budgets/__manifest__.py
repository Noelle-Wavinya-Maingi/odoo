# budgets/__manifest__.py
{
    'name': 'Budget Management',
    'summary': 'Shared, industry-agnostic budget line model for use by any business domain module.',
    'author': "Your Company",
    'website': "https://www.yourcompany.com",
    'category': 'Sales',
    'version': '1.0.0',
    'depends': ['base', 'mail', 'account', 'hr_expense'],
    'data': [
        
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3' 
}