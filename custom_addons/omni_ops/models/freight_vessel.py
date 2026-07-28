from odoo import fields, models

class FreightVessel(models.Model):
    _name = "freight.vessel"
    _description = "Freight Vessel"

    name = fields.Char(string="Vessel Name")
    imo_number = fields.Char(string="IMO Number")
    flag = fields.Char(string="Flag")
    year_built = fields.Char(string="Year Built")
    length = fields.Float(string="Length")
    width = fields.Float(string="Width")
    depth = fields.Float(string="Depth")
    freight_carrier_id = fields.Many2one('res.partner', string="Carrier", domain="[('is_company', '=', True), ('company_category', '=', 'supplier')]")
