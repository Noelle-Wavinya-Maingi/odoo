from odoo import models, fields

class ContactRoles(models.Model):
    _name = 'contact.roles'
    _description = 'Contact roles'
    
    name = fields.Char()
    contact_id = fields.Many2one('res.partner', string='Contact', required=True)  # Added required=True
    role_id = fields.Many2one('omnifreight.roles', string='Role', required=True)  # Added required=True