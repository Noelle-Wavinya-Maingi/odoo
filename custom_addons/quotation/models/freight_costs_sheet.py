from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)

class FreightCostsSheet(models.Model):
    _inherit = 'sale.order'

    # Special Costs linked to the sale order
    special_cost_ids = fields.One2many(
        'omnifreight.special.costs',
        'sales_order_id',
        string="Special Costs",
        domain=[('is_freight_cost', '=', True)],
        context={'default_is_freight_cost': True, 'default_is_route_cost': True, 'default_is_port_cost': False, 'default_is_soc_cost': False, 'default_is_fob_cost': False, 'default_is_lod_cost': False}
    )
    #Join relation to many 2 many known prices
    known_price_lines = fields.One2many('sale.order.known.price', 'sale_order_id', string="Carrier Freight Rates", domain=[('is_hidden', '=', False)])

    ##
    # CALCULATED FIELDS
    ##

    # A total of all freight costs, calculated from the known prices
    freight_costs = fields.Float(string="Freight Cost", compute="_compute_freight_costs", store=True)
    freight_costs_currency = fields.Many2one('res.currency', string="Freight Rate Currency", compute="_compute_freight_costs", store=True)
    # A total of all ecxtra costs in freight, such as port fees, customs, etc.
    misc_costs = fields.Integer(string="MISC", compute="_compute_misc_costs", store=True)
    # Margin on the freight costs, can be edited
    freight_margin = fields.Integer(string="Freight Margin (%)", default=0.0, help="Margin percentage applied to the freight costs.")
    # Value in figures of the mark-up
    total_freight_margin = fields.Float(string="Freight Margin", compute="_compute_estimated_total", store=True)
    # A calculated total cost of the freight, including margin and misc costs
    total_cost_est = fields.Float(string="Freight Total Incl. Margin", compute="_compute_estimated_total", store=True)
    #Actual quotation price, set by a user
    freight_price_set = fields.Integer(string='Quotation Price')
    #Total cost of freight and additional costs without margin
    freight_base_cost = fields.Float(string="Freight Total Cost", compute="_compute_estimated_total", store=True, help="Total cost of freight and additional costs.")
    # Route field based on the ports
    route_id = fields.Many2one('omnifreight.route', string="Freight Route", compute="_compute_route_id")

    # Historical Data and margins. This will be integrated with time
    historical_median = fields.Integer(string="Median Price", readonly=True)
    historical_best = fields.Integer(string="Best Price", readonly=True)
    margin_factor_ids = fields.One2many( 'omnifreight.margin.factor', 'sales_order_id', string="Margin Factors")
    selected_margin_factor = fields.Integer(string="Selected Margin Factor", compute="_compute_selected_margin", store=True)

    ###
    # THESE ARE FIELDS THAT ARE NOT USED BUT KEPT FOR DB SANITY
    # ##
    known_prices = fields.Many2many('known.price', 'sale_order_id')
    freight_carrier_id = fields.Many2one('res.partner', string='Carrier', compute='_compute_carrier_id', store=True)
    #####
    @api.depends('known_price_lines')
    def _compute_carrier_id(self):
        """Compute carrier_id from selected known price line."""
        for record in self:
            selected_rel = record.known_price_lines.filtered(lambda rel: rel.is_selected)
            if selected_rel and selected_rel[0].carrier_id:
                record.freight_carrier_id = selected_rel[0].carrier_id
            else:
                record.freight_carrier_id = False

    @api.depends('known_price_lines', 'content_classification', 'no_of_containers', 'soc')
    def _compute_freight_costs(self):
        for record in self:
            selected_rel = record.known_price_lines.filtered(lambda rel: rel.is_selected)
            price = 0.0

            if selected_rel:
                line = selected_rel[0]
                # Always start with the base price
                price = float(line.price or 0.0)
                # Add IMO surcharge if hazardous
                if record.content_classification == 'hazardous' and float(line.imo_surcharge_ft or 0.0):
                    price += float(line.imo_surcharge_ft or 0.0)
                # Add SOC tariff if SOC is true
                if record.soc and float(line.soc_tariff or 0.0):
                    price += float(line.soc_tariff or 0.0)
                record.freight_costs = price
                record.freight_costs_currency = line.currency_id or record.currency_id
                if len(selected_rel) > 1:
                    _logger.warning(f"Multiple known price lines selected: {[l.id for l in selected_rel]}")
            else:
                record.freight_costs = 0.0
                record.freight_costs_currency = record.currency_id

    @api.depends('special_cost_ids.price', 'special_cost_ids.currency_id', 'currency_id')
    def _compute_misc_costs(self):
        """Computes miscellaneous costs by combining special costs, converting each to quotation currency."""
        for record in self:
            total_misc_costs = 0.0
            for cost in record.special_cost_ids:
                cost_amount = float(cost.price or 0.0)
                if cost_amount > 0:
                    # Convert each special cost from its currency to quotation currency
                    if cost.currency_id and cost.currency_id != record.currency_id:
                        converted_amount = record.convert_rate_amount(
                            cost_amount, 
                            cost.currency_id
                        )
                    else:
                        converted_amount = cost_amount
                    total_misc_costs += converted_amount
            record.misc_costs = total_misc_costs


    @api.depends('freight_costs', 'misc_costs', 'freight_margin', 'no_of_containers', 
        'known_price_lines', 'currency_id')
    def _compute_estimated_total(self):
        for record in self:
            margin = 1.0 + (float(record.freight_margin or 0.0) / 100.0)
            
            # Get the currency from the selected known price
            selected_known_price = record.known_price_lines.filtered(lambda l: l.is_selected)

            if selected_known_price:
                rate_currency = selected_known_price.currency_id
                # Convert freight costs from rate currency to quotation currency
                converted_freight_costs = record.convert_rate_amount(
                    float(record.freight_costs or 0.0), 
                    rate_currency
                )
            else:
                converted_freight_costs = float(record.freight_costs or 0.0)
            
            # Calculate base total with converted freight costs
            base_total = (converted_freight_costs * float(record.no_of_containers or 1.0)) + float(record.misc_costs or 0.0)
            record.freight_base_cost = base_total
            
            record.total_cost_est = float(round(base_total * margin, 0))
            record.total_freight_margin = float(round(record.total_cost_est - base_total, 0))


    @api.depends('margin_factor_ids.margin_type')
    def _compute_selected_margin(self):
        """Computes the selected margin factor:
            - Prefers profile margin over country margin
            - Defaults to 1.0 if none are present
        """
        for order in self:
            selected_factor = order.margin_factor_ids.filtered(lambda mf: mf.margin_type)
            if selected_factor:
                factor = selected_factor[0]
                order.selected_margin_factor = factor.profile_margin if factor.margin_type == 'profile' else factor.country_margin
            else:
                order.selected_margin_factor = 1.0
                
    @api.depends('port_of_loading', 'port_of_dispatch')
    def _compute_route_id(self):
        """Compute the route based on the ports of loading and dispatch"""
        for record in self:
            record.route_id = record._get_current_route()

    @api.onchange('known_price_lines')
    def _onchange_known_price_selection(self):
        """Ensures only one price line is selected at a time and recomputes freight costs."""
        for order in self:
            selected = order.known_price_lines.filtered(lambda r: r.is_selected)
            if len(selected) > 1:
                for line in selected[1:]:
                    line.is_selected = False
            # Recompute freight costs based on selection
            order._compute_freight_costs()


    @api.onchange('container_type', 'port_of_dispatch', 'port_of_loading')
    def _onchange_ports_prices(self):
        """Auto-load known prices from a route if both ports are set."""
        for record in self:
            record.known_price_lines = [(5, 0, 0)]  # Clear previous lines
            if record.port_of_loading and record.port_of_dispatch:
                # First try to match exact direction
                route = self.env['omnifreight.route'].search([
                    ('departure_port_id', '=', record.port_of_loading.id),
                    ('arrival_port_id', '=', record.port_of_dispatch.id),
                ], limit=1)

                # If not found, try reverse direction
                if not route:
                    route = self.env['omnifreight.route'].search([
                        ('departure_port_id', '=', record.port_of_dispatch.id),
                        ('arrival_port_id', '=', record.port_of_loading.id),
                    ], limit=1)

                if route:
                    # Include both valid and expired rates that match the container type
                    matching_known_prices = route.known_prices_id.filtered(
                        lambda kp: kp.container_type == record.container_type
                    )
                    
                    # Apply filtering: one rate per company
                    from .rate_filtering_utils import filter_one_rate_per_company
                    filtered_prices = filter_one_rate_per_company(
                        matching_known_prices,
                        company_field='carrier_id',
                        valid_until_field='valid_until',
                        write_date_field='write_date'
                    )
                    
                    record.known_price_lines = [
                        (0, 0, {
                            'known_price_id': kp.id
                        }) for kp in filtered_prices
                    ]

    @api.onchange('freight_margin', 'freight_costs', 'misc_costs')
    def _onchange_recalculate_total(self):
        for record in self:
            record._compute_estimated_total()


    def _get_current_route(self):
        """Helper to fetch the route between current dispatch and loading ports."""
        self.ensure_one()
        if self.port_of_loading and self.port_of_dispatch:
            return self.env['omnifreight.route'].search([
                ('departure_port_id', '=', self.port_of_loading.id),
                ('arrival_port_id', '=', self.port_of_dispatch.id)
            ], limit=1)
        return None

    #  Override create to ensure known prices are linked on creation 
    # and add special cost presets        
    @api.model_create_multi
    def create(self, vals_list):
        records = super(FreightCostsSheet, self).create(vals_list)
        records._persist_new_known_prices()
        return records



    def write(self, vals):
        """Override write to ensure known prices are linked on save and clear freight costs when disabled."""
        if 'is_freight' in vals and not vals['is_freight']:
            # Clear all freight-related costs
            vals.update({
                'known_price_lines': [(5, 0, 0)],
                'special_cost_ids': [(5, 0, 0)],
                'freight_costs': 0.0,
                'misc_costs': 0,
                'freight_margin': 0.0,
                'total_freight_margin': 0.0,
                'total_cost_est': 0.0,
                'freight_base_cost': 0.0
            })
        res = super(FreightCostsSheet, self).write(vals)
        self._persist_new_known_prices()
        return res
    
    @api.model
    def copy_data(self, default=None):
        """Override copy_data to handle duplicating Freight-related lines when duplicating Sale Orders"""
    
        # Get the original copy data
        result = super().copy_data(default)
    
        if not result:
            return result
        
        # Handle both single record and multiple records
        if not isinstance(result, list):
            result = [result]
    
        records = self if len(result) == 1 else self
    
        for i, record_data in enumerate(result):
            record = records[i] if len(result) > 1 else records
        
            # Copy the known prices lines
            if record.known_price_lines:
                new_known_prices = []
                for rec in record.known_price_lines:
                    known_prices_val = rec.copy_data()[0]
                    # Remove the original sales order and known prices id to create a new record
                    if 'id' in known_prices_val:
                        del known_prices_val['id']
                    if 'sale_order_id' in known_prices_val:
                        del known_prices_val['sale_order_id']
                    new_known_prices.append((0, 0, known_prices_val))
                record_data['known_price_lines'] = new_known_prices
        
            # Copy Freight special costs
            if record.special_cost_ids:
                new_special_costs = []
                for cost in record.special_cost_ids:
                    cost_copy_vals = cost.copy_data()[0]
                    # Remove the original sales order and known prices id to create a new record
                    if 'id' in cost_copy_vals:
                        del cost_copy_vals['id']
                    if 'sales_order_id' in cost_copy_vals:
                        del cost_copy_vals['sales_order_id']
                    new_special_costs.append((0, 0, cost_copy_vals))
                record_data['special_cost_ids'] = new_special_costs
    
        return result[0] if len(result) == 1 else result
    
    @api.onchange('special_cost_ids')
    def _onchange_special_costs(self):
        """Ensure special costs are only shown for the current sale order."""
        for record in self:
            if record.special_cost_ids:
                record.special_cost_ids = record.special_cost_ids.filtered(lambda c: c.sales_order_id == record)

    @api.onchange('no_of_containers')
    def _compute_all_costs(self):
        for record in self:
            record._compute_estimated_total()            

    ###
    # Post a Known Price from the join table
    # Get the related fields and map them to the fields in the known prices table
    ##

    def _persist_new_known_prices(self):
        KnownPrice = self.env['known.price']
        for order in self:
            route = order._get_current_route()
            for line in order.known_price_lines:
                if not line.known_price_id:
                    if not line.container_type or not line.price or not line.carrier_id:
                        continue
                    vals = {
                        'route_id': route.id if route else None,
                        'price': line.price,
                        'carrier_id': line.carrier_id.id if line.carrier_id else False,
                        'valid_until': line.valid_until,
                        'transit_time': line.transit_time,
                        'container_type': line.container_type,
                        'departure_frequency': line.departure_frequency,
                        'imo_surcharge_ft': line.imo_surcharge_ft,
                        'notes': line.notes
                    }
                    line.known_price_id = KnownPrice._get_or_create_price(vals).id

    @api.onchange('is_freight')
    def _onchange_is_freight(self):
        for order in self:
            if not order.is_freight:
                has_freight_costs = bool(order.known_price_lines or order.special_cost_ids)
                if has_freight_costs:
                    return {
                        'warning': {
                            'title': 'Disable Freight?',
                            'message': 'You are about to disable Freight. This will clear all freight costs when you save. If not, re-select the service',
                            'type': 'dialog',
                            'sticky': True,
                            'buttons': [
                                {
                                    'text': 'Cancel',
                                    'primary': False,
                                    'click': 'function() { this.trigger_up("cancel"); }'
                                },
                                {
                                    'text': 'Continue',
                                    'primary': True,
                                    'click': 'function() { this.trigger_up("confirm"); }'
                                }
                            ]
                        }
                    }
            elif order.is_freight and order.port_of_loading and order.port_of_dispatch:
                # Reload known prices when re-enabling freight
                order._onchange_ports_prices()


