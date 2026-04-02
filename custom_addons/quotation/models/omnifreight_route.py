from odoo import models, fields, api

from .route_logic import compute_write_date_only, compute_name, check_ports


class OmnifreightRoute(models.Model):
    # Model name
    _name = 'omnifreight.route'
    _description = 'Route'

    # Name of the route
    name = fields.Char(compute="_compute_name", store=True)
    # Reference to the port model for the departute and the arrival port
    departure_port_id = fields.Many2one('port', string='Port of Loading')
    arrival_port_id = fields.Many2one('port', string='Port of Destination')
    # Last updated date for the route
    last_updated = fields.Date(compute='_last_updated')
    # Show existing carriers first, and allow new carrier creation
    known_prices_id = fields.One2many(
        'known.price', 
        'route_id',
        string='Known Prices',
    )  
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Quotation',
        ondelete='cascade',
    )
    #Linking a route to a customer
    partner_id = fields.Many2one(
        'res.partner',  # Link to the customer
        string='Customer',
        related='sale_order_id.partner_id',  # Automatically set based on the linked quotation
        store=True,
    )

    # Ensure no duplication of routes 
    # _sql_constraints = [
    #     ('unique_route', 'unique(departure_port_id, arrival_port_id)', 'A route between these ports already exists!')
    # ] 
    _unique_route = models.Constraint('unique(departure_port_id, arrival_port_id)', 'A route between these ports already exists!')
    
    @api.depends('departure_port_id', 'arrival_port_id', 'last_updated')
    # Compute method for the name of the routes
    def _compute_name(self):
        compute_name(self)
    
    @api.depends('last_updated')
    def _last_updated(self):
        compute_write_date_only(self)
                
    @api.constrains('departure_port_id', 'arrival_port_id')
    # Compute method to validate that POD and POL do not match
    def _check_ports(self):
        check_ports(self)
        
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to add debugging"""
        routes = super().create(vals_list)
        return routes
        
    def unlink(self):
        """Override unlink to add debugging"""
        return super().unlink()
        
   

