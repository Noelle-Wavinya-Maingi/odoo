from odoo import models, fields

class Supplier(models.Model):
    # Model name
    _name = 'supplier'
    _description = 'Supplier'
    
    # Name of supplier
    name = fields.Char()
    # Reference to specialty
    specialty_id = fields.Many2many('specialty', string='Specialty')
    