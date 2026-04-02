from odoo import fields, models

class CarrierRegionsJoin(models.Model):
    # model name
    _name = 'carrier.regions.join'
    _description = 'Carrier Regions Join'

    # reference to the carrier model
    # carrier_id = fields.Many2one('omnifreight.carrier', string='Carrier', required=True)
    # reference to the haulier region model
    region_id = fields.Many2one('haulier.region', string='Region', required=True)
