from odoo import api, models


class OmnifreightQuotationOnchange(models.AbstractModel):
    _name = 'omnifreight.quotation.onchange'
    _description = 'Omnifreight quotation onchange'

    @api.onchange('service_country_id', 'pickup_region', 'city_id', 'port_of_loading', 'transport_rates', 'pickup_type')
    def _onchange_region(self):
        """Update transport rates when region or container type or pickup type changes.
        Additionally, sort the rates so that the ones with the desired price type show up first.
        When suppliers have the same name and price type, only the latest one is included.
        """
        domain = []
        
        if self.pickup_region:
            domain.append(('haulier_region_ids.name', 'ilike', self.pickup_region))
            
        if self.pickup_type:
            domain.append(('pickup_type', '=', self.pickup_type))
            
        if not self.service_country_id and self.city_id:
            domain.extend([
                ('rate_type', '=', 'city'),
                # For city: check either the manual or computed field
                '|', 
                    ('transport_city', '=', self.city_id.id),
                    ('transport_city_comp', '=', self.city_id.id),
                # For port: check either the manual or computed field
                '|',
                    ('transport_port', '=', self.port_of_loading.id),
                    ('transport_port_comp', '=', self.port_of_loading.id),
            ])
        elif not self.city_id and self.service_country_id:
            domain.append(('rate_type', '=', 'scaffold'))
        elif self.service_country_id and self.city_id:
            domain.extend([
                '|',
                    ('rate_type', '=', 'scaffold'),
                    '&',
                        ('rate_type', '=', 'city'),
                        '&',
                            # Check for city match in either field
                            '|', 
                                ('transport_city', '=', self.city_id.id),
                                ('transport_city_comp', '=', self.city_id.id),
                            # Check for port match in either field
                            '|',
                                ('transport_port', '=', self.port_of_loading.id),
                                ('transport_port_comp', '=', self.port_of_loading.id)
            ])
            
        if domain:
            # Search for matching rates (including expired ones)
            rates = self.env['omnifreight.transport.rates'].sudo().search(domain)
            
            # Define the desired ordering.
            order_map = {
                'city': 0,
                'scaffold': 1,
            }
            
            # First sort rates by the preference order and creation date
            sorted_rates = rates.sorted(key=lambda r: (order_map.get(r.rate_type, 99), -r.create_date.timestamp()))
            
            # Filter to keep only the latest rate for each supplier-price type combination
            filtered_rates = self.env['omnifreight.transport.rates']
            supplier_pricetype_map = {}
            
            for rate in sorted_rates:
                key = (rate.supplier_id.name, rate.rate_type)
                if key not in supplier_pricetype_map or rate.create_date > supplier_pricetype_map[key].create_date:
                    supplier_pricetype_map[key] = rate
            
            for rate in supplier_pricetype_map.values():
                filtered_rates += rate
            
            # Update the Many2many relation without deleting records
            self.transport_rates = filtered_rates
            
            # Clear existing rate links
            self.rate_link_ids = [(5, 0, 0)]
            
            rate_link_vals = []
            
            #  Create new rate link records for the filtered rates
            for rate in filtered_rates:
                rate_link_vals.append((0, 0, {
                    'rate_id': rate.id,
                    'order_id': self.id,
                }))
                
            if rate_link_vals:
                self.rate_link_ids = rate_link_vals
                
        else:
            self.transport_rates = False

    @api.onchange('container_type', 'contents', 'content_classification')
    def _onchange_package_details(self):
        """When any of the editable fields in the quotation are changed, update the related package details"""
        if self.package_details_id:
            self.package_details_id.container_type = self.container_type
            self.package_details_id.contents = self.contents
            self.package_details_id.content_classification = self.content_classification
            self.package_details_id.soc = self.soc
            
    @api.onchange('route_id')
    def _onchange_route_id(self):
        """
        This method is triggered when the route_id is selected/changed.
        It updates the port_of_loading and port_of_dispatch fields accordingly.
        """
        # Check if we're already in the middle of a port update to prevent infinite loops
        if self.env.context.get('updating_ports_from_route'):
            return
            
        if self.route_id:
            # Set context flag to prevent infinite loop
            self = self.with_context(updating_ports_from_route=True)
            self.port_of_loading = self.route_id.departure_port_id
            self.port_of_dispatch = self.route_id.arrival_port_id
        else:
            # Set context flag to prevent infinite loop
            self = self.with_context(updating_ports_from_route=True)
            self.port_of_loading = False
            self.port_of_dispatch = False

    @api.onchange('port_of_loading', 'port_of_dispatch')
    def _onchange_ports(self):
        """
        This method is triggered when either port_of_loading or port_of_dispatch is changed.
        It updates the route_id to match the combination of ports.
        """
        # Check if we're already in the middle of a route update to prevent infinite loops
        if self.env.context.get('updating_route_from_ports'):
            return
        
        # Validate that both ports are not the same
        if self.port_of_loading and self.port_of_dispatch:
            if self.port_of_loading.id == self.port_of_dispatch.id:
                return {
                    'warning': {
                        'title': 'Invalid Port Selection',
                        'message': 'Port of Loading and Port of Destination cannot be the same. Please select different ports.',
                    }
                }
            
            try:
                # Search for a route with the selected POL and POD
                route = self.env['omnifreight.route'].search([
                    ('departure_port_id', '=', self.port_of_loading.id),
                    ('arrival_port_id', '=', self.port_of_dispatch.id)
                ], limit=1)

                if route:
                    # If a route exists, set the route_id
                    # Set context flag to prevent infinite loop
                    self = self.with_context(updating_route_from_ports=True)
                    self.route_id = route
                else:
                    # If no route exists, try to create one
                    try:
                        new_route = self.env['omnifreight.route'].create({
                            'departure_port_id': self.port_of_loading.id,
                            'arrival_port_id': self.port_of_dispatch.id,
                        })
                        # Set context flag to prevent infinite loop
                        self = self.with_context(updating_route_from_ports=True)
                        self.route_id = new_route
                    except Exception as e:
                        self.route_id = False
            except Exception as e:
                self.route_id = False
        else:
            # If either port is not selected, clear the route_id
            # Set context flag to prevent infinite loop
            self = self.with_context(updating_route_from_ports=True)
            self.route_id = False
            
    @api.onchange('service_country_id', 'city_id')
    def _onchange_country_city_field(self):
        """
        This method ensures the city and country provided are related.
        """
        for record in self:
            if record.service_country_id:
                if record.city_id.country_id != record.service_country_id:
                    record.city_id = False
            elif not record.service_country_id:
                record.city_id = False  
                
    @api.onchange('city_id')
    def _onchange_city(self):
        if self.city_id:
            self.service_country_id = self.city_id.country_id
    
    @api.onchange('transport_rates')
    def _onchange_transport_rates(self):
        """
        Ensures that only one transport rate (from the Many2many field) is selected at a time.
        The is_selected field lives on the transport rates model.
        When multiple rates are selected, the one with the most recent update is kept.
        """
        for order in self:
            # Get the transport rate records (from the Many2many field) that are marked as selected.
            selected_rates = order.transport_rates.filtered(lambda r: r.is_selected_fob)
            if len(selected_rates) > 1:
                # Identify the newly selected price by comparing with its _origin value.
                # If a record is new or its _origin had is_selected==False, it's the one recently toggled.
                newly_selected = selected_rates.filtered(lambda p: not p._origin or not p._origin.is_selected_fob)
                if newly_selected:
                    most_recent = newly_selected[0]
                else:
                    # If no record appears as newly selected, keep the first one.
                    most_recent = selected_rates[0]
            
            
                # Deselect all other prices.
                for price in selected_rates:
                    if price != most_recent:
                        price.is_selected_fob = False
                        
            order._compute_fob_selected_haulier()

    @api.onchange('city_id', 'port_of_loading')
    def _onchange_fill_transport_location(self):
        """
        When the city or port is provided on the sale order,
        prefill the transport_rates' transport_city and transport_port
        ONLY IF the rate is being created (new).
        """
        for order in self:
            if order.city_id or order.port_of_loading:
                for rate in order.transport_rates:
                    # Check if the rate is new (being created)
                    if not rate._origin:
                        # If a manual city is provided on the sale order and not already set on the rate,
                        # pass the city (as a Many2one reference) to the transport rate.
                        if order.city_id and not rate.transport_city:
                            rate.transport_city = order.city_id.id
                        if order.port_of_loading and not rate.transport_port:
                            rate.transport_port = order.port_of_loading.id
                            

    @api.onchange('city_id')
    def _onchange_city_set_country_clear_zip(self):
        """
        When the city changes, set the country to the city's country and clear the zip code.
        """
        for record in self:
            if record.city_id:
                record.service_country_id = record.city_id.country_id
            if record.zip_code_id.un_city_id != record.city_id:
                record.zip_code_id = False

    @api.onchange('zip_code_id')
    def _onchange_zip_code_set_city(self):
        """
        When the zip code changes, set the city to the zip code's city.
        """
        for record in self:
            if record.zip_code_id:
                record.city_id = record.zip_code_id.un_city_id

    @api.onchange('is_fob')
    def _onchange_is_fob(self):
        """
        When the FOB checkbox is toggled, update the quote type accordingly.
        """
        if self.is_fob:
            if self.is_freight and self.is_lod:
                self.quote_type = 'fob_freight_lod'
            elif self.is_freight:
                self.quote_type = 'fob_freight'
            else:
                self.quote_type = 'fob_only'
        else:
            if self.is_freight and self.is_lod:
                self.quote_type = 'freight_dap'
            elif self.is_freight:
                self.quote_type = 'freight_only'
            elif self.is_lod:
                self.quote_type = 'lod_only'
            else:
                self.quote_type = False
                
    @api.onchange('port_of_loading')
    def _onchange_pol_extra_charges(self):
        """When the port of loading changes, clear existing extra charges related to the previous port."""
        # Check if port_of_loading field exists and has a value
        if 'port_of_loading' in self._fields and self.port_of_loading:
            # Only clear if we have an originand the port is actually changing to a different one
            if self._origin and self.port_of_loading.id != self._origin.port_of_loading.id:
                # Clear all records in the one2many field
                self.fob_special_costs_id = [(5, 0, 0)]