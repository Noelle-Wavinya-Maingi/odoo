from odoo import models, fields

class Specialty(models.Model):
    # Model Name
    _name = 'specialty'
    _description = 'Specialty'
    
    # Name of specialty
    name = fields.Char(required = True)
    description = fields.Text()