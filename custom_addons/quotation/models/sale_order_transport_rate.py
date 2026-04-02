from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .route_price_logic import RoutePriceLogic
from datetime import timedelta

class SaleOrderTransportRate(models.Model): 
    _name = 'sale.order.transport.rate'
    _description = 'Sale Order Transport Rate (FOB and LOD)'
    
    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', string="Sale Order")

    rate_id = fields.Many2one(
        'omnifreight.transport.rates',
        ondelete='cascade',
        string="Transport Rate"
    )
    
    is_selected_fob = fields.Boolean(default=False)
    
    fob_total = fields.Integer(string='FOB Total', compute='_compute_fob_total', store=True)

    rate_type = fields.Selection(related="rate_id.rate_type", store=True, readonly=False)
    
    active_sale_order_fob = fields.Many2one('sale.order', compute='_compute_active_sale_order_fob', store=True)
    
    # Related fields for convenience
    supplier_id = fields.Many2one(related="rate_id.supplier_id", store=True, readonly=False)
    haulier_region_ids = fields.Many2one(related="rate_id.haulier_region_ids", store=True, readonly=False)
    distance_range_ids = fields.One2many(related="rate_id.distance_range_ids", readonly=False)
    container_type = fields.Selection(related="rate_id.container_type", readonly=False, store=True)
    price_per_extra_km = fields.Integer(related="rate_id.price_per_extra_km", store=True, readonly=False)
    additional_notes = fields.Text(related="rate_id.additional_notes", readonly=False, store=True)
    currency_id = fields.Many2one(related="rate_id.currency_id", readonly=False, store=True)
    is_distance_based = fields.Boolean(related="rate_id.is_distance_based", string="Is Distance Based",
                                      help="If checked, rate is calculated based on distance. Otherwise, a fixed base price is used.", readonly=False)
    base_price = fields.Integer(related="rate_id.base_price", store=True, readonly=False)
    transport_city = fields.Many2one(related="rate_id.transport_city", readonly=False, store=True)
    transport_port = fields.Many2one(related="rate_id.transport_port", readonly=False, store=True)
    rate_valid_until = fields.Date(related="rate_id.valid_until", string="Valid Until", readonly=False, store=True)
    region_name = fields.Char(related="rate_id.region_name", store=True, readonly=False)
    transport_city_comp = fields.Many2one(related="rate_id.transport_city_comp", store=True)
    transport_port_comp = fields.Many2one(related="rate_id.transport_port_comp", store=True)
    show_expiry_warning = fields.Boolean(compute='_compute_expiry_with_warning', store=True, readonly=True)
    last_updated = fields.Date(related="rate_id.last_updated", store=True)
    content_classification = fields.Selection(related="order_id.content_classification", store=True, readonly=False)
    has_hazardous_content = fields.Boolean(related="order_id.has_hazardous_content", store=True, readonly=False)
    soc = fields.Boolean(related="order_id.soc", store=True, readonly=False)
    pickup_type = fields.Selection(related="rate_id.pickup_type", string="Pickup Type", store=True, readonly=False)
    
    # Surcharge on haulage fields
    is_surcharge = fields.Boolean(string="Surcharge", default=False)
    surcharge_fee = fields.Integer(string="Hazmat Surcharge")
    
    # Computed field to determine if this rate should be shown based on filtering rules
    should_show_rate = fields.Boolean(compute='_compute_should_show_rate', store=True)
    is_hidden = fields.Boolean(default=False)
    
    @api.model
    def _recompute_should_show_rate_all(self):
        """Recompute should_show_rate for all records"""
        all_rates = self.search([])
        all_rates._compute_should_show_rate()
        return True
    
    @api.depends('supplier_id', 'rate_valid_until', 'order_id')
    def _compute_should_show_rate(self):
        """Filter out expired rates when there are valid rates from the same supplier.
        Only show expired rates when they're the only option for that supplier.
        """
        for rate in self:
            if not rate.supplier_id or not rate.order_id:
                rate.should_show_rate = True
                continue
                
            today = fields.Date.today()
            is_expired = rate.rate_valid_until and rate.rate_valid_until < today
            
            if not is_expired:
                # Always show valid rates
                rate.should_show_rate = True
            else:
                # For expired rates, check if there are any valid rates from the same supplier
                # Check in all services: FOB, freight, and LOD
                valid_rates_exist = False
                
                # Check FOB rates (excluding current rate)
                fob_rates = self.env['sale.order.transport.rate'].search([
                    ('order_id', '=', rate.order_id.id),
                    ('supplier_id', '=', rate.supplier_id.id),
                    ('rate_valid_until', '>=', today),
                    ('id', '!=', rate.id)
                ])
                if fob_rates:
                    valid_rates_exist = True
                
                # Check freight rates (if they exist)
                freight_rates = self.env['omnifreight.transport.rates'].search([
                    ('supplier_id', '=', rate.supplier_id.id),
                    ('valid_until', '>=', today)
                ])
                if freight_rates:
                    valid_rates_exist = True
                
                # Check LOD rates
                lod_rates = self.env['sale.order.lod.transport.rate'].search([
                    ('order_id', '=', rate.order_id.id),
                    ('supplier_id', '=', rate.supplier_id.id),
                    ('rate_valid_until', '>=', today)
                ])
                if lod_rates:
                    valid_rates_exist = True
                
                # Show expired rate only if no valid rates exist for this supplier
                rate.should_show_rate = not valid_rates_exist
    
    def _prepare_rate_vals(self, vals):
        """
        Prepares a dictionary of values to create or update an 'omnifreight.transport.rates' record
        from a 'sale.order.transport.rate' vals dictionary. This ensures that any changes on the
        sale order rate line are reflected in the master transport rate record.
        """
        rate_vals = {}
        # This dictionary maps fields from this model to the fields in 'omnifreight.transport.rates'.
        # The key is the field in 'sale.order.transport.rate' and the value is the field in 'omnifreight.transport.rates'.
        sync_fields_map = {
            'supplier_id': 'supplier_id',
            'haulier_region_ids': 'haulier_region_ids',
            'rate_valid_until': 'valid_until',
            'is_distance_based': 'is_distance_based',
            'base_price': 'base_price',
            'transport_city': 'transport_city',
            'transport_port': 'transport_port',
            'surcharge_fee': 'surcharge_fee',
            'additional_notes': 'additional_notes',
            'currency_id': 'currency_id',
            'container_type': 'container_type',
            'price_per_extra_km': 'price_per_extra_km',
            'is_surcharge': 'is_surcharge',
            'region_name': 'region_name',
        }

        for so_field, rate_field in sync_fields_map.items():
            if so_field in vals and vals[so_field] is not False: # Ensure we don't sync 'False' values for relational fields
                rate_vals[rate_field] = vals[so_field]

        # If a region name is provided but no region ID, we try to find the region and set it.
        if 'haulier_region_ids' not in rate_vals and 'region_name' in rate_vals:
            region_name = rate_vals.get('region_name')
            if region_name:
                haulier_region = self.env['haulier.region'].search([
                    '|',
                    ('name', '=ilike', region_name.strip().upper()),
                    ('name', '=ilike', region_name)
                ], limit=1)
                if haulier_region:
                    rate_vals['haulier_region_ids'] = haulier_region.id
        
        # Always ensure a currency is set, defaulting to the company currency.
        if 'currency_id' not in rate_vals or not rate_vals.get('currency_id'):
            # Try to get currency from sale order if available
            order_id = vals.get('order_id') or self.env.context.get('active_id')
            if order_id:
                sale_order = self.env['sale.order'].browse(order_id)
                if sale_order and sale_order.currency_id:
                    rate_vals['currency_id'] = sale_order.currency_id.id
                else:
                    rate_vals['currency_id'] = self.env.company.currency_id.id
            else:
                rate_vals['currency_id'] = self.env.company.currency_id.id
        
        return rate_vals

    # --------------- Computed Totals ---------------------
    @api.depends('base_price', 'is_distance_based', 'price_per_extra_km', 'surcharge_fee', 'is_selected_fob', 'order_id.content_classification')
    def _compute_fob_total(self):
        """Compute the total FOB (Free On Board) cost.
        
        The total is calculated differently based on whether the rate is distance-based or fixed:
        - For fixed rates: total = base_price + surcharge_fee (if applicable)
        - For distance-based: total = distance_rate + surcharge_fee (if applicable)
        
        Only calculates for selected rates (is_selected_fob = True)
        """
        for rate in self:
            sale_order = rate.active_sale_order_fob
            if not sale_order:
                rate.fob_total = 0.0
                continue
                
            if not rate.is_distance_based:
                if rate.order_id.content_classification == 'hazardous':
                    rate.fob_total = rate.base_price + rate.surcharge_fee
                else:
                    rate.fob_total = rate.base_price
            elif rate.is_distance_based:
                distance = sale_order.distance
                if rate.order_id.content_classification == 'hazardous':
                    rate.base_price = RoutePriceLogic.compute_route_rate_for_distance(rate, distance)
                    rate.fob_total = rate.base_price + rate.surcharge_fee
                else:
                    rate.fob_total = RoutePriceLogic.compute_route_rate_for_distance(rate, distance)
            else:
                rate.fob_total = 0.0

    # --------------- Helpers for referencing correct order ---------------------
    @api.depends('order_id')
    def _compute_active_sale_order_fob(self):
        """Determine the active sale order for FOB calculations.
        This ensures FOB calculations use the correct sale order when multiple exist.
        """
        for rate in self:
            active_id = self.env.context.get('active_id')
            if active_id:
                sale_order = self.env['sale.order'].browse(active_id)
                if sale_order in rate.order_id:
                    rate.active_sale_order_fob = sale_order
                    continue
            rate.active_sale_order_fob = rate.order_id[0] if rate.order_id else False
        
    @api.depends('rate_valid_until')
    def _compute_expiry_with_warning(self):
        """Compute expiry warning flag based on rate_valid_until date."""
        today = fields.Date.context_today(self)
        for record in self:
            record.show_expiry_warning = record.rate_valid_until and record.rate_valid_until < today
    

    @api.onchange('region_name')
    def _onchange_region_name(self):
        """When region_name changes, try to find and set the corresponding haulier_region_ids"""
        for record in self:
            if record.region_name:
                # Clean up region name - remove extra spaces and uppercase
                clean_region_name = record.region_name.strip().upper()
                
                # Search for haulier region case-insensitive
                haulier_region = self.env['haulier.region'].search([
                    '|',
                    ('name', '=ilike', clean_region_name),
                    ('name', '=ilike', record.region_name)
                ], limit=1)
                
                if haulier_region:
                    # Update directly on the rate_id to ensure consistency
                    if record.rate_id:
                        record.rate_id.write({
                            'haulier_region_ids': haulier_region.id
                        })
                        # Also update the related field
                        record.haulier_region_ids = haulier_region.id
                        
    @api.onchange("base_price", "price_per_extra_km", "surcharge_fee", "is_surcharge")
    def _onchange_base_fob_price(self):
        for record in self:
            record._compute_fob_total()
            
    @api.onchange('is_distance_based')
    def _onchange_is_distance_based(self):
        self.rate_type = 'scaffold' if self.is_distance_based else 'city'
    
    @api.onchange('rate_id')
    def _onchange_rate_id(self):
        """Sync currency from rate_id when rate_id is selected"""
        if self.rate_id and self.rate_id.currency_id:
            self.currency_id = self.rate_id.currency_id
        
    @api.onchange('order_id.content_classification')
    def _onchange_classification(self):
        self._compute_fob_total()
        
    @api.model
    def default_get(self, fields_list):
        """
        Override default_get to utilize context values
        """
        res = super(SaleOrderTransportRate, self).default_get(fields_list)
        
        # Get values from context
        context = self.env.context
        active_model = context.get('active_model')
        active_id = context.get('active_id')
        
        if active_model == 'sale.order' and active_id:
            sale_order = self.env['sale.order'].browse(active_id)
            
            # Set order_id if it's in fields_list and not already set
            if 'order_id' in fields_list and not res.get('order_id'):
                res['order_id'] = active_id
                
            # Get transport city, port, and region from context or sale order
            transport_city = context.get('default_transport_city') or (sale_order.city_id.id if sale_order.city_id else False)
            transport_port = context.get('default_transport_port') or (sale_order.port_of_loading.id if sale_order.port_of_loading else False)
            region_name = context.get('default_region_name') or (sale_order.pickup_region if sale_order.pickup_region else '')
            
            if transport_city:
                res['transport_city'] = transport_city
            if transport_port:
                res['transport_port'] = transport_port
            if region_name:
                res['region_name'] = region_name
                
                # Try to find haulier region ID based on region name
                if region_name:
                    haulier_region = self.env['haulier.region'].search([
                        '|',
                        ('name', '=ilike', region_name.strip().upper()),
                        ('name', '=ilike', region_name)
                    ], limit=1)
                    
                    if haulier_region:
                        res['haulier_region_ids'] = haulier_region.id
                        
            if sale_order.container_type:  # If the sale_order has a container_type
                res['container_type'] = sale_order.container_type
            if sale_order.pickup_type:  # If the sale_order has a pickup_type
                res['pickup_type'] = sale_order.pickup_type
            if sale_order.content_classification == 'hazardous':
                res['is_surcharge'] = True
            # Set currency from sale order if available
            if 'currency_id' in fields_list and not res.get('currency_id') and sale_order.currency_id:
                res['currency_id'] = sale_order.currency_id.id
        
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        Overrides the create method to ensure that for each sale order transport rate,
        a corresponding master 'omnifreight.transport.rates' record exists.
        If a 'rate_id' is passed, it uses that. Otherwise, it tries to find an existing
        matching rate to prevent duplicates, or creates a new one.
        """
        for vals in vals_list:
            if not vals.get('rate_id'):
                # Try to find an existing rate that matches to prevent duplicates
                # This happens when rate_id is lost during Odoo's serialization of One2many fields
                order_id = vals.get('order_id') or self.env.context.get('active_id')
                if order_id:
                    sale_order = self.env['sale.order'].browse(order_id)
                    if sale_order:
                        supplier_id = vals.get('supplier_id')
                        rate_type = vals.get('rate_type')
                        container_type = vals.get('container_type') or sale_order.container_type
                        transport_city = vals.get('transport_city') or (sale_order.city_id.id if sale_order.city_id else False)
                        transport_port = vals.get('transport_port') or (sale_order.port_of_loading.id if sale_order.port_of_loading else False)
                        haulier_region_ids = vals.get('haulier_region_ids')
                        base_price = vals.get('base_price')
                        valid_until = vals.get('rate_valid_until') or vals.get('valid_until')
                        
                        if not haulier_region_ids and sale_order.pickup_region:
                            region = self.env['haulier.region'].search([
                                ('name', '=ilike', sale_order.pickup_region.strip())
                            ], limit=1)
                            if region:
                                haulier_region_ids = region.id
                        
                        if supplier_id and rate_type:
                            domain = [
                                ('supplier_id', '=', supplier_id),
                                ('rate_type', '=', rate_type),
                                ('container_type', '=', container_type),
                            ]
                            
                            if haulier_region_ids:
                                domain.append(('haulier_region_ids', '=', haulier_region_ids))
                            if transport_city:
                                domain.append(('transport_city', '=', transport_city))
                            if transport_port:
                                domain.append(('transport_port', '=', transport_port))
                            if base_price is not None:
                                domain.append(('base_price', '=', base_price))
                            if valid_until:
                                domain.append(('valid_until', '=', valid_until))
                            
                            existing_rate = self.env['omnifreight.transport.rates'].search(domain, order='create_date desc', limit=1)
                            if existing_rate:
                                vals['rate_id'] = existing_rate.id
                
                # If still no rate_id, create a new master rate record
                if not vals.get('rate_id'):
                    rate_vals = self._prepare_rate_vals(vals)
                    order_id = vals.get('order_id') or self.env.context.get('active_id')
                    if order_id:
                        sale_order = self.env['sale.order'].browse(order_id)
                        if sale_order:
                            if 'transport_city' not in rate_vals and sale_order.city_id:
                                rate_vals['transport_city'] = sale_order.city_id.id
                            if 'transport_port' not in rate_vals and sale_order.port_of_loading:
                                rate_vals['transport_port'] = sale_order.port_of_loading.id
                            if 'region_name' not in rate_vals and sale_order.pickup_region:
                                rate_vals['region_name'] = sale_order.pickup_region
                            if 'container_type' not in rate_vals and sale_order.container_type:
                                rate_vals['container_type'] = sale_order.container_type

                    if 'haulier_region_ids' not in rate_vals and rate_vals.get('region_name'):
                        region_name = rate_vals['region_name']
                        haulier_region = self.env['haulier.region'].search([
                            '|', ('name', '=ilike', region_name.strip().upper()), ('name', '=ilike', region_name)
                        ], limit=1)
                        if haulier_region:
                            rate_vals['haulier_region_ids'] = haulier_region.id
                    
                    if rate_vals:
                        new_rate = self.env['omnifreight.transport.rates'].create(rate_vals)
                        vals['rate_id'] = new_rate.id
        
        return super(SaleOrderTransportRate, self).create(vals_list)


    def write(self, vals):
        """
        Overrides the write method to synchronize changes to the master 'omnifreight.transport.rates' record.
        If a rate_id exists, it's updated. If it doesn't, a new one is created and linked.
        """
        # If region name is changed, we try to find the corresponding region ID.
        if 'region_name' in vals and 'haulier_region_ids' not in vals:
            region_name = vals.get('region_name')
            if region_name:
                haulier_region = self.env['haulier.region'].search([
                    '|', ('name', '=ilike', region_name.strip().upper()), ('name', '=ilike', region_name)
                ], limit=1)
                if haulier_region:
                    vals['haulier_region_ids'] = haulier_region.id

        # First, we apply the changes to the sale.order.transport.rate recordset.
        res = super().write(vals)

        # Only sync to master rate if rate_id is not set (create new master rate)
        # If rate_id is already set, don't modify the master rate - it's a reference
        for record in self:
            if not record.rate_id:
                # If no master rate exists, create one from the current values
                rate_vals_to_sync = self._prepare_rate_vals(vals)
                if rate_vals_to_sync:
                    # Read record values - record is a singleton so read() returns list with one dict
                    full_vals = record.read()[0] if record.exists() else {}
                    new_rate_vals = self._prepare_rate_vals(full_vals)
                    if new_rate_vals:
                        new_rate = self.env['omnifreight.transport.rates'].create(new_rate_vals)
                        # We do a direct write to prevent recursion.
                        super(SaleOrderTransportRate, record).write({'rate_id': new_rate.id})
        
        return res
    
    @api.onchange('order_id')
    def _onchange_sale_id_set_container_type(self):
        """Set the container type and currency from the sale order if available."""
        if self.order_id:
            if self.order_id.container_type:
                self.container_type = self.order_id.container_type
            # Set currency from sale order if not already set
            if not self.currency_id and self.order_id.currency_id:
                self.currency_id = self.order_id.currency_id

    @api.constrains('surcharge_fee')
    def _check_surcharge_fee(self):
        """Validate surcharge fee requirements.
        Ensures that when hazardous contents are being shipped (is_surcharge is True),
        a surcharge fee must be specified.
        """
        for record in self:
            if record.is_surcharge and not record.surcharge_fee:
                raise ValidationError("Surcharge on Haulage is required when shipping Hazardous contents.")
    
    def action_duplicate_rate(self):
        """Duplicate an expired rate by creating a new transport rate."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        
        if not self.rate_valid_until or self.rate_valid_until >= today:
            raise ValidationError("Only expired rates can be duplicated.")
        
        tomorrow = today + timedelta(days=1)
        currency_id = self.currency_id.id if self.currency_id else self.env.company.currency_id.id
        
        new_rate_vals = {
            'supplier_id': self.supplier_id.id,
            'haulier_region_ids': self.haulier_region_ids.id,
            'container_type': self.container_type,
            'price_per_extra_km': self.price_per_extra_km,
            'additional_notes': self.additional_notes,
            'currency_id': currency_id,
            'is_distance_based': self.is_distance_based,
            'base_price': self.base_price,
            'transport_city': self.transport_city.id,
            'transport_port': self.transport_port.id,
            'rate_type': self.rate_type,
            'subregion_id': self.rate_id.subregion_id.id if self.rate_id and self.rate_id.subregion_id else False,
            'pickup_type': self.pickup_type,
            'transport_city_comp': self.transport_city_comp.id,
            'transport_port_comp': self.transport_port_comp.id,
            'soc_tariff': self.rate_id.soc_tariff if self.rate_id else False,
            'surcharge_fee': self.surcharge_fee,
            'valid_until': tomorrow,
        }
        
        new_rate = self.env['omnifreight.transport.rates'].with_context(skip_valid_until_check=True).create(new_rate_vals)
        
        # Copy distance ranges if they exist
        for distance_range in self.distance_range_ids:
            self.env['omnifreight.distance.range'].create({
                'transport_rate': new_rate.id,
                'distance_from': distance_range.distance_from,
                'distance_to': distance_range.distance_to,
                'fixed_price': distance_range.fixed_price,
            })
        
        # Create a new sale order transport rate linked to the new rate
        new_sale_order_rate = self.env['sale.order.transport.rate'].create({
            'rate_id': new_rate.id,
            'order_id': self.order_id.id,
            'transport_city': self.transport_city.id,
            'transport_port': self.transport_port.id,
            'region_name': self.region_name,
            'haulier_region_ids': self.haulier_region_ids.id,
            'container_type': self.container_type,
            'currency_id': currency_id,
            'is_distance_based': self.is_distance_based,
            'pickup_type': self.pickup_type,
        })
        
        self.is_hidden = True
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Duplicate Rate',
            'res_model': 'sale.order.transport.rate',
            'res_id': new_sale_order_rate.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'skip_valid_until_check': True},
        }