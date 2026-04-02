from odoo import models, fields, api
# from .route_price_logic import compute_land_route_rate

class RoutePrice(models.Model):
    # Model name
    _name = 'route.price'
    _description = 'Route Price'

    # Reference to the route for which the price is being calculated
    route_id = fields.Many2one(
        'omnifreight.route', string='Route', required=True)
    # Document fees associated with the route  price
    document_fees = fields.Integer()
    # Margin fee applied to the route price
    margin_fee = fields.Integer()
    # Reference to the port associated with the route
    port_id = fields.Many2one('port', string='Port')
    # Reference to the carrier in the route
    # carrier_id = fields.Many2one('omnifreight.carrier', string='Carrier')
    # Package associated with the route
    package_id = fields.Many2one('omnifreight.package.details', string='Package')
    # Total land route rate computed based on various fields
    total_rate = fields.Integer(
         string='Total Land Route Rate', store=True)
    # Haulier region associated with the route
    haulier_region_id = fields.Many2one('haulier.region', string='Haulier Region')

    # Compute the total land route rate when relevant fields change
    # @api.depends('document_fees', 'margin_fee', 'port_id', 'carrier_id', 'route_id', 'haulier_region_id')
    # def _compute_land_route_rate(self):
    #     for record in self:
    #         record.total_rate = compute_land_route_rate(record)
