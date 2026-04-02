from odoo import models, fields

class OmnifreightSegmentTwo(models.Model):
    _name = 'omnifreight.segment.two'
    _description = 'Omnifreight Segment Two'
    
    name = fields.Char(string="Segment Name",  required=True, help="Customers who rely on Omnifreight’s Antwerp location and European forwarding expertise.")
    code = fields.Char(string="Segment Code", required=True)
    