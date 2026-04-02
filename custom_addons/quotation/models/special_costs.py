from odoo import api, fields, models
from odoo.exceptions import ValidationError

class SpecialCosts(models.Model):
    
    # Name and description of the model
    _name = 'omnifreight.special.costs'
    _description = 'Special Costs for product'

    name = fields.Char(string="Name of Cost", compute="_compute_name", readonly=False, store=True)
    # Unit(s) of the extra cost services
    omnifreight_extra_cost_units = fields.Integer(string="Unit", default=1)
    
    # Cost of the service per unit
    omnifreight_extra_cost_price_per_unit = fields.Float(string="Unit Price")
    
    # Cost value associated with the special cost
    price = fields.Float(string="Price", compute="_compute_omnifreight_extra_cost_total_price")
    currency_id = fields.Many2one(
        'res.currency', 
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    # Link to the related sales order where this special cost applies
    sales_order_id = fields.Many2one('sale.order', string="Sales Order")
    additional_cost_id = fields.Many2one('omnifreight.special.cost.preset', string="EXTRA FREIGHT & MISCELLANEOUS COSTS")
    
    # Specify which part of the quotation this special cost belongs to
    is_fob_cost = fields.Boolean(string="FOB")
    is_freight_cost = fields.Boolean(string="Freight")
    is_lod_cost = fields.Boolean(string="Destination")

    # Add costs related to ports
    is_port_cost = fields.Boolean(string="Port Cost")
    is_route_cost = fields.Boolean(string="Route Cost")
    port_id = fields.Many2one('port', string="Port")
    container_type = fields.Selection(
        selection=lambda self: self.env['omnifreight.package.details'].CONTAINER_TYPES,
        string="Container Size"
    )
    # SOC (Shipper's Owned Container) related cost
    is_soc_cost = fields.Boolean(string="SOC Cost", help="Cost related to Shipper's Owned Container")
    route_id = fields.Many2one('omnifreight.route', string="Route")

    @api.depends('omnifreight_extra_cost_units', 'omnifreight_extra_cost_price_per_unit')
    def _compute_omnifreight_extra_cost_total_price(self):
        """Computes for the total price based on the units given and its price per unit"""
        for record in self:
            units = record.omnifreight_extra_cost_units or 0
            price_per_unit = record.omnifreight_extra_cost_price_per_unit or 0.0
            record.price = units * price_per_unit

    @api.depends('additional_cost_id')
    def _compute_name(self):
        """Computes the name of the special cost based on the additional cost preset"""
        for record in self:
            record.name = record.additional_cost_id.name

    @api.onchange('sales_order_id')
    def _onchange_sales_order_id(self):
        """Set currency from sale order when sales order changes"""
        for rec in self:
            order = rec.sales_order_id
            if not order:
                return

            rec.currency_id = order.currency_id

            if not rec.port_id and order.port_of_loading:
                rec.port_id = order.port_of_loading

            if not rec.container_type and order.container_type:
                rec.container_type = order.container_type

            # For freight costs, get route from sale order
            if rec.is_freight_cost and not rec.route_id:
                route = order._get_current_route()
                if route:
                    rec.route_id = route
                
            # Trigger price lookup after setting values
            if rec.additional_cost_id:
                rec._onchange_load_combo_price()
                
     # -----------------------------
    # ONCHANGE TO LOAD PRICE
    # -----------------------------
    @api.onchange('additional_cost_id', 'sales_order_id', 'port_id', 'container_type', 'route_id')
    def _onchange_load_combo_price(self):
        """Onchange to load the price based on selected additional cost and related fields"""
        for rec in self:
            
            current_price = rec.omnifreight_extra_cost_price_per_unit or 0.0
        
            # If user already set a price manually, don't override it
            if current_price != 0.0:
                return
        
            # Reset to 0 initially
            rec.omnifreight_extra_cost_price_per_unit = 0.0

            if not rec.additional_cost_id:
                return

            # Fetch missing values from sale order
            if rec.sales_order_id:
                if not rec.container_type and rec.sales_order_id.container_type:
                    rec.container_type = rec.sales_order_id.container_type
            
                # For freight costs, get route if missing
                if rec.is_freight_cost and not rec.route_id:
                    route = rec.sales_order_id._get_current_route()
                    if route:
                        rec.route_id = route

                # For non-freight costs, get port if missing
                if not rec.is_freight_cost and not rec.port_id and rec.sales_order_id.port_of_loading:
                    rec.port_id = rec.sales_order_id.port_of_loading

            # Now we need to find the ACTUAL preset record (not just the generic one)
            # Since additional_cost_id might be a generic deduplicated record
            domain = [('name', '=', rec.additional_cost_id.name)]
        
            # Add cost type filter
            domain.append(('is_freight_cost', '=', rec.is_freight_cost))
        
            # Build a list of possible presets matching this service name
            all_presets = self.env['omnifreight.special.cost.preset'].search(domain)

            if not all_presets:
                return
        
            # First, try to find a PERFECT match (container_type AND route/port)
            perfect_match = None
        
            for preset in all_presets:
                # Check if this is a perfect match
                is_perfect_match = True
            
                # Check container type (both must match or both be None/False)
                if preset.container_type != rec.container_type:
                    is_perfect_match = False
            
                # Check route/port based on cost type
                if rec.is_freight_cost:
                    if preset.route_id != rec.route_id:
                        is_perfect_match = False
                    if preset.port_id:  # Freight costs shouldn't have port_id
                        is_perfect_match = False
                else:
                    if preset.port_id != rec.port_id:
                        is_perfect_match = False
                    if preset.route_id:  # Non-freight costs shouldn't have route_id
                        is_perfect_match = False
            
                if is_perfect_match:
                    perfect_match = preset
                    break
        
            if perfect_match:
                if perfect_match.default_unit_price:
                    rec.omnifreight_extra_cost_price_per_unit = perfect_match.default_unit_price
                   
                    # Also update the additional_cost_id to point to the actual matched preset
                    rec.additional_cost_id = perfect_match
    
    # -----------------------------
    # PERSIST COMBO PRICE
    # -----------------------------
    def _persist_combo_price(self):
        for rec in self:
            if not rec.additional_cost_id or not rec.omnifreight_extra_cost_price_per_unit:
                continue

            # --- ensure container_type and route/port are set ---
            if rec.is_freight_cost:
                if not rec.container_type and rec.sales_order_id:
                    rec.container_type = rec.sales_order_id.container_type
                if not rec.route_id and rec.sales_order_id:
                    rec.route_id = rec.sales_order_id._get_current_route()
            else:
                if not rec.container_type and rec.sales_order_id:
                    rec.container_type = rec.sales_order_id.container_type
                if not rec.port_id and rec.sales_order_id:
                    rec.port_id = rec.sales_order_id.port_of_loading

            # --- First, try to find the most specific match ---
            existing_preset = None
        
            # Try exact match first (with container_type)
            if rec.container_type:
                domain = [
                    ('name', '=', rec.additional_cost_id.name),
                    ('container_type', '=', rec.container_type),
                    ('is_freight_cost', '=', rec.is_freight_cost),
                    ('is_fob_cost', '=', rec.is_fob_cost),
                    ('is_lod_cost', '=', rec.is_lod_cost),
                    ('is_port_cost', '=', rec.is_port_cost),
                    ('is_soc_cost', '=', rec.is_soc_cost),
                ]
            
                if rec.is_freight_cost:
                    domain.append(('route_id', '=', rec.route_id.id if rec.route_id else False))
                    domain.append(('port_id', '=', False))
                else:
                    domain.append(('port_id', '=', rec.port_id.id if rec.port_id else False))
                    domain.append(('route_id', '=', False))
            
                existing_preset = self.env['omnifreight.special.cost.preset'].search(domain, limit=1)
        
            # If no exact match found, look for a generic preset (without container_type)
            if not existing_preset:
                domain = [
                    ('name', '=', rec.additional_cost_id.name),
                    ('container_type', '=', False),  # Look for generic presets
                    ('is_freight_cost', '=', rec.is_freight_cost),
                    ('is_fob_cost', '=', rec.is_fob_cost),
                    ('is_lod_cost', '=', rec.is_lod_cost),
                    ('is_port_cost', '=', rec.is_port_cost),
                    ('is_soc_cost', '=', rec.is_soc_cost),
                ]
            
                if rec.is_freight_cost:
                    domain.append(('route_id', '=', False))  # Generic freight should have no route
                    domain.append(('port_id', '=', False))
                else:
                    domain.append(('port_id', '=', False))  # Generic non-freight should have no port
                    domain.append(('route_id', '=', False))
            
                existing_preset = self.env['omnifreight.special.cost.preset'].search(domain, limit=1)
        
            if existing_preset:
                # Update the existing preset with the new specific values
                update_vals = {
                    'default_unit_price': rec.omnifreight_extra_cost_price_per_unit,
                    'currency_id': rec.currency_id.id,
                }
            
                # Only update container_type if it's not already set
                if rec.container_type and not existing_preset.container_type:
                    update_vals['container_type'] = rec.container_type
            
                # Update route/port based on cost type
                if rec.is_freight_cost:
                    if rec.route_id and not existing_preset.route_id:
                        update_vals['route_id'] = rec.route_id.id
                    if not existing_preset.port_id:
                        update_vals['port_id'] = False
                else:
                    if rec.port_id and not existing_preset.port_id:
                        update_vals['port_id'] = rec.port_id.id
                    if not existing_preset.route_id:
                        update_vals['route_id'] = False
            
                existing_preset.write(update_vals)
            else:
                # create new preset
                preset_vals = {
                    'name': rec.additional_cost_id.name,
                    'default_unit_price': rec.omnifreight_extra_cost_price_per_unit,
                    'currency_id': rec.currency_id.id,
                    'is_freight_cost': rec.is_freight_cost,
                    'is_fob_cost': rec.is_fob_cost,
                    'is_lod_cost': rec.is_lod_cost,
                    'is_port_cost': rec.is_port_cost,
                    'is_soc_cost': rec.is_soc_cost,
                    'is_route_cost': rec.is_freight_cost,
                    'port_id': rec.port_id.id if rec.port_id else False,
                    'container_type': rec.container_type,
                    'route_id': rec.route_id.id if rec.route_id else False,
                }
                new_preset = self.env['omnifreight.special.cost.preset'].create(preset_vals)
    
    # -----------------------------
    # CREATE METHOD
    # -----------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Trigger price lookup for all new records
        for record in records:
            if record.additional_cost_id:
                record._onchange_load_combo_price()
        
        records._persist_combo_price()
        return records

    # -----------------------------
    # WRITE METHOD
    # -----------------------------
    def write(self, vals):
        res = super().write(vals)
        
        # If additional_cost_id changed, trigger price lookup
        if 'additional_cost_id' in vals:
            for rec in self:
                rec._onchange_load_combo_price()
        # If other relevant fields changed and price is 0, trigger lookup
        elif 'omnifreight_extra_cost_price_per_unit' not in vals:
            relevant_fields = {'port_id', 'container_type', 'route_id', 'sales_order_id'}
            if any(field in vals for field in relevant_fields):
                for rec in self:
                    if rec.omnifreight_extra_cost_price_per_unit == 0.0:
                        rec._onchange_load_combo_price()
        
        self._persist_combo_price()
        return res