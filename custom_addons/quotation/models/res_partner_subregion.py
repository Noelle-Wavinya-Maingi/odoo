from odoo import fields, models, api
import logging
_logger = logging.getLogger(__name__)

class ResPartnerRegion(models.Model):
    _inherit = 'res.partner'

    # Fields for contact country and region
    un_country_id = fields.Many2one('unloc.country', string='Contact Country')
    un_subregion_id = fields.Many2one('un.subregion', string='Contact Region', readonly=True)

    # Fields for import/export countries
    buy_country_ids = fields.Many2many(
        'unloc.country',
        'res_partner_buy_country_rel',  # Relation table for buy_country_ids
        'partner_id',                   # Column for res.partner
        'country_id',                   # Column for unloc.country
        string="Importing From"
    )
    ship_country_ids = fields.Many2many(
        'unloc.country',
        'res_partner_ship_country_rel',  # Relation table for ship_country_ids
        'partner_id',                    # Column for res.partner
        'country_id',                    # Column for unloc.country
        string="Exporting To"
    )
    
    #  Computed fields for import/export countries
    ship_country_comp = fields.Many2many(
        'unloc.country',
        'res_partner_ship_country_rel',  # Relation table for ship_country_ids
        'partner_id',                    # Column for res.partner
        'country_id',     
        string="Exporting",
        compute="_compute_trade_data",
        readonly=True,
    )
    
    buy_country_comp = fields.Many2many(
        'unloc.country',
        'res_partner_buy_country_rel',  # Relation table for buy_country_ids
        'partner_id',                   # Column for res.partner
        'country_id',  
        string="Importing",
        compute="_compute_trade_data",
        readonly=True,
    )

    buy_region_ids = fields.Many2many(
        'un.subregion',
        compute="_compute_buy_regions"
    )
    
    ship_region_ids = fields.Many2many(
        'un.subregion',
        compute="_compute_ship_regions"
    )

    # Computed fields for import/export regions for computed fields for import/export countries
    buy_region_comp = fields.Many2many(
        'un.subregion',
        compute="_compute_trade_data",
        readonly=True
    )
    
    ship_region_comp = fields.Many2many(
        'un.subregion',
        compute="_compute_trade_data",
        readonly=True
    )
    
    # ===================== EXPERT FIELDS =====================

    # Expert-selected buy regions (filtered)
    expert_buy_region_ids = fields.Many2many(
        'un.subregion',
        'res_partner_expert_buy_region_rel',
        'patner_id',
        'region_id',
        string="Expert Buy Region",
        domain="[('id', 'in', available_buy_regions)]"
    )
    
    # Read-only display of selected expert buy/ship regions
    expert_buy_region_display = fields.Many2many(
        'un.subregion',
        string="Expert Buy Regions (Readonly)",
        compute="_compute_expert_buy_region_display",
        readonly=True,
        store=False
    )
    
    expert_ship_region_display = fields.Many2many(
        'un.subregion',
        string="Expert Ship Regions (Readonly)",
        compute='_compute_expert_ship_region_display',
        readonly=True,
        store=False
    )
    
    # Expert-selected buy countries (with compute/inverse logic and domain filter)
    expert_buy_country_ids = fields.Many2many(
        'unloc.country',
        'res_partner_expert_buy_country_rel',
        'partner_id',
        'country_id',
        compute='_compute_expert_buy_country_ids',
        inverse="_inverse_expert_buy_country_ids",
        store=True,
        string="Expert Buy Countries",
        domain="[('id', 'in', expert_available_buy_countries)]"
    )

    # Expert-selected ship regions
    expert_ship_region_ids = fields.Many2many(
        'un.subregion',
        'res_partner_experts_ship_region_rel',
        'partner_id',
        'region_id',
        string="Expert Ship Regions",
        domain="[('id', 'in', available_ship_regions)]"
    )
    
     # Expert-selected ship countries (with compute/inverse logic and domain filter)
    expert_ship_country_ids = fields.Many2many(
        'unloc.country',
        'res_partner_experts_ship_country_rel',
        'partner_id',
        'country_id',
        compute='_compute_expert_ship_country_ids',
        inverse='_inverse_expert_ship_country_ids',
        store=True,
        string="Expert Ship Countries",
        domain="[('id', 'in', expert_available_ship_countries)]"
    )
    
    # ===================== AVAILABLE OPTIONS (FILTERS) =====================

    # Regions and countries made available for buying
    available_buy_regions = fields.Many2many(
        'un.subregion',
        'res_partner_available_buy_regions_rel',  # Unique relation table
        'partner_id',
        'region_id',
        compute='_compute_available_buy_regions',
        store=True,
        string="Available Buy Regions"
    )

    available_buy_countries = fields.Many2many(
        'unloc.country',
        'res_partner_available_buy_country_rel',
        'partner_id',
        'country_id',
        compute='_compute_available_buy_countries',
        string="Available Buy Countries"
    )
    
    # Countries filtered based on expert region selections
    expert_available_buy_countries = fields.Many2many(
        'unloc.country',
        'res_partner_expert_available_buy_country_rel',
        'partner_id',
        'country_id',
        compute="_compute_expert_available_buy_countries",
        string="Expert Available Buy Countries"
    )
    
    expert_available_ship_countries = fields.Many2many(
        'unloc.country',
        'res_partner_expert_available_ship_country_rel',
        'partner_id',
        'country_id',
        compute="_compute_expert_available_ship_countries",
        string="Expert Available Ship Countries"
    )
    
    # Regions and countries made available for shipping
    available_ship_regions = fields.Many2many(
        'un.subregion',
        'res_partner_available_ship_regions_rel',  # Unique relation table
        'partner_id',
        'region_id',
        compute='_compute_available_ship_regions',
        store=True,
        string="Available Ship Regions"
    )

    available_ship_countries = fields.Many2many(
        'unloc.country',
        'res_partner_available_ship_country_rel',
        'partner_id',
        'country_id',
        compute='_compute_available_ship_countries',
        string="Available Ship Countries"
    )
    
    # ===================== COMPUTE METHODS =====================
    
    @api.depends('company_ids.buy_region_ids', 'parent_id.buy_region_ids')
    def _compute_available_buy_regions(self):
        """Method to compute the available buy regions copied from the parent_id or company_id"""
        for record in self:
            if record.company_ids:
                record.available_buy_regions = record.company_ids.mapped('buy_region_ids')
            elif record.parent_id:
                record.available_buy_regions = record.parent_id.buy_region_ids
            else:
                record.available_buy_regions = False

    @api.depends('company_ids.buy_country_ids', 'parent_id.buy_country_ids')
    def _compute_available_buy_countries(self):
        """Method to compute the available buy countries copied from the parent_id or company_id"""
        for record in self:
            if record.company_ids:
                record.available_buy_countries = record.company_ids.mapped('buy_country_ids')
            elif record.parent_id:
                record.available_buy_countries = record.parent_id.buy_country_ids
            else:
                record.available_buy_countries = False
                
    @api.depends('company_ids.buy_country_ids', 'parent_id.buy_country_ids', 'expert_buy_region_ids')
    def _compute_expert_available_buy_countries(self):
        """Compute available buy countries, filtered by expert_buy_region_display if regions are chosen."""
        for record in self:
            # Base list comes from company or parent
            if record.company_ids:
                base_countries = record.company_ids.mapped('buy_country_ids')
            elif record.parent_id:
                base_countries = record.parent_id.buy_country_ids
            else:
                base_countries = self.env['unloc.country']

            # If expert regions selected, intersect with countries in those regions
            if record.expert_buy_region_ids:
                region_countries = record.expert_buy_region_display.mapped('country_ids')
                record.expert_available_buy_countries = base_countries & region_countries
            else:
                record.expert_available_buy_countries = False

    @api.depends('company_ids.ship_country_ids', 'parent_id.ship_country_ids', 'expert_ship_region_ids')
    def _compute_expert_available_ship_countries(self):
        """Compute expert-available buy countries filtered by selected expert buy regions."""
        for record in self:
            # Base list comes from parent or company
            if record.company_ids:
                base_countries = record.company_ids.mapped('ship_country_ids')
            elif record.parent_id:
                base_countries = record.parent_id.ship_country_ids
            else:
                base_countries = self.env['unloc.country']
                
            # If expert regions selected, intersect with countries in those regions
            if record.expert_ship_region_ids:
                region_countries = record.expert_ship_region_display.mapped('country_ids')
                record.expert_available_ship_countries = base_countries & region_countries
            else:
                record.expert_available_ship_countries = False
                
    @api.depends('company_ids.ship_region_ids', 'parent_id.ship_region_ids')
    def _compute_available_ship_regions(self):
        """Method to compute the available ship regions copied from the parent_id or company_id"""
        for record in self:
            # Checks if record has company_ids or parent_id then computes the available ship regions copied from either company_ids or parent_id else False
            if record.company_ids:
                record.available_ship_regions = record.company_ids.mapped('ship_region_ids')
            elif record.parent_id:
                record.available_ship_regions = record.parent_id.ship_region_ids
            else:
                record.available_ship_regions = False

    @api.depends('company_ids.ship_country_ids', 'parent_id.ship_country_ids')
    def _compute_available_ship_countries(self):
        """Method to compute the available buy countries copied from the parent_id or company_id"""
        for record in self:
            # Checks if record has company_ids or parent_id then computes the available ship countries copied from either company_ids or parent_id else False
            if record.company_ids:
                record.available_ship_countries = record.company_ids.mapped('ship_country_ids')
            elif record.parent_id:
                record.available_ship_countries = record.parent_id.ship_country_ids
            else:
                record.available_ship_countries = False

    @api.depends('expert_buy_region_ids', 'available_buy_countries')
    def _compute_expert_buy_country_ids(self):
        """Method to compute the importing from country based off of the selected expert import region"""
        for record in self:
            if not record.expert_buy_region_ids or not record.available_buy_countries:
                record.expert_buy_country_ids = False
                continue
            
            # Get countries from selected regions
            region_countries = record.expert_buy_region_ids.mapped('country_ids')
            
            # Intersect with available countries from company/parent
            available_countries = record.available_buy_countries & region_countries
            
            record.expert_buy_country_ids = available_countries
            
    def _inverse_expert_buy_country_ids(self):
        pass

    @api.depends('expert_ship_region_ids')
    def _compute_expert_ship_country_ids(self):
        """Method to compute the exporting to country based off of the selected expert export region"""
        for record in self:
            if not record.expert_ship_region_ids or not record.available_ship_countries:
                record.expert_ship_country_ids = False
                continue
            
            # Get countries from selected regions
            region_countries = record.expert_ship_region_ids.mapped('country_ids')
            
            # Intersect with available countries from company/parent
            available_countries = record.available_ship_countries & region_countries
            
            record.expert_ship_country_ids = available_countries
            
    def _inverse_expert_ship_country_ids(self):
        pass

    @api.depends('expert_buy_region_ids')
    def _compute_expert_buy_region_display(self):
        """Compute method for the readonly display of expert buy regions"""
        for record in self:
            record.expert_buy_region_display = record.expert_buy_region_ids
            
    @api.depends('expert_ship_region_ids')
    def _compute_expert_ship_region_display(self):
        """Compute method for the readonly display of expert buy regions"""
        for record in self:
            record.expert_ship_region_display = record.expert_ship_region_ids
    
    # Synchronize UN Country with Address Country
    @api.depends('un_country_id', 'country_id')
    def _compute_country_sync(self):
        """Ensure the UN Country and Address Country are always in sync."""
        for record in self:
            if record.un_country_id and not record.country_id:
                # If UN Country is set but Address Country is not, sync them
                record.country_id = self.env['res.country'].search([('name', '=ilike', record.un_country_id.name)], limit=1)
            elif record.country_id and not record.un_country_id:
                # If Address Country is set but UN Country is not, sync them
                un_country = self.env['unloc.country'].search([('name', '=ilike', record.country_id.name)], limit=1)
                record.un_country_id = un_country

    # Onchange method for UN Country
    @api.onchange('un_country_id')
    def _onchange_un_country_id(self):
        """Automatically set the region and address country when a UN country is selected."""
        if self.un_country_id:
            # Set the subregion based on the selected UN country
            self.un_subregion_id = self.un_country_id.subregion_id
            # Sync the address country
            self.country_id = self.env['res.country'].search([('name', '=ilike', self.un_country_id.name)], limit=1)

    # Onchange method for Address Country
    @api.onchange('country_id')
    def _onchange_country_id(self):
        """Automatically set the UN country when the address country is selected."""
        if self.country_id:
            # Sync the UN country
            un_country = self.env['unloc.country'].search([('name', '=ilike', self.country_id.name)], limit=1)
            self.un_country_id = un_country
            # Set the subregion based on the UN country
            self.un_subregion_id = un_country.subregion_id if un_country else False
            
    @api.depends('buy_country_ids')
    def _compute_buy_regions(self):
        for record in self:
            record.buy_region_ids = [(6, 0, record.buy_country_ids.mapped('subregion_id.id'))]
            
    @api.depends('ship_country_ids')
    def _compute_ship_regions(self):
        for record in self:
            record.ship_region_ids = [(6, 0, record.ship_country_ids.mapped('subregion_id.id'))]
            
    @api.depends('buy_country_ids', 'ship_country_ids', 'company_ids.buy_country_ids', 
                 'company_ids.ship_country_ids', 'parent_id.buy_country_ids', 
                 'parent_id.ship_country_ids')
    def _compute_trade_data(self):
        for record in self:
            # If the record is a company use its own data.
            # Otherwise, if it is an individual linked to a company, pull trade data from that company.
            if record.is_company or (not record.parent_id and not record.company_ids):
                buy_data = record.buy_country_ids
                ship_data = record.ship_country_ids
                buy_region = record.buy_region_ids
                ship_region = record.ship_region_ids
            else:
                # Aggregate trade data from linked companies:
                # Check if the record has companies linked through company_ids.
                if record.company_ids:
                    buy_data = record.company_ids.mapped('buy_country_ids')
                    ship_data = record.company_ids.mapped('ship_country_ids')
                    buy_region = record.company_ids.mapped('buy_region_ids')
                    ship_region = record.company_ids.mapped('ship_region_ids')
                # Otherwise, use the parent's trade data.
                elif record.parent_id:
                    buy_data = record.parent_id.buy_country_ids
                    ship_data = record.parent_id.ship_country_ids
                    buy_region = record.parent_id.buy_region_ids
                    ship_region = record.parent_id.ship_region_ids
                else:
                    buy_data = record.buy_country_ids
                    ship_data = record.ship_country_ids
                    buy_region = record.buy_region_ids
                    ship_region = record.ship_region_ids

            record.buy_country_comp = buy_data
            record.ship_country_comp = ship_data
            record.buy_region_comp = buy_region
            record.ship_region_comp = ship_region

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure the subregion is set when creating new records in batch."""
        if not isinstance(vals_list, list):
            # If vals_list is not a list, handle it as a single record creation
            vals_list = [vals_list]

        # Prepare the vals_list for batch creation
        for vals in vals_list:
            # Ensure vals is a dictionary
            if isinstance(vals, dict):
                # Handle UN Country sync if it exists
                if 'un_country_id' in vals:
                    country = self.env['unloc.country'].browse(vals['un_country_id'])
                    vals['un_subregion_id'] = country.subregion_id.id if country.subregion_id else False

                # Handle Address Country sync if it exists
                if 'country_id' in vals and 'un_country_id' not in vals:
                    country_id = vals.get('country_id')
                    if isinstance(country_id, (int, str)):  # Validate country_id
                        try:
                            country_id = int(country_id)
                            country = self.env['res.country'].browse(country_id)
                            if country.exists():
                                un_country = self.env['unloc.country'].search([('name', '=', country.name)], limit=1)
                                vals['un_country_id'] = un_country.id if un_country else False
                                vals['un_subregion_id'] = un_country.subregion_id.id if un_country and un_country.subregion_id else False
                        except ValueError:
                            pass  # Skip invalid country_id values gracefully

        # Use the super method to create the records in batch
        return super(ResPartnerRegion, self).create(vals_list)

    @api.model
    def write(self, vals):
        """Ensure the subregion is updated when the country changes."""
        if not isinstance(vals, dict):
            return super().write(vals)  # Only process dict inputs

        updates = dict(vals)  # Copy to avoid mutating original dict

        # If UN Country is directly set, sync subregion
        if 'un_country_id' in updates:
            country = self.env['unloc.country'].browse(updates['un_country_id'])
            updates['un_subregion_id'] = country.subregion_id.id if country.subregion_id else False

        # If Odoo Country changes but UN Country isn't set, try to find matching UN Country
        elif 'country_id' in updates:
            country_id = updates.get('country_id')
            if isinstance(country_id, (int, str)):
                try:
                    country_id = int(country_id)
                    country = self.env['res.country'].browse(country_id)
                    if country.exists():
                        un_country = self.env['unloc.country'].search([('name', '=', country.name)], limit=1)
                        updates['un_country_id'] = un_country.id if un_country else False
                        updates['un_subregion_id'] = un_country.subregion_id.id if (un_country and un_country.subregion_id) else False
                except ValueError:
                    pass  # Ignore bad country_id

        # Only call super if something actually changed to avoid unnecessary triggers
        if updates:
            try:
                return super(ResPartnerRegion, self).write(updates)
            except UnboundLocalError as e:
                # Temporary workaround for Odoo bug in partner2moves
                if "partner2moves" in str(e):
                    # Log it but don't crash
                    _logger.error("Odoo accounting write bug hit: %s", e)
                    return True
                raise
        return True
