from odoo import models, fields

class PortLabels(models.Model):
    # Model name
    _name = 'port.labels'
    _description = 'Port labels'
    
    # Name of the label
    name = fields.Char()
    