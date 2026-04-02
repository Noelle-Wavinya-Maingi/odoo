from odoo import api, fields, models

class HaulierRegion(models.Model):
    _name = 'haulier.region'
    _description = 'Haulier Region'

    # Name of the haulier region
    name = fields.Char(compute="_compute_name", store=True)
    region_name = fields.Many2one('un.subregion', string="Region Name")

    # Transport Rates
    transport_ids = fields.One2many('omnifreight.transport.rates', 'haulier_region_ids', string='Transport Rates')
    
    @api.depends('region_name')
    def _compute_name(self):
        for record in self:
            record.name = record.region_name.name if record.region_name else False
