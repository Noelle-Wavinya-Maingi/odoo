from odoo import models, fields

class OmnifreightSegments(models.Model):
    _name = 'omnifreight.segments'
    _description = 'Omnifreight Segments'
    
    name = fields.Char(string="Segment Name",  required=True, help="Customers who rely on Omnifreight’s knowledge and capabilities to ship to, from, and within Africa.")
    code = fields.Char(string="Segment Code", required=True)
    