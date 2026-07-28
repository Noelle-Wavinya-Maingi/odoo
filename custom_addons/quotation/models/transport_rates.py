from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from .route_price_logic import RoutePriceLogic
from .route_logic import compute_create_date_only
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class TransportRates(models.Model):
    _name = 'omnifreight.transport.rates'
    _description = 'Rates for transport in regions'
    
    supplier_id = fields.Many2one('res.partner', string='Supplier', default=None)
    # Reference to the haulier region model
    haulier_region_ids = fields.Many2one('haulier.region', string='Region')
    # Reference to the distance range model
    distance_range_ids = fields.One2many('omnifreight.distance.range', 'transport_rate')

    container_type = fields.Selection(
        selection=lambda self: self.env['omnifreight.package.details'].CONTAINER_TYPES,
        string="Container Size"
    )
    # Cost structure field to display the distance range with its fixed price
    cost_structures = fields.Char(
        string="Cost Structures",
        compute="_compute_cost_structures",
        store=True
    )
    price_per_extra_km = fields.Integer(string="Price Per Extra KM")

    # Additional notes field
    additional_notes = fields.Text(string="Notes")
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    last_updated = fields.Date(compute='_compute_create_date_only')
    valid_until = fields.Date(string="Valid Until")
    
    # Many2many link to sale.order
    sales_ids = fields.Many2many('sale.order', 'sale_order_fob_transport_rates_rel', 'rate_id', 'order_id', string="Sales Orders")
    
    lod_sales_ids = fields.Many2many('sale.order', 'sale_order_lod_transport_rates_rel', 'rate_id', 'order_id', string="Lod Sales Order")
    
    # Many2many field to track selected rates for each sale order
    selected_for_sale_orders = fields.Many2many('sale.order', 'sale_order_selected_fob_rates_rel', 'rate_id', 'order_id', string="Selected for Sale Orders")
    
    selected_lad_sale_orders = fields.Many2many('sale.order', 'sale_order_selected_lad_rates_rel', 'rate_id', 'order_id', string="Selected LAD Sale Orders")
    
    # Boolean flag to indicate if rate is selected
    is_selected = fields.Boolean()
    is_selected_fob = fields.Boolean()
    is_selected_lod = fields.Boolean()
    
    # Field to indicate if the rate is distance-based or city-based
    is_distance_based = fields.Boolean(string="Is Distance Based",
                                      help="If checked, rate is calculated based on distance. Otherwise, a fixed base price is used.")
    
    # Base price for city-based rates
    base_price = fields.Integer(string="Fixed Price", 
                             help="Fixed price for city-based rates when not using distance calculation")
    
    transport_city = fields.Many2one('unloc.city', string="City")
    transport_port = fields.Many2one('port', string="Port")
    rate_type = fields.Selection([
        ('city', 'City'),
        ('scaffold', 'Scaffold')
    ])
    
    # Subregion associated with the transport rate
    subregion_id = fields.Many2one('un.subregion', string="Subregion")
    
    # Computed region name field
    region_name = fields.Char(
        string="Region Name",
        compute="_compute_region_name",
        store=True,
        readonly=True
    )
    
    # Computed field for the total transport rate cost
    fob_total = fields.Float(string='FOB Total', compute='_compute_fob_total')
    lod_total = fields.Float(string='DAP Total', compute='_compute_lod_total')
    
    # Separate active sale order fields (computed from different many2many fields)
    active_sale_order_fob = fields.Many2one('sale.order', compute='_compute_active_sale_order_fob', store=True)
    active_sale_order_lod = fields.Many2one('sale.order', compute='_compute_active_sale_order_lod', store=True)
    
    transport_city_comp = fields.Many2one(
        'unloc.city', 
        string="Transport City (Computed)", 
        compute="_compute_transport_city", 
        store=True,
        readonly=True
    )
    transport_port_comp = fields.Many2one(
        'port', 
        string="Transport Port (Computed)", 
        compute="_compute_transport_port", 
        store=True,
        readonly=True
    )
    
    show_expiry_warning = fields.Boolean(compute='_compute_expiry_with_warning', store=True, readonly=True)
    # Marked true for hazardous materials
    is_surcharge = fields.Boolean(string="Surcharge", default=False)
    # Surcharge fee for hazardous materials, addeed to the total costs and is provided for by a supplier
    surcharge_fee = fields.Integer(string="Surcharge Fee")
    # Shippers own container (SOC) tarrif, charged by the carrier
    soc_tariff = fields.Integer(string="SOC Tariff", help="Shipper's Own Container Tariff, charged by the carrier")
    # Pickup type for cargo, different supplier provide different pickup types
    pickup_type = fields.Selection([
        ('immediate_on_trailer', 'Immediate loading / On trailer'),
        ('interval_on_trailer', 'Loading with Interval / On trailer'),
        ('immediate_on_sidebar', 'Immediate loading / Sideloader'),
        ('interval_on_sidebar', 'Loading with Interval / Sideloader'),
        ('one_way_on_trailer', 'One Way / On Trailer'),
        ('one_way_on_sideloader', 'One Way / Sideloader'),
    ], string='Pickup Type')
    
    # Active field for archiving
    active = fields.Boolean(default=True, string="Active")
    
    # ----------------------------------
    # Computed Methods
    # ----------------------------------
    @api.depends('sales_ids')
    def _compute_active_sale_order_fob(self):
        """Get the active sale order from context or the first one related"""
        for rate in self:
            active_id = self.env.context.get('active_id')
            if active_id:
                sale_order = self.env['sale.order'].browse(active_id)
                if sale_order in rate.sales_ids:
                    rate.active_sale_order_fob = sale_order
                    continue
            
            # Fallback to first related sale order
            rate.active_sale_order_fob = rate.sales_ids[0] if rate.sales_ids else False

    @api.depends('lod_sales_ids')
    def _compute_active_sale_order_lod(self):
        """Compute the active sale order for LOD using sales_ids."""
        for rate in self:
            active_id = self.env.context.get('active_id')
            if active_id:
                sale_order = self.env['sale.order'].browse(active_id)
                if sale_order in rate.lod_sales_ids:
                    rate.active_sale_order_lod = sale_order
                    continue
            rate.active_sale_order_lod = rate.lod_sales_ids[0] if rate.lod_sales_ids else False

    @api.depends('sales_ids', 'sales_ids.distance', 'sales_ids.is_fob',
                 'distance_range_ids', 'price_per_extra_km', 'is_distance_based',
                 'base_price', 'surcharge_fee', 'is_surcharge')
    def _compute_fob_total(self):
        """Calculate FOB total for this rate based on active sale order data"""
        for rate in self:
            sale_order = rate.active_sale_order_fob
            if not sale_order:
                rate.fob_total = 0.0
                continue
            if sale_order.is_fob:
                # Calculate base total
                if not rate.is_distance_based:
                    base_total = rate.base_price or 0.0
                elif sale_order.distance:
                    base_total = RoutePriceLogic.compute_route_rate_for_distance(rate, sale_order.distance)
                else:
                    base_total = 0.0
                
                # Add surcharge if applicable
                if rate.is_surcharge and rate.surcharge_fee:
                    base_total += rate.surcharge_fee
                    
                rate.fob_total = base_total
            else:
                rate.fob_total = 0.0
                
    def _get_active_sale_order(self, rec):
        """Helper method to get the active sale order using context's active_id or the first sale order."""
        # First, check the correct computed fields
        active_view = self.env.context.get('active_view')
        if active_view == 'fob':
            if rec.active_sale_order_fob and rec.active_sale_order_fob.exists():
                return rec.active_sale_order_fob
        elif active_view == 'lod':
            if rec.active_sale_order_lod and rec.active_sale_order_lod.exists():
                return rec.active_sale_order_lod
        
        # Next, try to get from context
        active_id = self.env.context.get('active_id')
        if self.env.context.get('active_model') == 'sale.order' and active_id:
            if isinstance(active_id, int) or (isinstance(active_id, str) and active_id.isdigit()):
                sale_order = self.env['sale.order'].browse(int(active_id))
                if sale_order.exists():
                    return sale_order
                    
        # Try to get from params
        if self.env.context.get('params') and self.env.context['params'].get('resId'):
            resId = self.env.context['params']['resId']
            if isinstance(resId, int) or (isinstance(resId, str) and resId.isdigit()):
                sale_order = self.env['sale.order'].browse(int(resId))
                if sale_order.exists():
                    return sale_order
                    
        # Fallback to first related sale order based on the context
        if active_view == 'fob' and rec.sales_ids:
            return rec.sales_ids[0]
        elif active_view == 'lod' and rec.lod_sales_ids:
            return rec.lod_sales_ids[0]
            
        return False
    @api.depends('lod_sales_ids', 'lod_sales_ids.lod_distance', 'lod_sales_ids.is_lod',
                 'distance_range_ids', 'price_per_extra_km', 'is_distance_based',
                 'base_price')
    def _compute_lod_total(self):
        """Calculate LOD total for this rate based on active sale order data"""
        for rate in self:
            sale_order = rate.active_sale_order_lod
            if not sale_order:
                rate.lod_total = 0.0
                continue
            if sale_order.is_lod:
                if not rate.is_distance_based:
                    rate.lod_total = rate.base_price
                elif sale_order.lod_distance:
                    rate.lod_total = RoutePriceLogic.compute_route_rate_for_distance(rate, sale_order.lod_distance)
                else:
                    rate.lod_total = 0.0
            else:
                rate.lod_total = 0.0

    @api.depends('distance_range_ids', 'write_date', 'supplier_id')
    def _compute_cost_structures(self):
        for record in self:
            cost_details = []
            if record.is_distance_based and record.distance_range_ids:
                for range_record in record.distance_range_ids:
                    cost_details.append(
                        f"{range_record.min_distance} Km - {range_record.max_distance} Km, Fixed price: €{range_record.price}"
                    )
                record.cost_structures = " | ".join(cost_details)
            elif not record.is_distance_based:
                record.cost_structures = f"Fixed price: €{record.base_price}"
            else:
                record.cost_structures = 'N/A'
    
    def _compute_create_date_only(self):
        compute_create_date_only(self)
        
    @api.depends('supplier_id', 'last_updated')
    def _compute_name(self):
        for record in self:
            if record.supplier_id and record.supplier_id.name:
                record.name = f"{record.supplier_id.name}({record.last_updated})"
            else:
                record.name = "Unnamed Rate"

    @api.depends('haulier_region_ids', 'sales_ids.pickup_region', 'sales_ids.delivery_region', 
                 'sales_ids.is_fob', 'sales_ids.is_lod')
    def _compute_region_name(self):
        for record in self:
            if record.haulier_region_ids:
                record.region_name = record.haulier_region_ids.name
            else:
                # Use FOB active sale order as fallback (or adapt as needed)
                sale_order = self._get_active_sale_order(record)
                if sale_order:
                    active_view = self.env.context.get('active_view')
                    if active_view == 'fob':
                        region_candidate = sale_order.pickup_region
                    elif active_view == 'lod':
                        region_candidate = sale_order.delivery_region
                    else:
                        region_candidate = sale_order.pickup_region or sale_order.delivery_region
                    if region_candidate:
                        # Try exact match first
                        haulier_region = self.env['haulier.region'].search(
                            [('name', '=', region_candidate)], limit=1
                        )
                        if not haulier_region:
                            # Try case-insensitive match
                            haulier_region = self.env['haulier.region'].search(
                                [('name', 'ilike', region_candidate)], limit=1
                            )
                        if not haulier_region:
                            # Try with trimmed and uppercase
                            clean_region_name = region_candidate.strip().upper()
                            haulier_region = self.env['haulier.region'].search(
                                [('name', 'ilike', clean_region_name)], limit=1
                            )
                        if haulier_region:
                            # Update both the region_id and region_name
                            record.haulier_region_ids = haulier_region.id
                            record.region_name = haulier_region.name
                        else:
                            record.region_name = region_candidate
                    else:
                        record.region_name = ''
                else:
                    record.region_name = ''

    @api.depends('transport_city', 'sales_ids.city_id', 'lod_sales_ids.lod_service_city',
                 'sales_ids.is_fob', 'lod_sales_ids.is_lod', 'active_sale_order_fob', 'active_sale_order_lod')
    def _compute_transport_city(self):
        for record in self:
            if record.transport_city:
                record.transport_city_comp = record.transport_city.id
            else:
                # Prefer FOB city; fallback to LAD
                sale_order = self._get_active_sale_order(record)
                if sale_order:
                    active_view = self.env.context.get('active_view')
                    if active_view == 'fob':
                        city_candidate = sale_order.city_id
                    elif active_view == 'lod':
                        city_candidate = sale_order.lod_service_city
                    else:
                        if sale_order.is_fob and not sale_order.is_lod:
                            city_candidate = sale_order.city_id
                        elif sale_order.is_lod and not sale_order.is_fob:
                            city_candidate = sale_order.lod_service_city
                        elif sale_order.is_fob and sale_order.is_lod:
                            city_candidate = sale_order.city_id
                        else:
                            city_candidate = False
                    if city_candidate:
                        record.transport_city_comp = city_candidate.id
                        record.transport_city = city_candidate.id
                    else:
                        record.transport_city_comp = False
                else:
                    record.transport_city_comp = False

    @api.depends('transport_port', 'sales_ids.port_of_loading', 'lod_sales_ids.port_of_dispatch',
                 'sales_ids.is_fob', 'lod_sales_ids.is_lod', 'active_sale_order_fob', 'active_sale_order_lod')
    def _compute_transport_port(self):
        for record in self:
            if record.transport_port:
                record.transport_port_comp = record.transport_port.id
            else:
                sale_order = self._get_active_sale_order(record)
                if sale_order:
                    active_view = self.env.context.get('active_view')
                    candidate = sale_order.port_of_loading if active_view == 'fob' else sale_order.port_of_dispatch
                    candidate = candidate or (sale_order.port_of_loading or sale_order.port_of_dispatch)
                    if candidate:
                        record.transport_port_comp = candidate.id
                        record.transport_port = candidate.id
                    else:
                        record.transport_port_comp = False
                else:
                    record.transport_port_comp = False
                    
    @api.depends('selected_for_sale_orders', 'active_sale_order_fob')
    def _compute_is_selected_fob(self):
        """Compute whether the rate is selected for the current sale order."""
        for rate in self:
             # If we're in a force_write context, don't recompute
            sale_order = rate.active_sale_order_fob
            rate.is_selected_fob = sale_order in rate.selected_for_sale_orders if sale_order else False

    @api.depends('selected_for_sale_orders', 'active_sale_order_fob')
    def _inverse_is_selected_fob(self):
        """Update the selected_for_sale_orders field based on is_selected_fob value"""
        for rate in self:
            # Skip if we're in an onchange context that's handling this elsewhere
            sale_order = rate.active_sale_order_fob
            if sale_order:
                if rate.is_selected_fob:
                    # Add this sale order to selected ones
                    rate.selected_for_sale_orders = [(4, sale_order.id, 0)]

                    # Deselect other rates for this sale order
                    other_rates = self.search([
                        ('id', '!=', rate.id),
                        ('selected_for_sale_orders', '=', sale_order.id) 
                    ])
                    # Update selected_for_sale_orders instead of writing is_selected_fob
                    other_rates.write({'selected_for_sale_orders': [(3, sale_order.id, 0)]})
                else:
                    # Remove this sale order from selected ones
                    rate.selected_for_sale_orders = [(3, sale_order.id, 0)]

    @api.depends('selected_lad_sale_orders', 'active_sale_order_lod')
    def _compute_is_selected_lod(self):
        for rate in self:
            sale_order = rate.active_sale_order_lod
            rate.is_selected_lod = sale_order in rate.selected_lad_sale_orders if sale_order else False

    @api.depends('selected_lad_sale_orders', 'active_sale_order_lod')
    def _inverse_is_selected_lod(self):
        for rate in self:
            sale_order = rate.active_sale_order_lod
            if sale_order:
                if rate.is_selected_lod:
                    rate.selected_lad_sale_orders = [(4, sale_order.id, 0)]
                    other_rates = self.search([
                        ('id', '!=', rate.id),
                        ('selected_lad_sale_orders', '=', sale_order.id)
                    ])
                    other_rates.write({'selected_lad_sale_orders': [(3, sale_order.id, 0)]})
                else:
                    rate.selected_lad_sale_orders = [(3, sale_order.id, 0)]

    @api.model
    def get_selected_rate_for_sale_order(self, sale_order_id):
        """Return the selected rate for a specific sale order."""
        return self.search([
            ('selected_for_sale_orders', 'in', [sale_order_id])
        ], limit=1)

    def update_transport_fields(self):
        """Forcibly update transport fields from computed values."""
        for record in self:
            if record.transport_city_comp:
                record.transport_city = record.transport_city_comp
            if record.transport_port_comp:
                record.transport_port = record.transport_port_comp
        return True

    @api.onchange('is_distance_based')
    def _onchange_is_distance_based(self):
        self.rate_type = 'scaffold' if self.is_distance_based else 'city'
        
    @api.onchange('distance', 'transport_rates', 'transport_rates.is_selected_fob')
    def _onchange_distance_and_rates(self):
        self._compute_transport_rate_total()
        
    @api.onchange('transport_city_comp')
    def _onchange_transport_city_comp(self):
        if self.transport_city_comp:
            self.transport_city = self.transport_city_comp

    @api.onchange('transport_port_comp')
    def _onchange_transport_port_comp(self):
        if self.transport_port_comp:
            self.transport_port = self.transport_port_comp
            
    @api.onchange('active_sale_order_fob', 'active_sale_order_lod')
    def _onchange_active_sale_order(self):
        if self.active_sale_order_fob or self.active_sale_order_lod:
            self._compute_fob_total()
            self._compute_lod_total()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'rate_type' not in vals:
                is_distance_based = vals.get('is_distance_based', False)
                vals['rate_type'] = 'scaffold' if is_distance_based else 'city'
        return super(TransportRates, self).create(vals_list)
    
    def write(self, vals):
        """Override write to handle special cases for is_selected_fob"""
        # If we're explicitly setting is_selected_fob and in a force_write context
        if 'is_selected_fob' in vals and self.env.context.get('force_write'):
            # Force the field value without triggering compute/inverse
            self.env.cr.execute(
                """UPDATE omnifreight_transport_rates SET is_selected_fob = %s WHERE id = %s""",
                (vals['is_selected_fob'], self.id)
            )
            # Remove the key so it's not processed again
            vals.pop('is_selected_fob')
        
        if 'is_selected_lod' in vals and self.env.context.get('force_write'):
            # Force the field value without triggering compute/inverse
            self.env.cr.execute(
                """UPDATE omnifreight_transport_rates SET is_selected_lod = %s WHERE id = %s""",
                (vals['is_selected_lod'], self.id)
            )
            # Remove the key so it's not processed again
            vals.pop('is_selected_lod')
        
        if 'currency_id' in vals and not vals['currency_id']:
            vals['currency_id'] = self.env.company.currency_id.id
            
            for record in self:
                if not record.currency_id:
                    vals['currency_id'] = self.env.company.currency_id.id
                    
        return super(TransportRates, self).write(vals)

    @api.model
    def force_recompute_from_sale_order(self, sale_order_id):
        """Called from sale.order when fields affecting transport rates change."""
        # Search rates that are related to the sale order in either sales_ids or selected_lad_sale_orders
        if hasattr(sale_order_id, 'origin'):
            sale_order_id = sale_order_id.origin
            if not sale_order_id:
                return True
            
        rates = self.search([
            '|',  # OR condition
            ('sales_ids', 'in', [sale_order_id]),
            ('lod_sales_ids', 'in', [sale_order_id])
        ])
        
        if rates:
            # Modified to track changes in both sales_ids and selected_lad_sale_orders
            rates.modified(['sales_ids', 'lod_sales_ids'])
            
            # Recompute all relevant computed fields
            rates._compute_fob_total()
            rates._compute_lod_total()
            rates._compute_region_name()
            rates._compute_transport_city()
            rates._compute_transport_port()
            rates._compute_active_sale_order_fob()
            rates._compute_active_sale_order_lod()
            
            # Force recomputation of related fields in sale.order.transport.rate
            sale_order = self.env['sale.order'].browse(sale_order_id)
            if sale_order.rate_link_ids:
                sale_order.rate_link_ids._compute_fob_total()
            if sale_order.lod_rate_link_ids:
                sale_order.lod_rate_link_ids._compute_lod_total()
        return True
    
    @api.constrains('valid_until')
    def validation_constraints(self):
        today=fields.Date.today()
        # for rec in self:

        #     if rec.valid_until and rec.valid_until <= today:
        #         raise ValidationError(_('Date cannot be before today'))
            
    @api.depends('valid_until')
    def _compute_expiry_with_warning(self):
        """Compute expiry warning flag based on valid_until date."""
        today = fields.Date.context_today(self)
        for record in self:
            record.show_expiry_warning = record.valid_until and record.valid_until < today
    
    def action_duplicate_rate(self):
        """Duplicate an expired rate with a new valid_until date."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        
        if not self.valid_until or self.valid_until >= today:
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
            'base_price': 0,
            'transport_city': self.transport_city.id,
            'transport_port': self.transport_port.id,
            'rate_type': self.rate_type,
            'subregion_id': self.subregion_id.id,
            'pickup_type': self.pickup_type,
            'transport_city_comp': self.transport_city_comp.id,
            'transport_port_comp': self.transport_port_comp.id,
            'soc_tariff': self.soc_tariff,
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
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Duplicate Rate',
            'res_model': 'omnifreight.transport.rates',
            'res_id': new_rate.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'skip_valid_until_check': True},
        }