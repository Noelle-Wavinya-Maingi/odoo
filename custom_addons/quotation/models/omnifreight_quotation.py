from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from .currency_conversion_mixin import OmniCurrencyConversion
from .set_quote import SetQuote
from datetime import date

class OmnifreightQuotation(models.Model, OmniCurrencyConversion, SetQuote):
    _inherit = 'sale.order'
    # The route, a combination of POD and POL
    route_id = fields.Many2one('omnifreight.route', string='Route', compute="_compute_route", store=True)
    # Link to the 'omnifreight.package.details' model
    package_details_id = fields.Many2one('omnifreight.package.details', string="Package Details")
    # Editable fields for package details directly in the quotation
    container_type = fields.Selection(
        selection=lambda self: self.env['omnifreight.package.details'].CONTAINER_TYPES,
        string="Container Size"
    )
    contents = fields.Many2many('omnifreight.cargo.type', string="Cargo Type", required=True)
    content_classification = fields.Selection(
        selection=lambda self: self.env['omnifreight.package.details'].CONTENT_CLASSIFICATION,
        string="Content Classification"
    )
    soc = fields.Boolean(string="SOC")
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterms From')
    incoterm_to_id = fields.Many2one('account.incoterms', string='Incoterms To')

    client_class = fields.Selection(related='partner_id.ratings_tag', string="Client Class", store=True)
    client_volume = fields.Integer()
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id.id, readonly=False)
    # The cost set by a user
    full_service_cost = fields.Monetary(string="Full Service Cost", currency_field='currency_id', help="The amount we want to charge the customer for this shipment")
    # The total margin for the set price
    set_price_cost_margin = fields.Float(string="Quotation Margin", compute="_compute_set_price_margins", store=True, readonly=True)
    # The total margin percentage for the set price
    set_price_margin_percentage = fields.Float(string="Quotation Margin Percentage (%)", compute="_compute_set_price_margins", store=True, readonly=True)
    # Computed total estimated cost for the full service
    full_service_cost_est = fields.Float(string="Full Service Cost Est", compute="_compute_full_service_cost_est")
    
    # Computed total margin for the full service
    full_service_cost_margin = fields.Float(string="Total Margin Cost", compute="_compute_full_service_cost_margin")
    #The sum of all service costs without margins
    service_cost = fields.Float(string="Service Cost", compute="_compute_service_cost")
    # The total margin in percentage
    full_margin_percentage = fields.Float(string="Total Margin Percentage (%)", compute="_compute_full_service_cost_margin")
    

    port_of_loading = fields.Many2one('port', string="POL")
    port_of_dispatch= fields.Many2one('port', string="POD")
    
    @api.constrains('port_of_loading', 'port_of_dispatch')
    def _check_ports_different(self):
        """Ensure that port of loading and port of dispatch are different."""
        for order in self:
            if order.port_of_loading and order.port_of_dispatch:
                if order.port_of_loading.id == order.port_of_dispatch.id:
                    raise ValidationError(
                        "Port of Loading and Port of Destination cannot be the same. Please select different ports."
                    )
    # Service Details - FOB
    is_fob = fields.Boolean(string='FOB', default=True)
    # Service Details - Freight
    is_freight = fields.Boolean(string='Freight')
    # Service Details - Local at Destination
    is_lod = fields.Boolean(string='Destination')
    # Only this determines the service name
    quote_type = fields.Selection([
        ('fob_freight', 'FOB + Freight'),
        ('fob_only', 'FOB Only'),
        ('freight_only', 'Freight Only'),
        ('lod_only', 'DAP Only'),
        ('fob_freight_lod', 'FOB + Freight + DAP'),
        ('freight_dap', 'Freight + DAP'),
    ], string="Service Scope")
    
    quote_line_mode = fields.Selection([
        ('single', 'Single Line (Combined)'),
        ('individual', 'Individual Lines (Per Service)'),
        ('dap+freight_fob', 'Two Lines (FOB+FREIGHT, DAP)')
    ], string="Quote Line Mode", default='single',
       help="Choose whether to show a single combined line or individual lines for each service when multiple services are selected.")
    
    ###
    # THESE FIELDS CONTROL FORM AND TAB VISIBILITY
    # They are not stored in the database, but computed dynamically based on the quote type and selected services
    # ##
    show_pricing_tab = fields.Boolean(
        string="Show Pricing Tab",
        compute="_compute_show_pricing_tab",
        store=False
    )
    show_fob_section = fields.Boolean(compute="_compute_show_fob_section", store=False)
    show_freight_section = fields.Boolean(compute="_compute_show_freight_section", store=False)
    show_lod_section = fields.Boolean(compute="_compute_show_lod_section", store=False)

    # Fields to track multiple containers per quote
    no_of_containers= fields.Integer(default=1, help="Update the number of containers for multiple containers")

    has_hazardous_content = fields.Boolean(string="Hazardous Content", compute="_compute_has_hazardous_content")
    hide_order_lines = fields.Boolean(compute="_compute_hide_order_lines", store=False)

        # --- Quote Type Configuration Map ---
    QUOTE_TYPE_MAP = {
        'fob_freight': {
            'service_type': 'FOB+FREIGHT',
            'description': "Coordination of your shipment from FOT (free on truck) supplier's premises to port of destination.",
            'is_fob': True, 'is_freight': True, 'is_lod': False,
        },
        'fob_only': {
            'service_type': 'FOB',
            'description': "Supervision and coordination of FOB export handling at origin",
            'is_fob': True, 'is_freight': False, 'is_lod': False,
        },
        'freight_only': {
            'service_type': 'FREIGHT',
            'description': "Arrangement of ocean freight carriage (as freight forwarder)",
            'is_fob': False, 'is_freight': True, 'is_lod': False,
        },
        'lod_only': {
            'service_type': 'DAP',
            'description': "Management of post-arrival logistics services from port of discharge to final delivery (Free on Truck)",
            'is_fob': False, 'is_freight': False, 'is_lod': True,
        },
        'fob_freight_lod': {
            'service_type': 'FOB + Freight + DAP',
            'description': "Coordination of your shipment from FOT (free on truck) supplier's premises to final delivery (Free On Truck).",
            'is_fob': True, 'is_freight': True, 'is_lod': True,
        },
        'freight_dap': {
            'service_type': 'Freight + DAP',
            'description': "Coordination of your shipment from FOT (free on truck) supplier's premises to final delivery (Free On Truck).",
            'is_fob': False, 'is_freight': True, 'is_lod': True,
        },
    }

    @api.depends('content_classification')
    def _compute_has_hazardous_content(self):
        for order in self:
            if order.content_classification == 'hazardous':
                order.has_hazardous_content = True
            else:
                order.has_hazardous_content = False
    
    @api.depends('fob_total_cost_est', 'lod_total_cost_est', 'total_cost_est')
    def _compute_full_service_cost_est(self):
        """
        Computes the total estimated cost for the full service by summing up:
        - FOB (Free On Board) total estimated costs
        - LOD (Local at Destination) total estimated costs
        - Freight total estimated costs
        """
        for order in self:
            order.full_service_cost_est = order.fob_total_cost_est + order.lod_total_cost_est + order.total_cost_est

    @api.depends('total_freight_margin', 'fob_total_margin', 'lod_total_margin',
             'freight_base_cost', 'fob_base_cost', 'lod_total_cost')
    def _compute_full_service_cost_margin(self):
        """
        Calculates margin and margin percentage based only on the services used (non-zero margin).
        """
        for order in self:
            freight_margin = order.total_freight_margin or 0.0
            fob_margin = order.fob_total_margin or 0.0
            lod_margin = order.lod_total_margin or 0.0

            # Use base costs (without margins) for percentage calculation
            freight_base_cost = order.freight_base_cost or 0.0
            fob_base_cost = order.fob_base_cost or 0.0
            lod_base_cost = order.lod_total_cost or 0.0

            # Match only services that are used (non-zero margin)
            services = [
                (freight_margin, freight_base_cost),
                (fob_margin, fob_base_cost),
                (lod_margin, lod_base_cost)
            ]
            active = [(m, c) for m, c in services if m != 0.0]

            total_margin = sum(m for m, _ in active)
            total_base_cost = sum(c for _, c in active)

            order.full_service_cost_margin = total_margin
            order.full_margin_percentage = (total_margin / total_base_cost) * 100 if total_base_cost > 0 else 0.0

    @api.depends('fob_base_cost', 'freight_base_cost', 'lod_total_cost')
    def _compute_service_cost(self):
        """
        Computes the total service cost by summing:
        - FOB base cost
        - Freight base cost
        - LOD base cost
        """
        for order in self:
            order.service_cost = order.fob_base_cost + order.freight_base_cost + order.lod_total_cost


    @api.depends('full_service_cost', 'service_cost')  
    def _compute_set_price_margins(self):
        """
        Compares the price that a user has set, with what the price calculator has suggested and 
        gives the margin
        """
        for order in self:
            service_cost = order.service_cost or 0.0
            set_price = order.full_service_cost if order.full_service_cost else 0.0
            order.set_price_cost_margin = (set_price - service_cost)
            order.set_price_margin_percentage = (((set_price - service_cost) / service_cost) * 100 if service_cost > 0 else 0.0)

    @api.onchange(
        'fob_total_cost_est', 'lod_total_cost_est', 'total_cost_est',
        'full_service_cost', 'full_service_cost_est'
    )
    def _onchange_pricing_totals(self):
        # Recompute all parent totals and margins
        self._compute_full_service_cost_est()
        self._compute_full_service_cost_margin()
        self._compute_service_cost()
        self._compute_set_price_margins()        


 # --- Quote Type Change Handler ---
    @api.onchange('quote_type', 'quote_line_mode')
    def _onchange_quote_type(self):
        # In an onchange context, self is a singleton record.
        # Using self directly is cleaner and safer than looping.

        # Guard against running when quote_type is not set or cleared.
        if not self.quote_type:
            # If quote_type is cleared, also clear related fields and lines.
            self.is_fob = False
            self.is_freight = False
            self.is_lod = False
            self.order_line = self.order_line.filtered(
                lambda l: l.product_id.categ_id.name != 'Omnifreight Services'
            )
            return

        config = self.QUOTE_TYPE_MAP.get(self.quote_type, {})
        self.is_fob = config.get('is_fob', False)
        self.is_freight = config.get('is_freight', False)
        self.is_lod = config.get('is_lod', False)

        # Automatically update order lines.
        self.set_quote()

    # --- Main Quote Setup Logic ---
    def set_quote(self):
        super().set_quote()


    # Helpers

    def _map_quote_type_to_service_scope(self, quote_type):
        """Map quote_type to service_scope for BOM lookup."""
        mapping = {
            'fob_only': 'fob',
            'fob_freight': 'fob_freight',
            'freight_only': 'freight',
            'lod_only': 'lod',
            'fob_freight_lod': 'fob_freight_lod',
            'freight_dap': 'freight_lod',
        }
        return mapping.get(quote_type, quote_type)
    
    def _get_bom_for_service_scope(self, quote_type):
        """Get BOM based on service scope for manufacturing integration."""
        # Map quote_type to service_scope
        service_scope = self._map_quote_type_to_service_scope(quote_type)
        
        # Try to find BOM with matching service_scope first (service type for omni_ops)
        try:
            bom = self.env['mrp.bom'].search([
                ('product_tmpl_id.name', '=', 'Freight Forwarding Service'),
                ('service_scope', '=', service_scope),
                ('type', '=', 'service')
            ], limit=1)
        except Exception:
            bom = self.env['mrp.bom']
        
        # If no BOM found with service_scope, try to find any service BOM for the product
        if not bom:
            bom = self.env['mrp.bom'].search([
                ('product_tmpl_id.name', '=', 'Freight Forwarding Service'),
                ('type', '=', 'service')
            ], limit=1)
        
        # If still no BOM found, try to find any BOM for the product (any type)
        if not bom:
            bom = self.env['mrp.bom'].search([
                ('product_tmpl_id.name', '=', 'Freight Forwarding Service')
            ], limit=1)
        
        if not bom:
            raise UserError(f"No BOM found for Freight Forwarding Service product with service scope '{service_scope}'. Please create a BOM for this product.")
        
        return bom
    
    
    #ONLY SHOW THE PRICING TAB IF COSTS TO ALL SELECTED SERVICES ARE SET   
    @api.depends(
        'is_fob', 'is_freight', 'is_lod',
        'rate_link_ids',
        'known_price_lines',
        'lod_rate_link_ids'
    )
    def _compute_show_pricing_tab(self):
        for order in self:
            if not order.is_fob and not order.is_freight and not order.is_lod:
                order.show_pricing_tab = False
                continue
            
            if order.pickup_type == 'no_pickup':
                order.show_pricing_tab = True
                continue

            show = True
            if order.is_fob and not order.rate_link_ids.filtered(lambda l: l.is_selected_fob):
                show = False
            
            if order.is_freight and not order.known_price_lines.filtered(lambda l: l.is_selected):
                show = False

            if order.is_lod and not order.lod_rate_link_ids.filtered(lambda l: l.is_selected_lod):
                show = False
            
            order.show_pricing_tab = show
    
    ##
    # Methods to compute visibility of sections based on selected services
    # The goal is to show/hide sections based on whether the service is selected and the relevant region or route is set
    ##
    @api.depends('is_fob', 'pickup_region')
    def _compute_show_fob_section(self):
        for order in self:
            order.show_fob_section = bool(order.is_fob and order.pickup_region and order.pickup_type)

    @api.depends('is_freight', 'route_id')
    def _compute_show_freight_section(self):
        for order in self:
            order.show_freight_section = bool(order.is_freight and order.route_id)

    @api.depends('is_lod', 'delivery_region')
    def _compute_show_lod_section(self):
        for order in self:
            order.show_lod_section = bool(order.is_lod and order.delivery_region )

    @api.depends('quote_type', 'validity_date')
    def _compute_hide_order_lines(self):
        for order in self:
            order.hide_order_lines = not (bool(order.quote_type) and bool(order.validity_date))   

    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        """Clear full_service_cost when currency changes to avoid confusion."""
        if self.full_service_cost:
            self.full_service_cost = 0.0
    
    # === MANUFACTURING ORDER INTEGRATION ===
    
    def action_confirm(self):
        """Override the public action_confirm method."""
        return super().action_confirm()
    
    def _action_confirm(self):
        """Override to create manufacturing orders for freight forwarding services."""
        # Call parent method first to handle standard confirmation
        result = super()._action_confirm()
        
        # Create manufacturing orders for freight forwarding services
        for order in self:
            if order.quote_type and order.order_line:
                order._create_manufacturing_orders()
        
        return result
    
    def _create_manufacturing_orders(self):
        """Create manufacturing orders for freight forwarding services."""
        self.ensure_one()
        
        # Get the Freight Forwarding Service product
        freight_product = self.env['product.product'].search([
            ('name', '=', 'Freight Forwarding Service')
        ], limit=1)
        
        if not freight_product:
            return
        
        # Find the BOM for the current service scope
        try:
            bom = self._get_bom_for_service_scope(self.quote_type)
        except UserError:
            return
        
        # Check order lines
        freight_lines = self.order_line.filtered(lambda l: l.product_id == freight_product)
        
        if not freight_lines:
            return
        
        # Create manufacturing order for each order line with freight product
        for line in freight_lines:
            if line.product_uom_qty > 0:
                mo_vals = {
                    'product_id': freight_product.id,
                    'product_qty': line.product_uom_qty,
                    'product_uom_id': line.product_uom_id.id,
                    'bom_id': bom.id,
                    'origin': self.name,
                    'sale_line_id': line.id,
                    'company_id': self.company_id.id,
                }
                
                # Create the manufacturing order
                mo = self.env['mrp.production'].create(mo_vals)
                
                # Link the manufacturing order to the sale order
                mo.sale_line_id = line.id
                
                # Confirm the manufacturing order
                mo.action_confirm()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._ensure_package_details_record()
        return orders

    def write(self, vals):
        result = super().write(vals)
        for order in self:
            order._ensure_package_details_record()
        return result

    def _ensure_package_details_record(self):
        """Ensure package details record exists and is synchronized"""
        if (self.container_type or self.contents or 
            self.content_classification or self.soc):
            
            if not self.package_details_id:
                # Create new package details record
                package_vals = {
                    'container_type': self.container_type,
                    'contents': [(6, 0, self.contents.ids)],
                    'content_classification': self.content_classification,
                    'soc': self.soc,
                }
                package_details = self.env['omnifreight.package.details'].create(package_vals)
                self.package_details_id = package_details.id
            else:
                # Update existing package details record
                self.package_details_id.write({
                    'container_type': self.container_type,
                    'contents': [(6, 0, self.contents.ids)],
                    'content_classification': self.content_classification,
                    'soc': self.soc,
                })
                
    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        # Set validity_date to today when creating a new quotation
        if 'validity_date' in fields_list:
            defaults['validity_date'] = date.today()
        return defaults
