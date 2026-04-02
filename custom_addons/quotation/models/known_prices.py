from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

from .route_logic import compute_write_date_only

class KnownPrices(models.Model):
    _name = 'known.price'
    _description = 'Known prices for the routes'

    name = fields.Char()
    carrier_id = fields.Many2one('res.partner', string='Carrier', domain="[('company_category', '=', 'supplier')]")
    container_type = fields.Selection(
        selection=lambda self: self.env['omnifreight.package.details'].CONTAINER_TYPES,
        string="Container Size"
    )
    price = fields.Integer()
    last_updated = fields.Date(compute='_compute_write_date_as_date')
    transit_time = fields.Integer(string="T.T")
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    
    # Compute fields for color coding
    is_cheapest = fields.Boolean(compute='_compute_flags')
    is_oldest = fields.Boolean(compute='_compute_flags')
    route_id = fields.Many2one('omnifreight.route', required=True)
    sale_order_id = fields.Many2one('sale.order')
    valid_until = fields.Date(string="Validity")
    departure_frequency = fields.Integer(string="Departure Frequency", help="Days taken between departures")
    notes = fields.Text(string='Notes')
    # IMO surcharge on Freight
    imo_surcharge_ft = fields.Float(string="Hazmat Surcharge")
    # Shipper's Own Container Tariff, charged by the carrier
    soc_tariff = fields.Integer(string="SOC Tariff", help="Shipper's Own Container Tariff, charged by the carrier")
    
    # Field to indicate if the rate has expired
    show_expiry_warning = fields.Boolean(default=False, compute="_compute_expiry_with_warning")

    ###
    # THESE ARE FIELDS THAT ARE NOT USED BUT KEPT FOR DB SANITY
    # ##
    is_selected = fields.Boolean()
 
    #####

    @api.depends('write_date', 'price', 'write_date')
    def _compute_write_date_as_date(self):
        compute_write_date_only(self)
        
    @api.depends('price', 'last_updated', 'route_id')
    def _compute_flags(self):
    # Group records by route to compute flags per route
        route_map = {}
        for rec in self:
            route_map.setdefault(rec.route_id.id, []).append(rec)

        for route_id, records in route_map.items():
            # Compute cheapest price in this route
            prices = [r.price for r in records if r.price is not None]
            min_price = min(prices) if prices else None

            # Compute oldest record based on last_updated
            valid_dates = [r.last_updated for r in records if r.last_updated]
            oldest_date = min(valid_dates) if valid_dates else None

            for r in records:
                r.is_cheapest = (r.price == min_price)
                r.is_oldest = (r.last_updated == oldest_date)

    
    @api.depends('valid_until')
    def _compute_expiry_with_warning(self):
        """Compute expiry warning flag."""
        today = fields.Date.today()
        for record in self:
            record.show_expiry_warning = record.valid_until and record.valid_until < today


    ###
    # This method is used to create or get a price record based on the provided values.
    # It checks if a price record with the same route_id, carrier_id, container_type,
    # transit_time, valid_until, and price already exists. If it does, it returns that record.
    # If not, it creates a new price record with the provided values.
    # This is useful for avoiding duplicate records and ensuring that the same price
    # information is not entered multiple times.
    @api.model
    def _get_or_create_price(self, vals):
        domain = [
            ('route_id', '=', vals.get('route_id')),
            ('carrier_id', '=', vals.get('carrier_id')),
            ('container_type', '=', vals.get('container_type')),
            ('transit_time', '=', vals.get('transit_time')),
            ('valid_until', '=', vals.get('valid_until')),
            ('price', '=', vals.get('price')),
            ('departure_frequency', '=', vals.get('departure_frequency')),
            ('imo_surcharge_ft', '=', vals.get('imo_surcharge_ft')),
            ('soc_tariff', '=', vals.get('soc_tariff')),
            ('notes', '=', vals.get('notes')),
        ]
        existing = self.search(domain, limit=1)
        if existing:
            return existing
        # Allow creating prices with past dates (expired rates) by skipping the constraint
        return self.with_context(skip_valid_until_check=True).create(vals)

    @api.onchange('valid_until')
    def _onchange_valid_until(self):
        """Reset valid_until to today if date is in the past."""
        if self._context.get('skip_valid_until_check') or self.env.context.get('skip_valid_until_check'):
            return
        today = fields.Date.context_today(self)
        if self.valid_until and self.valid_until < today:
            self.valid_until = today
            return {
                'warning': {
                    'title': 'Invalid Date',
                    'message': 'The "Valid Until" date cannot be in the past. It has been reset to today\'s date.',
                }
            }

    @api.constrains('valid_until')
    def _check_valid_until(self):
        """Validate that valid_until date is not in the past.
        Allow existing records with past dates (historical data) but prevent setting new/changed dates to the past.
        """
        if self._context.get('skip_valid_until_check') or self.env.context.get('skip_valid_until_check'):
            return
        today = fields.Date.context_today(self)
        for record in self:
            if record.valid_until and record.valid_until < today:
                # Check if this is an existing record that already had this past date
                # (i.e., the date hasn't changed - it's historical data)
                if record.id:
                    # Read the original value from database to check if date is being changed
                    # Use sudo to bypass any access rights and read directly from DB
                    original_record = self.sudo().browse(record.id)
                    if original_record.exists():
                        # If the date in DB matches the current date, it hasn't changed - allow it
                        if original_record.valid_until == record.valid_until:
                            # The date hasn't changed, so this is existing historical data - allow it
                            continue
                # Otherwise, this is a new record or the date was changed to a past date - prevent it
                raise ValidationError("The 'Valid Until' date cannot be in the past.")
    
    def action_duplicate_rate(self):
        """Duplicate an expired known price with a new valid_until date."""
        self.ensure_one()
        today = fields.Date.today()
        
        # Check if the current rate is expired
        if self.valid_until and self.valid_until < today:
            # Create a copy of the current known price
            new_price_vals = {
                'name': self.name,
                'carrier_id': self.carrier_id.id,
                'container_type': self.container_type,
                'price': self.price,
                'transit_time': self.transit_time,
                'currency_id': self.currency_id.id,
                'route_id': self.route_id.id,
                'sale_order_id': self.sale_order_id.id,
                'departure_frequency': self.departure_frequency,
                'notes': self.notes,
                'imo_surcharge_ft': self.imo_surcharge_ft,
                'soc_tariff': self.soc_tariff,
                'valid_until': False,  # Will be set by user
            }
            
            # Create the new known price
            new_price = self.env['known.price'].create(new_price_vals)
            
            # Archive the expired rate to filter it out
            self.write({'active': False})
            
            # Return action to open the new price
            return {
                'type': 'ir.actions.act_window',
                'name': 'Duplicate Known Price',
                'res_model': 'known.price',
                'res_id': new_price.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            raise ValidationError("Only expired rates can be duplicated.")

