from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import timedelta

class SaleOrderKnownPriceRel(models.Model):
    _name = 'sale.order.known.price'
    _description = 'Sale Order Known Price Relation'

    sale_order_id = fields.Many2one('sale.order', ondelete='cascade')
    known_price_id = fields.Many2one('known.price', ondelete='cascade')

    # Copy some fields for display in the list view
    carrier_id = fields.Many2one(related='known_price_id.carrier_id', store=True, readonly=False, domain="[('company_category', '=', 'supplier')]")
    container_type = fields.Selection(
        selection=lambda self: self.env['omnifreight.package.details'].fields_get()['container_type']['selection'],
        string="Container Type"
    )

    transit_time = fields.Integer(related='known_price_id.transit_time', store=True, readonly=False)
    valid_until = fields.Date(related='known_price_id.valid_until', store=True, readonly=False)
    price = fields.Integer(related='known_price_id.price', store=True, readonly=False)
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        compute='_compute_currency_id',
        inverse='_inverse_currency_id',
        store=True,
        readonly=False,
        help="Currency for this rate"
    )
    departure_frequency = fields.Integer(related='known_price_id.departure_frequency', store=True, readonly=False)
    imo_surcharge_ft = fields.Float(related='known_price_id.imo_surcharge_ft', store=True, readonly=False)
    notes = fields.Text(related='known_price_id.notes', string='Notes', readonly=False, store=True)
    route_id = fields.Many2one(related='known_price_id.route_id', store=True, readonly=False)
    soc_tariff = fields.Integer(related='known_price_id.soc_tariff', store=True, readonly=False)
    has_hazardous_content = fields.Boolean(related='sale_order_id.has_hazardous_content', store=True, readonly=False)
    soc = fields.Boolean(related='sale_order_id.soc', store=True, readonly=False)

    # This flag is sale-order specific!
    is_selected = fields.Boolean(string="Selected Rate")
    
    # Field to indicate if the rate has expired
    show_expiry_warning = fields.Boolean(compute='_compute_show_expiry_warning', store=True, readonly=True)
    
    is_hidden = fields.Boolean(default=False)
    
    @api.depends('known_price_id', 'known_price_id.currency_id', 'sale_order_id', 'sale_order_id.currency_id')
    def _compute_currency_id(self):
        """Compute currency from known_price_id if available, otherwise from sale_order_id"""
        for record in self:
            if record.known_price_id and record.known_price_id.currency_id:
                record.currency_id = record.known_price_id.currency_id
            elif record.sale_order_id and record.sale_order_id.currency_id:
                record.currency_id = record.sale_order_id.currency_id
            else:
                record.currency_id = self.env.company.currency_id
    
    def _inverse_currency_id(self):
        """When currency is set, update the known_price_id if it exists"""
        for record in self:
            if record.known_price_id and record.currency_id:
                record.known_price_id.currency_id = record.currency_id
    
    @api.depends('valid_until', 'known_price_id')
    def _compute_show_expiry_warning(self):
        """Compute expiry warning flag based on valid_until date."""
        today = fields.Date.context_today(self)
        for record in self:
            valid_until = record.valid_until
            if not valid_until and record.known_price_id:
                valid_until = record.known_price_id.valid_until
            record.show_expiry_warning = valid_until and valid_until < today
    
    # Computed field for total rate including all additional costs
    rate_total = fields.Float(
        string="Total Rate", 
        compute='_compute_rate_total', 
        store=True,
        help="Total rate including base price, IMO surcharge (if hazardous), and SOC tariff (if SOC enabled)"
    )

    @api.depends('price', 'imo_surcharge_ft', 'soc_tariff', 'has_hazardous_content', 'sale_order_id.soc')
    def _compute_rate_total(self):
        """Compute the total rate including all additional costs."""
        for record in self:
            total = float(record.price or 0.0)
            
            # Add IMO surcharge if hazardous content
            if record.has_hazardous_content and float(record.imo_surcharge_ft or 0.0):
                total += float(record.imo_surcharge_ft or 0.0)
            
            # Add SOC tariff if SOC is enabled
            if record.sale_order_id and record.sale_order_id.soc and float(record.soc_tariff or 0.0):
                total += float(record.soc_tariff or 0.0)
            
            record.rate_total = total


    def _ensure_known_price_in_route(self):
        order = self.sale_order_id
        route = order._get_current_route() if order else None

        if not order or not order.port_of_loading or not order.port_of_dispatch:
            self.unlink()
            return

        if route and self.known_price_id not in route.known_prices_id:
            route.known_prices_id = [(4, self.known_price_id.id)]


    @api.onchange('sale_order_id')
    def _onchange_sale_order_id_set_container_type(self):
        """Set the container type and currency from the sale order if available."""
        if self.sale_order_id:
            if self.sale_order_id.container_type:
                self.container_type = self.sale_order_id.container_type
            # Set currency from sale order if not already set
            if not self.currency_id and self.sale_order_id.currency_id:
                self.currency_id = self.sale_order_id.currency_id
    
    @api.onchange('known_price_id')
    def _onchange_known_price_id(self):
        """Sync currency from known_price_id when known_price_id is selected"""
        # The compute method will handle this automatically, but we trigger it here
        self._compute_currency_id()

    @api.model
    def default_get(self, fields_list):
        res = super(SaleOrderKnownPriceRel, self).default_get(fields_list)
        # Get sale_order_id directly from the record's field (since it's part of the model)
        if 'sale_order_id' in res:
            sale_order = self.env['sale.order'].browse(res['sale_order_id'])
            if sale_order.container_type:  # If the sale_order has a container_type
                res['container_type'] = sale_order.container_type
            # Set SOC and hazardous content from parent sale order
            if 'soc' in fields_list:
                res['soc'] = sale_order.soc
            if 'has_hazardous_content' in fields_list:
                res['has_hazardous_content'] = sale_order.has_hazardous_content
            # Set currency from sale order if available (for new records without known_price_id)
            if 'currency_id' in fields_list and not res.get('currency_id') and sale_order.currency_id:
                res['currency_id'] = sale_order.currency_id.id
        
        return res    

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure SOC and hazardous content are set from parent sale order."""
        for vals in vals_list:
            if 'sale_order_id' in vals and vals['sale_order_id']:
                sale_order = self.env['sale.order'].browse(vals['sale_order_id'])
                # Set SOC and hazardous content from parent sale order if not already set
                if 'soc' not in vals:
                    vals['soc'] = sale_order.soc
                if 'has_hazardous_content' not in vals:
                    vals['has_hazardous_content'] = sale_order.has_hazardous_content
        records = super().create(vals_list)
        return records

    @api.constrains('sale_order_id', 'known_price_id')
    def _check_ports_set(self):
        for rec in self:
            order = rec.sale_order_id
            if order and (not order.port_of_loading or not order.port_of_dispatch):
                raise ValidationError(
                    "You must select both a Port of Loading and a Port of Destination before adding a freight rate."
                )

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id_ports(self):
        if self.sale_order_id and (not self.sale_order_id.port_of_loading or not self.sale_order_id.port_of_dispatch):
            return {
                'warning': {
                    'title': "Missing Ports",
                    'message': "You must select both a Port of Loading and a Port of Destination before adding a freight rate."
                }
            }    
    
    @api.constrains('is_selected', 'sale_order_id')
    def _check_only_one_selected(self):
        for rec in self:
            if rec.is_selected and rec.sale_order_id:
                domain = [
                    ('sale_order_id', '=', rec.sale_order_id.id),
                    ('is_selected', '=', True),
                    ('id', '!=', rec.id)
                ]
                if self.search_count(domain):
                    raise ValidationError("Only one price can be selected per Sale Order.")

    def write(self, vals):
        # If is_selected is being set to True, unselect others for the same sale_order_id
        if 'is_selected' in vals and vals['is_selected']:
            for rec in self:
                if rec.sale_order_id:
                    others = self.search([
                        ('sale_order_id', '=', rec.sale_order_id.id),
                        ('id', '!=', rec.id),
                        ('is_selected', '=', True)
                    ])
                    others.write({'is_selected': False})
        
        res = super().write(vals)
        
        # Ensure the related field write actually updated the known_price_id
        if 'valid_until' in vals:
            for rec in self:
                if rec.known_price_id and rec.valid_until != rec.known_price_id.valid_until:
                    # Check if the date is in the past (expired rate)
                    # If it's an existing expired rate, skip validation to allow historical data
                    today = fields.Date.context_today(self)
                    is_expired = rec.valid_until and rec.valid_until < today
                    existing_was_expired = rec.known_price_id.valid_until and rec.known_price_id.valid_until < today
                    
                    # If both old and new dates are expired, it's historical data - skip validation
                    if is_expired and existing_was_expired:
                        rec.known_price_id.with_context(skip_valid_until_check=True).write({'valid_until': rec.valid_until})
                    else:
                        # Force update the known_price_id.valid_until if there's a mismatch
                        rec.known_price_id.write({'valid_until': rec.valid_until})
        
        for rec in self:
            rec._ensure_known_price_in_route()
            # Force parent recompute if is_selected changed
            if 'is_selected' in vals and rec.sale_order_id:
                rec.sale_order_id._compute_freight_costs()
                rec.sale_order_id._compute_estimated_total()
        return res

    def force_recompute_pricing(self, sale_order_id):
        """Force recompute pricing for the sale order."""
        if not sale_order_id:
            return

        # Recompute the freight costs
        sale_order_id._compute_freight_costs()
        
        # Recompute the estimated total
        sale_order_id._compute_estimated_total()
        

    @api.model_create_multi
    def create_multi(self, vals_list):
        records = super().create_multi(vals_list)
        for record, vals in zip(records, vals_list):
            if vals.get('is_selected') and record.sale_order_id:
                others = self.search([
                    ('sale_order_id', '=', record.sale_order_id.id),
                    ('id', '!=', record.id),
                    ('is_selected', '=', True)
                ])
                others.write({'is_selected': False})
            try:
                record._ensure_known_price_in_route()
            except Exception:
                pass
            # Force parent recompute if is_selected set
            if vals.get('is_selected') and record.sale_order_id:
                record.sale_order_id._compute_freight_costs()
                record.sale_order_id._compute_estimated_total()
        return records

    def action_duplicate_rate(self):
        """Duplicate an expired known price with a new valid_until date."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        
        if not self.valid_until or self.valid_until >= today:
            raise ValidationError("Only expired rates can be duplicated.")
        
        source_known_price = self.known_price_id
        
        if not source_known_price:
            if not self.sale_order_id:
                raise ValidationError("Cannot duplicate: no sale order associated with this rate.")
            
            route = self.sale_order_id._get_current_route()
            if not route:
                raise ValidationError("Cannot duplicate: no route found for the current ports.")
            
            domain = [
                ('route_id', '=', route.id),
                ('carrier_id', '=', self.carrier_id.id if self.carrier_id else False),
                ('container_type', '=', self.container_type),
                ('transit_time', '=', self.transit_time or 0),
                ('valid_until', '=', self.valid_until),
                ('price', '=', self.price or 0),
                ('departure_frequency', '=', self.departure_frequency or 0),
                ('imo_surcharge_ft', '=', self.imo_surcharge_ft or 0.0),
                ('soc_tariff', '=', self.soc_tariff or 0),
            ]
            source_known_price = self.env['known.price'].search(domain, limit=1)
            
            if not source_known_price:
                currency_id = self.currency_id.id if self.currency_id else self.env.company.currency_id.id
                tomorrow = today + timedelta(days=1)
                source_known_price = self.env['known.price'].with_context(skip_valid_until_check=True).create({
                    'name': '',
                    'carrier_id': self.carrier_id.id if self.carrier_id else False,
                    'container_type': self.container_type,
                    'price': self.price or 0,
                    'transit_time': self.transit_time or 0,
                    'currency_id': currency_id,
                    'route_id': route.id,
                    'departure_frequency': self.departure_frequency or 0,
                    'notes': self.notes or '',
                    'imo_surcharge_ft': self.imo_surcharge_ft or 0.0,
                    'soc_tariff': self.soc_tariff or 0,
                    'valid_until': tomorrow,
                })
               
        
        currency_id = source_known_price.currency_id.id if source_known_price.currency_id else self.env.company.currency_id.id
        tomorrow = today + timedelta(days=1)
        
        new_price_vals = {
            'name': source_known_price.name or '',
            'carrier_id': source_known_price.carrier_id.id if source_known_price.carrier_id else False,
            'container_type': source_known_price.container_type,
            'price': source_known_price.price,
            'transit_time': source_known_price.transit_time or 0,
            'currency_id': currency_id,
            'route_id': source_known_price.route_id.id if source_known_price.route_id else False,
            'sale_order_id': source_known_price.sale_order_id.id if source_known_price.sale_order_id else False,
            'departure_frequency': source_known_price.departure_frequency or 0,
            'notes': source_known_price.notes or '',
            'imo_surcharge_ft': source_known_price.imo_surcharge_ft or 0.0,
            'soc_tariff': source_known_price.soc_tariff or 0,
            'valid_until': tomorrow,
        }
        
        new_price = self.env['known.price'].with_context(skip_valid_until_check=True).create(new_price_vals)
        
        new_sale_order_known_price = self.env['sale.order.known.price'].create({
            'sale_order_id': self.sale_order_id.id,
            'known_price_id': new_price.id,
            'container_type': self.container_type,
            'transit_time': self.transit_time,
            'departure_frequency': self.departure_frequency,
            'imo_surcharge_ft': self.imo_surcharge_ft,
            'soc_tariff': self.soc_tariff,
            'currency_id': currency_id,
            'is_selected': False,
        })
        
        self.is_hidden = True
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Duplicate Known Price',
            'res_model': 'sale.order.known.price',
            'res_id': new_sale_order_known_price.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'skip_valid_until_check': True},
        }

