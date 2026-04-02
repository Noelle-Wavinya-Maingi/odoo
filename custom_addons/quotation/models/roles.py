from odoo import models, fields

class Roles(models.Model):
    _name = 'omnifreight.roles'
    _description = 'Contacts roles'
    
    name = fields.Char(required=True)
    description = fields.Char()
    color = fields.Integer('Color Index')
    role_type = fields.Selection([
        ('client', 'Client'),
        ('logistics_supplier', 'Logistics Supplier'),
        ('general_supplier', 'General Supplier'),
        ('organization', 'Organization')
    ])