from odoo import fields, models, api
from .route_price_logic import RoutePriceLogic
from .currency_conversion_mixin import OmniCurrencyConversion

from odoo.exceptions import ValidationError

class OmnifreightLod(models.Model):
    _inherit = 'sale.order'

    # Service Details - Local at Destination
    lod_service_street = fields.Char(string="LOD Street")
    lod_service_po_box = fields.Char()
    # City for the LOD service; the domain filters cities by the selected LOD country.
    lod_service_city = fields.Many2one('unloc.city', domain="[('country_id', '=?', lod_service_country_id)]")
    lod_service_zip = fields.Char(string="LOD ZIP Code")
    lod_service_zip_code_id = fields.Many2one(
        'unloc.city.zip', 
        domain="[('un_city_id', '=', lod_service_city)]",
        context= {
            'create': True,
            'no_open': True,
            'default_un_city_id': lod_service_city
        }
    )
    # Custom country model for LOD service.
    lod_service_country_id = fields.Many2one('unloc.country', string="LOD Country")
    # Compute field for the delivery region set by either city or country.
    delivery_region = fields.Char(string='Delivery Region', compute="_compute_delivery_region", store=True)
    expected_arrival = fields.Date(string="Expected Delivery")
    
    # Relational field for the special costs 
    lod_special_costs_id = fields.One2many('omnifreight.special.costs', 'sales_order_id', string="Special Costs(lod)", 
                                           domain=[('is_lod_cost', '=', True)], context={'default_is_lod_cost': True, 'default_is_port_cost': True, 'default_is_fob_cost': False, 'default_is_freight_cost': False, 'default_is_soc_cost': False})

    # Transport rates and LOD fields
    lod_rate_link_ids = fields.One2many('sale.order.lod.transport.rate', 'order_id', copy=False, domain=[('is_hidden', '=', False)])
    filtered_lod_rate_link_ids = fields.One2many('sale.order.lod.transport.rate', 'order_id', 
                                                string="Filtered LOD Transport Rates")
    selected_lod_transport_rate_id = fields.Many2one('omnifreight.transport.rates', string="Selected LOD Transport Rate",
        compute="_compute_selected_lod_transport_rate", store=True)
    lod_transport_rate_total = fields.Integer(string="LOD Transport Rate Total", compute="_compute_lod_transport_rate_total", store=True)

    # Selected haulier cost for LOD (derived from the transport rates).
    lod_selected_haulage = fields.Float(string="lod Selected Haulier", compute="_compute_lod_selected_haulier", store=True)
    lod_selected_haulage_currency = fields.Many2one('res.currency', string="LOD Rate Currency", compute="_compute_lod_selected_haulier", store=True)
    
    lod_risk_percentage = fields.Integer(string="LAD Margin (%)", default = 0.0, help="Margin percentage applied to the destination costs.")
    
    # Computed estimated total LOD cost based on misc costs and selected haulier.
    lod_total_cost_est = fields.Float(string="DAP Total Incl. Margin", compute="_compute_lod_total_cost_est")
    
    # Computed miscellaneous cost for LOD derived from special costs.
    lod_misc_cost = fields.Integer(string="lod Extra Costs", compute="_compute_lod_misc_costs")
    # Computed total cost for LOD, including transport and miscellaneous costs.
    lod_total_cost = fields.Float(string="DAP Total Cost", compute="_compute_lod_total_cost_est", help="Total cost for DAP, including transport and miscellaneous costs.")
    # Computed margin for the LOD total cost.
    lod_total_margin = fields.Float(string="LOD Margin", compute="_compute_lod_total_cost_est")
    # Destination transporter rate costs plus misc costs
    
    # LOD transport rates (Many2many relation with transport rates for LOD)
    lod_transport_rates = fields.Many2many(
        'omnifreight.transport.rates',
        'sale_order_lod_transport_rates_rel',
        'order_id',
        'rate_id', 
        string="Transport rates(LOD)"
        )
    
    # LOD distance used to compute transport rate.
    lod_distance = fields.Integer(string='LOD Distance')
    
    # ----------------------------
    # Constraints
    # ----------------------------
    
    @api.depends('selected_lad_transport_rate_id', 'transport_rates.selected_for_sale_orders', 'transport_rates.is_selected_lod')
    def _compute_selected_lad_transport_rate(self):
        """Computes the selected transport rate for this sale order."""
        for order in self:
            selected_rate = self.env['omnifreight.transport.rates'].search([
                ('selected_for_sale_orders', 'in', [order.id])
            ], limit=1)
            order.selected_lad_transport_rate_id = selected_rate.id if selected_rate else False
    
    # ----------------------------
    # Compute Methods
    # ----------------------------
    @api.depends('lod_service_country_id', 'lod_service_country_id.subregion_id', 'lod_service_city', 'lod_service_city.country_id', 'lod_service_city.country_id.subregion_id')
    def _compute_delivery_region(self):
        """
        Compute the delivery region:
        - If a city is provided and its country's subregion exists, use that.
        - Otherwise, if only a LOD country is provided and it has a subregion, use that.
        - If neither, set delivery_region to False.
        """
        for record in self:
            if record.lod_service_city and record.lod_service_city.country_id and record.lod_service_city.country_id.subregion_id:
                record.delivery_region = record.lod_service_city.country_id.subregion_id.name
            elif record.lod_service_country_id and record.lod_service_country_id.subregion_id:
                record.delivery_region = record.lod_service_country_id.subregion_id.name
            else:
                record.delivery_region = False


    @api.depends('lod_special_costs_id', 'lod_special_costs_id.price', 'lod_special_costs_id.currency_id', 'currency_id')
    def _compute_lod_misc_costs(self):
        """
        Compute the miscellaneous LOD cost as the sum of all linked special cost prices,
        converting each to quotation currency.
        """
        for record in self:
            total_lod_misc_cost = 0.0
            for cost in record.lod_special_costs_id:
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
                    total_lod_misc_cost += converted_amount
            record.lod_misc_cost = total_lod_misc_cost
    
    @api.depends('lod_rate_link_ids', 'lod_rate_link_ids.lod_total', 'lod_rate_link_ids.currency_id', 'currency_id')
    def _compute_lod_selected_haulier(self):
        """
        Compute the selected haulier for LOD:
        - Filters LOD transport rates marked as selected.
        - Stores original value for display. Conversion happens in totals computation.
        """
        for record in self:
            selected_rate = record.lod_rate_link_ids.filtered(lambda link: link.is_selected_lod)
            if len(selected_rate) == 1:
                # Store original value for display (conversion happens in totals)
                record.lod_selected_haulage = selected_rate.lod_total or 0.0
                record.lod_selected_haulage_currency = selected_rate.currency_id or record.currency_id
            else:
                record.lod_selected_haulage = 0.0
                record.lod_selected_haulage_currency = record.currency_id
    
    @api.onchange("lod_risk_percentage")
    def _onchange_lod_risk_percentage(self):
        for record in self:
            record._compute_lod_total_cost_est()
            
    @api.depends('lod_misc_cost', 'lod_total_cost_est', 'lod_rate_link_ids.is_selected_lod', 'lod_risk_percentage', 'no_of_containers', 'soc',
     'selected_lod_transport_rate_id.soc_tariff', 'selected_lod_transport_rate_id.currency_id', 'currency_id')
    def _compute_lod_total_cost_est(self):
        """
        Compute the estimated total LOD cost:
        - Sum the miscellaneous LOD cost and the selected haulier cost.
        - If SOC is true, add soc_tariff from the selected LOD transport rate.
        - Apply the risk percentage to compute a final estimated cost.
        - Compute the margin for the LOD total cost.
        """
        for record in self:
            margin = 1 + (record.lod_risk_percentage / 100)
            
            # Convert haulier cost from rate currency to quotation currency
            if record.selected_lod_transport_rate_id:
                converted_haulier_cost = record.convert_rate_amount(
                    record.lod_selected_haulage, 
                    record.selected_lod_transport_rate_id.currency_id
                )
            else:
                converted_haulier_cost = record.lod_selected_haulage
                
            haulier_total = converted_haulier_cost * record.no_of_containers
            base_total = record.lod_misc_cost + haulier_total

            record.lod_total_cost = base_total
            record.lod_total_cost_est = round(base_total * margin, 0)
            record.lod_total_margin = round(record.lod_total_cost_est - base_total, 0)
            
            
    @api.onchange('lod_service_country_id', 'lod_service_city')
    def _onchange_country_field(self):
        """
        This method ensures the city and country provided are related.
        """
        for record in self:
            if record.lod_service_country_id:
                if record.lod_service_city.country_id != record.lod_service_country_id:
                    record.lod_service_city = False
                    
    @api.onchange('lod_transport_rates')
    def _onchange_lod_transport_rates(self):
        """
        Ensures that only one LOD transport rate is selected at a time.
        When multiple rates are selected, it deselects all others, keeping only the one with the most recent update.
        """
        for order in self:
            # Get the known prices records that are marked as selected.
            selected_rates = order.lod_transport_rates.filtered(lambda r: r.is_selected_lod)
            if len(selected_rates) > 1:
                # Identify the newly selected price by comparing with its _origin value.
                # If a record is new or its _origin had is_selected==False, it's the one recently toggled.
                newly_selected = selected_rates.filtered(lambda p: not p._origin or not p._origin.is_selected_lod)
                if newly_selected:
                    most_recent = newly_selected[0]
                else:
                    # If no record appears as newly selected, keep the first one.
                    most_recent = selected_rates[0]
            
            
                # Deselect all other prices.
                for price in selected_rates:
                    if price != most_recent:
                        price.is_selected_lod = False
                        
    @api.onchange('lod_service_city')
    def _onchange_lod_city(self):
        if self.lod_service_city:
            self.lod_service_country_id = self.lod_service_city.country_id
    
    @api.onchange('lod_service_country_id', 'lod_service_city')
    def _onchange_lod_country_city_field(self):
        """
        This method ensures the city and country provided are related.
        """
        for record in self:
            if record.lod_service_country_id:
                if record.lod_service_city.country_id != record.lod_service_country_id:
                    record.lod_service_city = False
            elif not record.lod_service_country_id:
                record.lod_service_city = False  
    
    @api.onchange('lod_service_zip_code_id')
    def _onchange_lod_zip_code_set_city(self):
        """
        When the zip code changes, set the city to the zip's city.
        """
        for record in self:
            if record.lod_service_zip_code_id:
                record.lod_service_city = record.lod_service_zip_code_id.un_city_id
                
    @api.onchange('lod_service_city')
    def _onchange_lod_city_set_country_clear_zip(self):
        """
        When the city changes, set the country to the city's country and clear the zip code.
        """
        for record in self:
            if record.lod_service_city:
                record.lod_service_country_id = record.lod_service_city.country_id
            if record.lod_service_zip_code_id.un_city_id != record.lod_service_city:
                record.lod_service_zip_code_id = False
    
    @api.onchange('lod_rate_link_ids')
    def _onchange_rate_link_selected_lod(self):
        """Ensure only one LOD transport rate is selected at a time."""
        for order in self:
            selected_lod_links = order.lod_rate_link_ids.filtered('is_selected_lod')
            if len(selected_lod_links) > 1:
                last_lod = selected_lod_links[-1]
                for link in selected_lod_links:
                    if link != last_lod:
                        link.is_selected_lod = False
            order._compute_lod_selected_haulier()
            
    @api.onchange('is_lod')
    def _onchange_is_lod(self):
        for order in self:
            if not order.is_lod:
                has_lod_costs = bool(order.lod_rate_link_ids or order.lod_special_costs_id)
                if has_lod_costs:
                     # If the user continues (e.g. saves again), clear the lines
                    order.lod_rate_link_ids = [(5, 0, 0)]
                    order.lod_special_costs_id = [(5, 0, 0)]
                    return {
                        'warning': {
                            'title': 'Disabling Local At Destination',
                            'message': 'You are disabling Local At Destination, but there are still LAD costs present. If you continue, all LAD costs will be removed.'
                        }
                    }
    
    @api.onchange('container_type')
    def _onchange_container_type_clear_lod_rates(self):
        """Clear LOD rates when container type changes."""
        for order in self:
            if order.is_lod and order.lod_rate_link_ids:
                # Clear all LOD rate links when container type changes
                order.lod_rate_link_ids = [(5, 0, 0)]
                order.lod_transport_rates = [(5, 0, 0)]
    
    @api.onchange('lod_service_country_id', 'lod_service_city', 'port_of_dispatch', 'container_type')
    def _onchange_lod_location_fields(self):
        """
        Fetch existing transport rates for the matching region, city, and port.
        Handles both 'scaffold' and 'city' rate types.
        Prevents duplication by only adding rate links that don't already exist and
        clears links that no longer match the current location.
        """
        for order in self:
            if not order.is_lod:
                return

            if not (order.lod_service_country_id and order.port_of_dispatch):
                return

            subregion = order.lod_service_country_id.subregion_id
            if not subregion:
                return

            region = self.env['haulier.region'].search([
                ('name', '=ilike', subregion.name.strip())
            ], limit=1)
            if not region:
                return

            # Build domain to find matching rates
            domain = [
                ('haulier_region_ids', '=', region.id),
                ('transport_port', '=', order.port_of_dispatch.id),
                ('container_type', '=', order.container_type),
            ]

            if order.lod_service_city:
                domain += ['|',
                        ('rate_type', '=', 'scaffold'),
                        '&', ('rate_type', '=', 'city'),
                                ('transport_city', '=', order.lod_service_city.id)]
            else:
                domain.append(('rate_type', '=', 'scaffold'))

            rates = self.env['omnifreight.transport.rates'].search(domain)
            
            # Apply filtering: one rate per company
            from .rate_filtering_utils import filter_one_rate_per_company
            filtered_rates = filter_one_rate_per_company(
                rates,
                company_field='supplier_id',
                valid_until_field='valid_until',
                write_date_field='write_date'
            )
            
            order.lod_transport_rates = [(6, 0, filtered_rates.ids)]

            new_links = []
            for rate in filtered_rates:
                new_links.append((0, 0, {
                    'rate_id': rate.id,
                    'transport_city': rate.transport_city.id if rate.transport_city else False,
                    'transport_port': rate.transport_port.id if rate.transport_port else False,
                    'haulier_region_ids': region.id,
                }))
            
            order.lod_rate_link_ids = [(5, 0, 0)] + new_links

            self.env['omnifreight.transport.rates'].with_context(
                active_id=order.id,
                active_model='sale.order',
                active_view='lod'
            ).force_recompute_from_sale_order(order.id)

            if order.lod_rate_link_ids:
                order.lod_rate_link_ids._compute_lod_total()


    @api.depends('lod_rate_link_ids', 'lod_rate_link_ids.is_selected_lod')
    def _compute_selected_lod_transport_rate(self):
        """Compute the selected LOD transport rate based on the selected rate link."""
        for order in self:
            selected_rate = order.lod_rate_link_ids.filtered(lambda r: r.is_selected_lod)
            order.selected_lod_transport_rate_id = selected_rate.rate_id if selected_rate else False

    @api.depends('selected_lod_transport_rate_id', 'selected_lod_transport_rate_id.lod_total', 'no_of_containers')
    def _compute_lod_transport_rate_total(self):
        """Compute the total LOD transport rate cost."""
        for order in self:
            order.lod_transport_rate_total = order.selected_lod_transport_rate_id.lod_total * order.no_of_containers  if order.selected_lod_transport_rate_id else 0.0

    @api.onchange('no_of_containers')
    def _compute_all_costs(self):
        for record in self:
            record._compute_lod_transport_rate_total()   

    ##
    # DB CALLS AND OVERIDES
    ##

    def write(self, vals):
        res = super(OmnifreightLod, self).write(vals)
        
        # If the city is updated, force recomputation on related transport rates.
        if 'lod_service_city' in vals:
            self.env['omnifreight.transport.rates'].with_context(
            active_id=self.id,  # Pass the current sale order ID
            active_model='sale.order'  # Pass the current model
        ).force_recompute_from_sale_order(self.id)
         # If any of these fields are updated, update the context for rate creation
        if any(field in vals for field in ['lod_service_city', 'port_of_dispatch', 'delivery_region']):
            # Update context for transport rates
            for record in self:
                context = {
                    'default_transport_city': record.lod_service_city.id if record.lod_service_city else False,
                    'default_transport_port': record.port_of_dispatch.id if record.port_of_dispatch else False, 
                    'default_region_name': record.delivery_region,
                    'active_id': record.id,
                    'active_model': 'sale.order'
                }
                # This will be used when creating new transport rates
                record.with_context(**context)
                
                # Update existing rate_link_ids with new city/port values if needed
                if record.lod_rate_link_ids:
                    for rate_link in record.lod_rate_link_ids:
                        if not rate_link.transport_city and record.lod_service_city:
                            rate_link.transport_city = record.lod_service_city.id
                        if not rate_link.transport_port and record.port_of_dispatch:
                            rate_link.transport_port = record.port_of_dispatch.id
                        if not rate_link.region_name and record.delivery_region:
                            rate_link.region_name = record.delivery_region
                            
            # Update existing fob_special_costs when port_of_loading or container_type changes
            if 'port_of_dispatch' in vals or 'container_type' in vals:
                for record in self:
                    if record.lod_special_costs_id:
                        # Update existing special costs that don't have these values set
                        for cost in record.lod_special_costs_id:
                            if 'port_of_dispatch' in vals and not cost.port_id and record.port_of_dispatch:
                                cost.port_id = record.port_of_dispatch.id
                            if 'container_type' in vals and not cost.container_type and record.container_type:
                                cost.container_type = record.container_type
        
        return res
    
    # Method to directly create transport rates with proper values
    def create_transport_rate(self, vals=None):
        """Create a transport rate with values from the sale order"""
        self.ensure_one()
        if vals is None:
            vals = {}
            
        haulier_region_id = False
        
        if self.delivery_region:
            haulier_region = self.env['haulier.region'].search([('name', '=ilike', self.delivery_region)], limit=1)
            if haulier_region:
                haulier_region_id = haulier_region.id
                
        # Prepare values with defaults from the sale order
        vals.update({
            'order_id': self.id,
            'transport_city': vals.get('transport_city', self.lod_service_city.id if self.lod_service_city else False),
            'transport_port': vals.get('transport_port', self.port_of_dispatch.id if self.port_of_dispatch else False),
            'region_name': vals.get('region_name', self.delivery_region),
            'haulier_region_ids': vals.get('haulier_region_ids', haulier_region_id),
        })
    
        # Create the transport rate
        rate = self.env['sale.order.transport.rate'].create(vals)
        return rate
     
    
    def read(self, fields=None, load='_classic_read'):
        # When the record is loaded and the city field is requested, force recomputation.
        if fields is None or 'lod_service_city' in fields:
            # Loop through each record in the recordset
            for record in self:
                record.modified(['lod_service_city'])
                self.env['omnifreight.transport.rates'].with_context(
                    active_id=record.id,  # Use record.id instead of self.id
                    active_model='sale.order'
                ).force_recompute_from_sale_order(record.id)
        return super(OmnifreightLod, self).read(fields, load)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure context is passed to transport rates"""
        orders = super(OmnifreightLod, self).create(vals_list)
        
        # Set up context for each created order
        for order in orders:
            order.with_context({
                'default_transport_city': order.lod_service_city.id if order.lod_service_city else False,
                'default_transport_port': order.port_of_dispatch.id if order.port_of_dispatch else False,
                'default_region_name': order.delivery_region,
                'active_id': order.id,
                'active_model': 'sale.order',
                'default_container_type': order.container_type
            })
        
        if 'package_details_id' in vals_list and vals_list['package_details_id']:
            package_details = self.env['omnifreight.package.details'].browse(vals_list['package_details_id'])
            vals_list.update({
                'container_type': package_details.container_type,
                'contents': package_details.contents,
                'content_classification': package_details.content_classification,
            })
            
            order.create_transport_rate()
        return orders

    @api.model
    def copy_data(self, default=None):
        """Override copy_data to handle duplicating DAP-related lines when duplicating Sale Orders"""
    
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
        
            # Copy rate link IDs
            if record.lod_rate_link_ids:
                new_rate_links = []
                for link in record.lod_rate_link_ids:
                    link_copy_vals = link.copy_data()[0]
                    # Remove the original sales order and rates id to create a new record
                    if 'id' in link_copy_vals:
                        del link_copy_vals['id']
                    if 'order_id' in link_copy_vals:
                        del link_copy_vals['order_id']
                    new_rate_links.append((0, 0, link_copy_vals))
                record_data['lod_rate_link_ids'] = new_rate_links
        
            # Copy DAP special costs
            if record.lod_special_costs_id:
                new_special_costs = []
                for cost in record.lod_special_costs_id:
                    cost_copy_vals = cost.copy_data()[0]
                    # Remove the original sales order and special costs id to create a new record
                    if 'id' in cost_copy_vals:
                        del cost_copy_vals['id']
                    if 'sales_order_id' in cost_copy_vals:
                        del cost_copy_vals['sales_order_id']
                    new_special_costs.append((0, 0, cost_copy_vals))
                record_data['lod_special_costs_id'] = new_special_costs
    
        return result[0] if len(result) == 1 else result
