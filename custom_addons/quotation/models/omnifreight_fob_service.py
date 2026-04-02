from odoo import api, fields, models
from .omnifreight_quotation_computation import OmnifreightQuotationComputation
from .omnifreight_quotation_onchange import OmnifreightQuotationOnchange

class OmnifreightFobService(models.Model, OmnifreightQuotationComputation, OmnifreightQuotationOnchange):
    _inherit = 'sale.order'
    _description = 'Omnifreight Quotation'
    # FOB-specific fields
    PICKUP_TYPES = [
        ('immediate_on_trailer', 'Immediate loading / On trailer'),
        ('interval_on_trailer', 'Loading with Interval / On trailer'),
        ('immediate_on_sidebar', 'Immediate loading / Sideloader'),
        ('interval_on_sidebar', 'Loading with Interval / Sideloader'),
        ('one_way_on_trailer', 'One Way / On Trailer'),
        ('one_way_on_sideloader', 'One Way / Sideloader'),
        ('no_pickup', 'No Pickup'),
    ]
    
    fob_special_costs_id = fields.One2many(
        'omnifreight.special.costs', 
        'sales_order_id', 
        string="Special Costs(FOB)", 
        domain=[('is_fob_cost', '=', 'True')], 
        context={'default_is_fob_cost': True, 'default_is_port_cost': True, 'default_is_freight_cost': False, 'default_is_lod_cost': False, 'default_is_soc_cost': False})
    fob_selected_haulage = fields.Float(string="FOB Selected Haulier", compute="_compute_fob_selected_haulier", store=True)
    fob_selected_haulage_currency = fields.Many2one('res.currency', string="FOB Rate Currency", compute="_compute_fob_selected_haulier", store=True)
    fob_risk_percentage = fields.Integer(string="FOB Margin (%)", default = 0.0, help="Margin percentage applied to the haulage costs.")
    fob_total_cost_est = fields.Float(string="FOB Total Incl. Margin", compute="_compute_fob_total_cost_est")
    fob_misc_cost = fields.Integer(string="FOB Extra Costs", compute="_compute_fob_misc_costs")
    fob_base_cost = fields.Float(string="Hauling Fee", compute="_compute_fob_total_cost_est")
    fob_costs_sum = fields.Float(string="FOB Total Cost", compute="_compute_fob_total_cost_est", help="Total cost of haulage and additional costs.")

    # Transport rates and FOB fields
    transport_rates = fields.Many2many('omnifreight.transport.rates','sale_order_fob_transport_rates_rel',
        'order_id', 'rate_id', string="Transport rates(FOB)")
    selected_transport_rate_id = fields.Many2one('omnifreight.transport.rates', string="Selected Transport Rate",
        compute="_compute_selected_transport_rate", store=True)
    transport_rate_total = fields.Integer(string="Transport Rate Total", compute="_compute_transport_rate_total", store=True)
    rate_link_ids = fields.One2many('sale.order.transport.rate', 'order_id', copy=False, domain=[('is_hidden', '=', False)])
    filtered_rate_link_ids = fields.One2many('sale.order.transport.rate', 'order_id', 
                                           string="Filtered Transport Rates")
    is_fob = fields.Boolean(string='FOB', default=True)
    pickup_region = fields.Char(string='Pickup Region', compute="_compute_pickup_region", store=True)
    city_id = fields.Many2one('unloc.city', string='City ID', domain="[('country_id', '=?', service_country_id)]")
    
    distance = fields.Integer(string='Distance')
    pickup_type = fields.Selection(PICKUP_TYPES, string='Pickup Type')

    zip_code_id = fields.Many2one(
        'unloc.city.zip',
        domain="[('un_city_id', '=', city_id)]",
        context= {'default_un_city_id': city_id, 'create': True, 'no_open': True,}
    )

    service_country_id = fields.Many2one('unloc.country', string="Country")
    fob_total_margin = fields.Float(string="FOB Margin", compute="_compute_fob_total_cost_est")

    @api.onchange('service_country_id', 'city_id', 'port_of_loading', 'container_type', 'is_fob')
    def _onchange_location_fields(self):
        for order in self:
            if not order.is_fob:
                return
            
            # Only proceed if all three location fields are set
            if not (order.service_country_id and order.city_id and order.port_of_loading and order.container_type):
                order.rate_link_ids = [(5, 0, 0)]
                order.transport_rates = False
                return

            order.rate_link_ids = [(5, 0, 0)]
            order.transport_rates = False

            domain = []
            region = None

            # Match region from subregion
            if order.service_country_id.subregion_id:
                subregion = order.service_country_id.subregion_id
                region = self.env['haulier.region'].search(
                    [('name', '=ilike', subregion.name.strip())], limit=1
                )
                if region:
                    domain.append(('haulier_region_ids', 'in', [region.id]))
                else:
                    return
            else:
                return

            domain += [
                ('transport_city', '=', order.city_id.id),
                ('transport_port', '=', order.port_of_loading.id),
                ('container_type', '=', order.container_type),
            ]
            # Only filter by pickup_type if it's set on the order
            if order.pickup_type:
                domain.append(('pickup_type', '=', order.pickup_type))

            # Search for both valid and expired rates
            all_rates = self.env['omnifreight.transport.rates'].with_context(
                active_id=order.id,
                active_model='sale.order',
                active_view='fob'
            ).search(domain)

            if all_rates:
                from .rate_filtering_utils import filter_one_rate_per_company
                filtered_rates = filter_one_rate_per_company(
                    all_rates,
                    company_field='supplier_id',
                    valid_until_field='valid_until',
                    write_date_field='write_date'
                )
                
                order.transport_rates = filtered_rates
                new_lines = []
                
                for rate in filtered_rates:
                    new_lines.append((0, 0, {
                        'rate_id': rate.id,
                        'order_id': order.id,
                        'transport_city': order.city_id.id,
                        'transport_port': order.port_of_loading.id,
                        'region_name': order.pickup_region,
                        'haulier_region_ids': region.id if region else False,
                    }))
                    
                order.update({'rate_link_ids': [(5, 0, 0)] + new_lines})

                self.env['omnifreight.transport.rates'].with_context(
                    active_id=order.id,
                    active_model='sale.order',
                    active_view='fob'
                ).force_recompute_from_sale_order(order.id)
                
                if order.rate_link_ids:
                    order.rate_link_ids._compute_fob_total()
            else:
                order.update({'rate_link_ids': [(5, 0, 0)]})

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure context is passed to transport rates"""
        orders = super(OmnifreightFobService, self).create(vals_list)
        
        # Set up context for each created order
        for order in orders:
            # Set up context for transport rates
            order.with_context({
                'default_transport_city': order.city_id.id if order.city_id else False,
                'default_transport_port': order.port_of_loading.id if order.port_of_loading else False,
                'default_region_name': order.pickup_region,
                'active_id': order.id,
                'active_model': 'sale.order',
                'default_container_type': order.container_type,
            })
            
            # If we have package details, update the order
            if 'package_details_id' in vals_list and vals_list['package_details_id']:
                package_details = self.env['omnifreight.package.details'].browse(vals_list['package_details_id'])
                order.write({
                    'container_type': package_details.container_type,
                    'contents': package_details.contents,
                    'content_classification': package_details.content_classification,
                })
            
        return orders

    def read(self, fields=None, load='_classic_read'):
        # When the record is loaded and the city field is requested, force recomputation
        if fields is None or 'city_id' in fields:
            # Loop through each record in the recordset
            for record in self:
                record.modified(['city_id'])
                self.env['omnifreight.transport.rates'].with_context(
                    active_id=record.id,  # Use record.id instead of self.id
                    active_model='sale.order'
                ).force_recompute_from_sale_order(record.id)
        return super(OmnifreightFobService, self).read(fields, load)
    
    def write(self, vals):
        res = super(OmnifreightFobService, self).write(vals)
        # If the city is updated, force recomputation on related transport rates
        if 'city_id' in vals:
            self.env['omnifreight.transport.rates'].with_context(
                active_id=self.id,  # Pass the current sale order ID
                active_model='sale.order'  # Pass the current model
            ).force_recompute_from_sale_order(self.id)
        
        # If any of these fields are updated, update the context for rate creation
        if any(field in vals for field in ['city_id', 'port_of_loading', 'pickup_region']):
            # Update context for transport rates
            for record in self:
                context = {
                    'default_transport_city': record.city_id.id if record.city_id else False,
                    'default_transport_port': record.port_of_loading.id if record.port_of_loading else False,
                    'default_region_name': record.pickup_region,
                    'active_id': record.id,
                    'active_model': 'sale.order'
                }
                # This will be used when creating new transport rates
                record.with_context(**context)
                
                # Update existing rate_link_ids with new city/port values if needed
                if record.rate_link_ids:
                    for rate_link in record.rate_link_ids:
                        if not rate_link.transport_city and record.city_id:
                            rate_link.transport_city = record.city_id.id
                        if not rate_link.transport_port and record.port_of_loading:
                            rate_link.transport_port = record.port_of_loading.id
                        if not rate_link.region_name and record.pickup_region:
                            rate_link.region_name = record.pickup_region
                            
        # Update existing fob_special_costs when port_of_loading or container_type changes
        if 'port_of_loading' in vals or 'container_type' in vals or 'pickup_type' in vals:
            for record in self:
                if record.fob_special_costs_id:
                    # Update existing special costs that don't have these values set
                    for cost in record.fob_special_costs_id:
                        if 'port_of_loading' in vals and not cost.port_id and record.port_of_loading:
                            cost.port_id = record.port_of_loading.id
                        if 'container_type' in vals and not cost.container_type and record.container_type:
                            cost.container_type = record.container_type
                        if 'pickup_type' in vals and hasattr(cost, 'pickup_type') and not cost.pickup_type and record.pickup_type:
                            cost.pickup_type = record.pickup_type
    
        return res
    
    @api.model
    def copy_data(self, default=None):
        """Override copy_data to handle duplicating FOB-related lines when duplicating Sale Orders"""
    
        # Get the original copy data
        result = super().copy_data(default)
        if not result:
            return result
        
        # Handle both single record and multiple records
        if not isinstance(result, list):
            result = [result]
        
        # For each dict in the result, use the corresponing record in self when multiple records are being copied
        records = self if len(result) == 1 else self

        for i, record_data in enumerate(result):
            record = records[i] if len(result) > 1 else records
        
            # Copy rate link IDs
            if record.rate_link_ids:
                new_rate_links = []
                for link in record.rate_link_ids:
                    link_copy_vals = link.copy_data()[0]
                    # Remove the original rate and sale order id to create a new record
                    if 'id' in link_copy_vals:
                        del link_copy_vals['id']
                    if 'order_id' in link_copy_vals:
                        del link_copy_vals['order_id']
                    new_rate_links.append((0, 0, link_copy_vals))
                record_data['rate_link_ids'] = new_rate_links
        
            # Copy FOB special costs
            if record.fob_special_costs_id:
                new_special_costs = []
                for cost in record.fob_special_costs_id:
                    cost_copy_vals = cost.copy_data()[0]
                    # Remove the original sale order and special cost ID to create a new record
                    if 'id' in cost_copy_vals:
                        del cost_copy_vals['id']
                    if 'sales_order_id' in cost_copy_vals:
                        del cost_copy_vals['sales_order_id']
                    new_special_costs.append((0, 0, cost_copy_vals))
                record_data['fob_special_costs_id'] = new_special_costs
    
        return result[0] if len(result) == 1 else result


    def create_transport_rate(self, vals=None):
        """Create a transport rate with values from the sale order"""
        self.ensure_one()
        if vals is None:
            vals = {}
            
        haulier_region_id = False
        
        if self.pickup_region:
            haulier_region = self.env['haulier.region'].search([('name', '=ilike', self.pickup_region)], limit=1)
            if haulier_region:
                haulier_region_id = haulier_region.id
                
        # Prepare values with defaults from the sale order
        vals.update({
            'order_id': self.id,
            'transport_city': vals.get('transport_city', self.city_id.id if self.city_id else False),
            'transport_port': vals.get('transport_port', self.port_of_loading.id if self.port_of_loading else False),
            'region_name': vals.get('region_name', self.pickup_region),
            'haulier_region_ids': vals.get('haulier_region_ids', haulier_region_id),
        })
    
        # Create the transport rate
        rate = self.env['sale.order.transport.rate'].create(vals)
        return rate
        
    @api.onchange('rate_link_ids')
    def _onchange_rate_link_selected_fob(self):
        """Ensure only one rate is selected and recompute totals when selection changes"""
        for order in self:
            # Handle FOB selection
            selected_fob_links = order.rate_link_ids.filtered('is_selected_fob')
            if len(selected_fob_links) > 1:
                last_fob = selected_fob_links[-1]
                for link in selected_fob_links:
                    if link != last_fob:
                        link.is_selected_fob = False
            
            # Force recomputation of totals
            if order.rate_link_ids:
                order.rate_link_ids._compute_fob_total()
                
    @api.onchange('transport_rates', 'distance')
    def _onchange_transport_rates(self):
        """Ensure that only one FOB transport rate is selected at a time and recompute totals"""
        for order in self:
            # Get the transport rates that are marked as selected
            selected_rates = order.transport_rates.filtered(lambda r: r.is_selected_fob)
            if len(selected_rates) > 1:
                # Keep only the most recent one
                most_recent = selected_rates[-1]
                for rate in selected_rates:
                    if rate != most_recent:
                        rate.is_selected_fob = False
                        
            # Force recomputation of totals
            if order.rate_link_ids:
                order.rate_link_ids._compute_fob_total()     
