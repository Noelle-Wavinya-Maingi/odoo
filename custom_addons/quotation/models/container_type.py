from odoo import models, fields

class ContainerType(models.Model):
    _name = 'container.type'
    _description = 'Container Type'
    
    name = fields.Char(string='Container Type')
    code = fields.Char()