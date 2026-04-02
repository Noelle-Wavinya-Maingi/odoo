from odoo.exceptions import UserError, ValidationError
from .route_price_logic import RoutePriceLogic
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class SaleOrderTransportRate(models.Model):
    _name = 'sale.order.lod.transport.rate'
    _description = 'Sale Order Transport Rate (FOB and LOD)'
    # The sale order document the transport rates are associated with
    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', string="Sale Order")
    # The transport rate associated with this sale order, a join to the master transport rates
    rate_id = fields.Many2one('omnifreight.transport.rates', ondelete='cascade', string="Transport Rate")
    # Flag to indicate that a rate is selected on this sale order for the LOD (Local At Destination) service
    is_selected_lod = fields.Boolean(default=False)
    
    lod_total = fields.Float(string='DAP Total', compute='_compute_lod_total', store=True)
    # Related field linking back to the rate's rate_type (city or scaffold)
    rate_type = fields.Selection(related="rate_id.rate_type", store=True, readonly=False)
    
    active_sale_order_lod = fields.Many2one('sale.order', compute='_compute_active_sale_order_lod', store=True)  
    
    ## Related fields, these are used to ensure that changes on the sale order transport rate
    #  are reflected in the master transport rate record.
    ## 
    supplier_id = fields.Many2one(related="rate_id.supplier_id", store=True, readonly=False)
    haulier_region_ids = fields.Many2one(related="rate_id.haulier_region_ids", store=True, readonly=False)
    distance_range_ids = fields.One2many(related="rate_id.distance_range_ids", readonly=False)
    container_type = fields.Selection(related="rate_id.container_type", readonly=False, store=True)
    price_per_extra_km = fields.Integer(related="rate_id.price_per_extra_km", store=True, readonly=False)
    additional_notes = fields.Text(related="rate_id.additional_notes", readonly=False, store=True)
    currency_id = fields.Many2one(related="rate_id.currency_id", readonly=False, store=True)
    is_distance_based = fields.Boolean(string="Is Distance Based",
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
    soc_tariff = fields.Integer(related="rate_id.soc_tariff", store=True, readonly=False, string="SOC Tariff")
    
    # Computed field to determine if this rate should be shown based on filtering rules
    should_show_rate = fields.Boolean(compute='_compute_should_show_rate', store=True)
    is_hidden = fields.Boolean(default=False)
    
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
                
                # Check FOB rates
                fob_rates = self.env['sale.order.transport.rate'].search([
                    ('order_id', '=', rate.order_id.id),
                    ('supplier_id', '=', rate.supplier_id.id),
                    ('rate_valid_until', '>=', today)
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
                
                # Check LOD rates (excluding current rate)
                lod_rates = self.env['sale.order.lod.transport.rate'].search([
                    ('order_id', '=', rate.order_id.id),
                    ('supplier_id', '=', rate.supplier_id.id),
                    ('rate_valid_until', '>=', today),
                    ('id', '!=', rate.id)
                ])
                if lod_rates:
                    valid_rates_exist = True
                
                # Show expired rate only if no valid rates exist for this supplier
                rate.should_show_rate = not valid_rates_exist

    def _prepare_rate_vals(self, vals):
        """
        Prepares a dictionary of values to create or update an 'omnifreight.transport.rates' record
        from a 'sale.order.lod.transport.rate' vals dictionary. This ensures that any changes on the
        sale order rate line are reflected in the master transport rate record.
        """
        rate_vals = {}
        # This dictionary maps fields from this model to the fields in 'omnifreight.transport.rates'.
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
            if so_field in vals and vals[so_field] is not False:
                rate_vals[rate_field] = vals[so_field]

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
        
    @api.depends('base_price', 'is_distance_based', 'price_per_extra_km', 'order_id.lod_distance', 'soc_tariff', 'order_id.soc')
    def _compute_lod_total(self):
        """Compute the total LAD (Local At Destination) cost.
        
        The total is calculated differently based on whether the rate is distance-based or fixed:
        - For fixed rates: total = base_price + soc_tariff (if SOC enabled)
        - For distance-based: total = distance_rate + soc_tariff (if SOC enabled)
        """
        for rate in self:
            sale_order = rate.active_sale_order_lod
            if not sale_order:
                rate.lod_total = 0.0
                continue
                
            # Calculate base total
            if not rate.is_distance_based:
                base_total = float(rate.base_price or 0.0)
            elif rate.is_distance_based:
                distance = sale_order.lod_distance
                rate.base_price = RoutePriceLogic.compute_route_rate_for_distance(rate, distance)
                base_total = rate.base_price
            else:
                base_total = 0.0
            
            # Add SOC tariff if SOC is enabled
            if sale_order.soc and float(rate.soc_tariff or 0.0):
                base_total += float(rate.soc_tariff or 0.0)
            
            rate.lod_total = base_total
                
    @api.onchange("base_price", 'is_distance_based', 'price_per_extra_km')
    def _onchange_base_price(self):
        for record in self:
            record._compute_lod_total()
    
    @api.depends('order_id')
    def _compute_active_sale_order_lod(self):
        for rate in self:
            active_id = self.env.context.get('active_id')
            if active_id:
                sale_order = self.env['sale.order'].browse(active_id)
                if sale_order in rate.order_id:
                    rate.active_sale_order_lod = sale_order
                    continue
            rate.active_sale_order_lod = rate.order_id[0] if rate.order_id else False
            
    @api.depends('rate_valid_until')
    def _compute_expiry_with_warning(self):
        """Compute expiry warning flag based on rate_valid_until date."""
        today = fields.Date.context_today(self)
        for record in self:
            record.show_expiry_warning = record.rate_valid_until and record.rate_valid_until < today

    @api.onchange('region_name')
    def _onchange_delivery_region_name(self):
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
                    
    @api.onchange('is_distance_based')
    def _onchange_is_distance_based(self):
        self.rate_type = 'scaffold' if self.is_distance_based else 'city'
    
    @api.onchange('rate_id')
    def _onchange_rate_id(self):
        """Sync currency from rate_id when rate_id is selected"""
        if self.rate_id and self.rate_id.currency_id:
            self.currency_id = self.rate_id.currency_id
    
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
            transport_city = context.get('default_transport_city') or (sale_order.lod_service_city.id if sale_order.lod_service_city else False)
            transport_port = context.get('default_transport_port') or (sale_order.port_of_dispatch.id if sale_order.port_of_dispatch else False)
            region_name = context.get('default_region_name') or (sale_order.delivery_region if sale_order.delivery_region else '')
            
            if transport_city:
                res['transport_city'] = transport_city
            if transport_port:
                res['transport_port'] = transport_port
            if region_name:
                res['region_name'] = region_name
                
                # Try to find haulier region ID based on region name
                haulier_region = self.env['haulier.region'].search([
                    '|',
                    ('name', '=ilike', region_name.strip().upper()),
                    ('name', '=ilike', region_name)
                ], limit=1)
                
                if haulier_region:
                    res['haulier_region_ids'] = haulier_region.id
                    
            if 'order_id' in res:
                sale_order = self.env['sale.order'].browse(res['order_id'])
            if sale_order.container_type:  # If the sale_order has a container_type
                res['container_type'] = sale_order.container_type
            # Set currency from sale order if available
            if 'currency_id' in fields_list and not res.get('currency_id') and sale_order.currency_id:
                res['currency_id'] = sale_order.currency_id.id
        
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        Overrides the create method to ensure that for each sale order LOD transport rate,
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
                        transport_city = vals.get('transport_city') or (sale_order.lod_service_city.id if sale_order.lod_service_city else False)
                        transport_port = vals.get('transport_port') or (sale_order.port_of_dispatch.id if sale_order.port_of_dispatch else False)
                        haulier_region_ids = vals.get('haulier_region_ids')
                        base_price = vals.get('base_price')
                        valid_until = vals.get('rate_valid_until') or vals.get('valid_until')
                        
                        if not haulier_region_ids and sale_order.delivery_region:
                            region = self.env['haulier.region'].search([
                                ('name', '=ilike', sale_order.delivery_region.strip())
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
                            if 'transport_city' not in rate_vals and sale_order.lod_service_city:
                                rate_vals['transport_city'] = sale_order.lod_service_city.id
                            if 'transport_port' not in rate_vals and sale_order.port_of_dispatch:
                                rate_vals['transport_port'] = sale_order.port_of_dispatch.id
                            if 'region_name' not in rate_vals and sale_order.delivery_region:
                                rate_vals['region_name'] = sale_order.delivery_region
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
        if 'region_name' in vals and 'haulier_region_ids' not in vals:
            region_name = vals.get('region_name')
            if region_name:
                haulier_region = self.env['haulier.region'].search([
                    '|', ('name', '=ilike', region_name.strip().upper()), ('name', '=ilike', region_name)
                ], limit=1)
                if haulier_region:
                    vals['haulier_region_ids'] = haulier_region.id

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
                        super(SaleOrderTransportRate, record).write({'rate_id': new_rate.id})
        
        return res
        
    def force_recompute_order(self, order_id):
        """
        Force recomputation of all relevant fields for transport rates associated with a sale order
        :param sale_order: sale.order recordset
        """
        if not order_id:
            return False
    
        # Find all transport rates linked to this sale order
        transport_rates = self.search([('order_id', '=', order_id)])
        if not transport_rates:
            return True
    
    
        try:
            # Force recomputation of all computed fields
            transport_rates._compute_lod_total()
            transport_rates._compute_active_sale_order_lod()
        
            # Also recompute related fields if needed
            for rate in transport_rates:
                if rate.region_name and not rate.haulier_region_ids:
                    rate._onchange_delivery_region_name()
        
            return True
        except Exception as e:
            raise UserError(f"Could not recompute transport rates: {str(e)}")
        
    
    @api.onchange('order_id')
    def _onchange_order_id_set_container_type(self):
        """Set the container type and currency from the sale order if available."""
        if self.order_id:
            if self.order_id.container_type:
                self.container_type = self.order_id.container_type
            # Set currency from sale order if not already set
            if not self.currency_id and self.order_id.currency_id:
                self.currency_id = self.order_id.currency_id
    
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
            'pickup_type': self.rate_id.pickup_type if self.rate_id and self.rate_id.pickup_type else False,
            'transport_city_comp': self.transport_city_comp.id,
            'transport_port_comp': self.transport_port_comp.id,
            'soc_tariff': self.rate_id.soc_tariff if self.rate_id else False,
            'surcharge_fee': self.rate_id.surcharge_fee if self.rate_id else False,
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
        
        # Create a new sale order LOD transport rate linked to the new rate
        new_sale_order_rate = self.env['sale.order.lod.transport.rate'].create({
            'rate_id': new_rate.id,
            'order_id': self.order_id.id,
            'transport_city': self.transport_city.id,
            'transport_port': self.transport_port.id,
            'region_name': self.region_name,
            'haulier_region_ids': self.haulier_region_ids.id,
        })
        
        self.is_hidden = True
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Duplicate Rate',
            'res_model': 'sale.order.lod.transport.rate',
            'res_id': new_sale_order_rate.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'skip_valid_until_check': True},
        }