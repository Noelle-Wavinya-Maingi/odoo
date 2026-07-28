from odoo import models, fields, api


class FreightCarrier(models.Model):
    _inherit = 'res.partner'

    vessel_id = fields.Many2one('freight.vessel', string="Vessel")
