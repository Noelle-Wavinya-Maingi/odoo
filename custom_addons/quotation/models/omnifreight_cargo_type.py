from odoo import fields, models

class OmnifreightCargoType(models.Model):
    _name = 'omnifreight.cargo.type'
    _description = 'Omnifreight package details on the cargo type'
    
    name = fields.Char(string="Name")
    color = fields.Integer(string="Color Index")