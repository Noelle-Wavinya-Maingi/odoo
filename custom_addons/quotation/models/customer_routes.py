from odoo import models, fields, api

class CustomerRoutes(models.Model):
    _inherit = 'res.partner'
    #Routes the customer has shipped on before
    route_ids = fields.One2many(
        'omnifreight.route',
        'partner_id',
        string='Routes',
    )
    #names of routes, to be displayed
    route_names = fields.Char(
        string='Route Names',
        compute='_compute_route_names',
        store=True,
    )
    #Last time a customer had a successful sales order
    last_ordered_date = fields.Date(
        string="Last Ordered Date",
        compute="_compute_last_ordered_date",
        store=True,
    )
    #Check for last successful quotation with status sale 
    @api.depends('sale_order_ids.state', 'sale_order_ids.date_order')
    def _compute_last_ordered_date(self):
        for partner in self:
            # Filter confirmed sales orders (e.g., 'sale' or 'done' states)
            sale_orders = partner.sale_order_ids.filtered(
                lambda so: so.state in ['sale', 'done']
            )
            # Find the most recent order date
            partner.last_ordered_date = max(sale_orders.mapped('date_order')) if sale_orders else False

    #Get the name of a route
    #Check if a contact has a route, then display it
    @api.depends('route_ids.name')
    def _compute_route_names(self):
        for partner in self:
            partner.route_names = ', '.join(partner.route_ids.mapped('name'))
