from odoo import models, fields

class ContainerSize(models.Model):
    _name = 'container.size'
    _description = 'Container Size'
    
    name = fields.Char(string='Name')
    code = fields.Char()
    container_type_id = fields.Many2one('container.type', string="Container Type")