from odoo import fields, models

class OmnifreightPackageDetails(models.Model):
    _name = "omnifreight.package.details"
    _description = "Details on the consignment being shipped"

    CONTAINER_TYPES = [
        ('20dv', "20' DV"),
        ('40dv', "40' DV"),
        ('40hc', "40' HC"),
        ('20ot', "20' OT"),
        ('40ot', "40' OT"),
        ('40hc_ot', "40' HC OT"),
        ('20rf', "20' RF"),
        ('40hrf', "40' HRF"),
        ('20fl', "20' FL"),
        ('40fl', "40' FL"),
        ('20_iso_tank', "20' ISO TANK"),
        ('40_iso_tank', "40' ISO TANK"),
    ]

    CONTENT_CLASSIFICATION = [
        ('hazardous', 'Hazardous contents'),
        ('temperature', 'Temperature controlled'),
    ]

    container_type = fields.Selection(CONTAINER_TYPES, string="Container Size", required=True)
    contents = fields.Many2many(
        'omnifreight.cargo.type',
        'omnifreight_package_cargo_rel',
        'package_id',
        'cargo_id',
        string="Contents"
    )
    content_classification = fields.Selection(CONTENT_CLASSIFICATION, string="Content Classification")
    soc = fields.Boolean(string="SOC (Shipper Owned Container)")
    weight = fields.Float(string="Weight")
    volume = fields.Float(string="Volume")
    weight_uom_id = fields.Many2one('uom.uom', string="Weight Unit of Measure")
    volume_uom_id = fields.Many2one('uom.uom', string="Volume Unit of Measure")
    

