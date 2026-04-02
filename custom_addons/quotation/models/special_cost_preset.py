from odoo import api, fields, models
from odoo.exceptions import ValidationError

class SpecialCostPreset(models.Model):
    _name = 'omnifreight.special.cost.preset'
    _description = 'Preset Special Costs'

    name = fields.Char(required=True)
    default_unit_price = fields.Float(string="Default Price/Unit")
    currency_id = fields.Many2one(
        'res.currency', 
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    is_freight_cost = fields.Boolean()
    is_fob_cost = fields.Boolean()
    is_lod_cost = fields.Boolean()
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

    def name_get(self):
        """Show just the name (no details) for dropdown"""
        return [(rec.id, rec.name) for rec in self]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Override to deduplicate by name - only show each service name once, filtered by context"""
        if args is None:
            args = []
        
        # Get context from the view
        context = self._context
        
        # Add filters based on context
        if context.get('default_is_freight_cost') or context.get('parent_is_freight_cost'):
            args.append(('is_freight_cost', '=', True))
            args.append(('is_route_cost', '=', True))
            # Exclude other cost types
            args.append(('is_fob_cost', '=', False))
            args.append(('is_lod_cost', '=', False))
            args.append(('is_port_cost', '=', False))
            args.append(('is_soc_cost', '=', False))
        
        elif context.get('default_is_fob_cost') or context.get('parent_is_fob_cost'):
            args.append(('is_fob_cost', '=', True))
            # Exclude other cost types
            args.append(('is_freight_cost', '=', False))
            args.append(('is_lod_cost', '=', False))
            args.append(('is_port_cost', '=', False))
            args.append(('is_soc_cost', '=', False))
        
        elif context.get('default_is_lod_cost') or context.get('parent_is_lod_cost'):
            args.append(('is_lod_cost', '=', True))
            # Exclude other cost types
            args.append(('is_freight_cost', '=', False))
            args.append(('is_fob_cost', '=', False))
            args.append(('is_port_cost', '=', False))
            args.append(('is_soc_cost', '=', False))
        
        elif context.get('default_is_port_cost') or context.get('parent_is_port_cost'):
            args.append(('is_port_cost', '=', True))
            # Exclude other cost types
            args.append(('is_freight_cost', '=', False))
            args.append(('is_fob_cost', '=', False))
            args.append(('is_lod_cost', '=', False))
            args.append(('is_soc_cost', '=', False))
        
        elif context.get('default_is_soc_cost') or context.get('parent_is_soc_cost'):
            args.append(('is_soc_cost', '=', True))
            # Exclude other cost types
            args.append(('is_freight_cost', '=', False))
            args.append(('is_fob_cost', '=', False))
            args.append(('is_lod_cost', '=', False))
            args.append(('is_port_cost', '=', False))
        
        # First, get all records matching the search criteria
        records = self.search(args, limit=None)
        
        if not records:
            return []
        
        # Deduplicate by name - keep the most generic one (no container_type, no route/port)
        seen_names = set()
        deduplicated_records = []
        
        # Sort records: generic ones first (no container_type, no route/port), then specific ones
        sorted_records = sorted(records, 
            key=lambda r: (
                0 if r.container_type else 1, 
                0 if r.route_id or r.port_id else 1,  
                -r.id
            )
        )
        
        for record in sorted_records:
            if record.name not in seen_names:
                deduplicated_records.append(record)
                seen_names.add(record.name)
        
        # Filter by search term if provided
        if name:
            deduplicated_records = [r for r in deduplicated_records if name.lower() in r.name.lower()]
        
        # Apply limit
        deduplicated_records = deduplicated_records[:limit]
        
        return [(r.id, r.name) for r in deduplicated_records]

    @api.model
    def name_create(self, name):
        """Create a new preset with values from context when user enters a new name"""
        vals = {'name': name}
        ctx = self.env.context

        # -------------------------------------------------
        # Boolean flags (parent_ takes precedence)
        # -------------------------------------------------
        def _ctx_bool(parent_key, default_key):
            if parent_key in ctx:
                return ctx[parent_key]
            return ctx.get(default_key)

        vals['is_fob_cost'] = _ctx_bool('parent_is_fob_cost', 'default_is_fob_cost') or False
        vals['is_freight_cost'] = _ctx_bool('parent_is_freight_cost', 'default_is_freight_cost') or False
        vals['is_lod_cost'] = _ctx_bool('parent_is_lod_cost', 'default_is_lod_cost') or False
        vals['is_port_cost'] = _ctx_bool('parent_is_port_cost', 'default_is_port_cost') or False
        vals['is_soc_cost'] = _ctx_bool('parent_soc', 'default_is_soc_cost') or False
        vals['is_route_cost'] = _ctx_bool('parent_is_route_cost', 'default_is_route_cost') or False

        # -------------------------------------------------
        # Container type
        # -------------------------------------------------
        container_type = ctx.get('parent_container_type') or ctx.get('default_container_type')
        if container_type:
            vals['container_type'] = container_type

        # -------------------------------------------------
        # Port (allowed for FOB / LOD / Port / SOC)
        # -------------------------------------------------
        port_id = (
            ctx.get('parent_port_id')
            or ctx.get('default_port_id')
            or ctx.get('default_port')
            or ctx.get('default_transport_port')
        )
        if port_id:
            vals['port_id'] = port_id

        # -------------------------------------------------
        # Route — ONLY for Freight costs
        # -------------------------------------------------
        route_id = ctx.get('parent_route_id') or ctx.get('default_route_id')

        if vals.get('is_freight_cost'):
            if route_id:
                vals['route_id'] = route_id
            else:
                # Fallback: derive from sale order
                active_id = ctx.get('active_id')
                active_model = ctx.get('active_model')

                if active_model == 'sale.order' and active_id:
                    sale_order = self.env['sale.order'].browse(active_id)
                    route = sale_order._get_current_route()
                    if not route:
                        raise ValidationError("Freight cost presets require a route.")
                    vals['route_id'] = route.id
                else:
                    raise ValidationError("Freight cost presets require a route.")
        else:
            # FOB / LOD must NEVER carry a route
            vals.pop('route_id', None)

        # -------------------------------------------------
        # Fallbacks from Sale Order (non-route fields only)
        # -------------------------------------------------
        if ctx.get('active_model') == 'sale.order' and ctx.get('active_id'):
            sale_order = self.env['sale.order'].browse(ctx['active_id'])

            if not vals.get('container_type') and sale_order.container_type:
                vals['container_type'] = sale_order.container_type

            if not vals.get('port_id') and sale_order.port_of_loading:
                vals['port_id'] = sale_order.port_of_loading.id

        return self.create(vals).name_get()[0]
    
    @api.constrains('is_port_cost', 'port_id', 'is_soc_cost', 'container_type')
    def _check_port_and_soc_cost(self):
        for rec in self:
            if rec.is_port_cost and not rec.port_id:
                raise ValidationError("If 'Port Cost' is checked, you must select a Port.")
            if (rec.is_port_cost or rec.is_soc_cost) and not rec.container_type:
                raise ValidationError("Port costs and SOC costs must specify a container type.")