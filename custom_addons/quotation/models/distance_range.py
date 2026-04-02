from odoo import fields, models

class DistanceRange(models.Model):
    # Model name
    _name = 'omnifreight.distance.range'
    _description = 'Distance Range'
    # Order the records by the minimum record
    _order = 'min_distance'

    # Name of the range
    name = fields.Char( string = 'Range Value' )
    # Minimum distance for the range
    min_distance = fields.Float(string='Minimum Distance (km)', required=True)
    # Maximum distance for the range
    max_distance = fields.Float(string='Maximum Distance (km)', required=True)
    # Fixed price for the distance range
    price = fields.Float(string='Fixed Price', required=True)
    # Currency for the fixed price
    currency_id = fields.Many2one(
    'res.currency', 
    string='Currency', 
    required=True, 
    default=lambda self: self.env.company.currency_id
)

    # Reference to the haulier region model
    haulier_region_id = fields.Many2one('haulier.region', string='Region')
    
    transport_rate = fields.Many2one('omnifreight.transport.rates')

    # SQL constraints to ensure that maximum distance is greater than minimum distance and the carrier, min_distance and max_distance are unique
    # _sql_constraints = [
    #     ('min_max_check', 'CHECK(max_distance > min_distance)', 'Maximum distance must be greater than minimum distance!'),
    #     ('range_unique', 'UNIQUE(haulier_region_id, min_distance, max_distance)', 'Distance range must be unique for this carrier!')
    # ]
    _min_max_check = models.Constraint('CHECK(max_distance > min_distance)', 'Maximum distance must be greater than minimum distance!')
    _range_unique = models.Constraint('UNIQUE(haulier_region_id, min_distance, max_distance)', 'Distance range must be unique for this carrier!')