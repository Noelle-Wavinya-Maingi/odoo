from odoo import models, fields

class Subcategory(models.Model):
    _name = 'subcategory'
    _description = 'Partner Subcategories'

    name = fields.Char(string="Subcategory", required=True)
    target = fields.Selection([
        ('target_1a', 'Standalone Merchants in Africa'),
        ('target_1b', 'SMEs Trading in/with Africa'),
        ('target_1c', 'Worldwide Freight Forwarders & Traders'),
        ('target_2a', 'SMEs Needing Logistics Services in Europe'),
        ('target_2b', 'Chinese Companies in Europe'),
        ('target_2c', 'Worldwide Freight Forwarders Needing Logistics in Europe')
    ], string="Target", required=True)
    color = fields.Integer(string="Color Index")