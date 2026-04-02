from odoo import models, fields

class Target(models.Model):
    _name = 'target'
    _description = 'Partner Targets'
    
    name = fields.Char(string="Target", required=True)
    segment = fields.Selection([
        ('segment_1', 'Trade with Africa'),
        ('segment_2', 'Geographical Position in Antwerp, Europe'),
        ('segment_3', 'Trade With Africa & Geographical Position in Antwerp, Europe')
    ], string="Segment", required=True)