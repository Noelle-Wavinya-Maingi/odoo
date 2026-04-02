from odoo import fields, models, api
from odoo.exceptions import  ValidationError, UserError
from .capitalize_mixin import CapitalizedNameMixin
import logging
_logger = logging.getLogger(__name__)


# UN Subregions Model - Represents geographical subregions according to UN M49 standard
class UNSubregions(models.Model, CapitalizedNameMixin):
    _name = 'un.subregion'
    _description = 'World subregions as per the UN M49 classification'

    # Basic subregion information
    name = fields.Char(string='Subregion Name', required=True)
    code = fields.Integer(string='M49 Code', required=True)
    
    # Relationships
    continent_id = fields.Many2one('geographical.continent', string='Continent')
    country_ids = fields.One2many('unloc.country', 'subregion_id', string='Countries')

    # Database constraints
    # _sql_constraints = [
    #     ('unique_subregion_name', 'unique(name)', 'Subregion names must be unique.'),
    #     ('unique_subregion_code', 'unique(code)', 'Subregion codes must be unique.')
    # ]
    _uniq_name = models.Constraint('unique(name)', 'Subregion names must be unique.')
    _uniq_code = models.Constraint('unique(code)', 'Subregion codes must be unique!')

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure a Haulier Region is created for each new Subregion, supporting bulk creation."""
        subregions = super().create(vals_list)

        haulier_region_data = [{'name': subregion.name, 'region_name': subregion.id} for subregion in subregions]
        self.env['haulier.region'].create(haulier_region_data)

        return subregions

# Continents Model - Represents major geographical continents
class Continents(models.Model, CapitalizedNameMixin):
    _name = 'geographical.continent'
    _description = 'World continents'

    # Basic continent information
    name = fields.Char(string='Continent', required=True)
    code = fields.Integer(string='Continent Code', required=True)
    
    # Relationships
    subregion_ids = fields.One2many('un.subregion', 'continent_id', string='Subregions')
    country_ids = fields.One2many('unloc.country', 'continent_id', string='Countries')

    # Computed fields for display purposes
    subregion_names = fields.Char(
        string='Subregion Names',
        compute='_compute_subregion_names',
        store=False
    )
    country_names = fields.Char(
        string='Country Names',
        compute='_compute_country_names',
        store=False
    )

    # Database constraints
    # _sql_constraints = [
    #     ('unique_continent_name', 'unique(name)', 'Continent names must be unique.'),
    #     ('unique_continent_code', 'unique(code)', 'Continent codes must be unique.')
    # ]
    _uniq_name = models.Constraint('unique(name)', 'Continent names must be unique.')
    _uniq_code = models.Constraint('unique(code)', 'Continent codes must be unique!')

    # Computes a comma-separated list of all subregion names belonging to this continent
    def _compute_subregion_names(self):
        for record in self:
            record.subregion_names = ', '.join(set(record.subregion_ids.mapped('name')))

    # Computes a comma-separated list of all country names belonging to this continent
    def _compute_country_names(self):
        for record in self:
            record.country_names = ', '.join(set(record.country_ids.mapped('name')))


# UN Country Model - Represents countries with their UN and ISO codes
class UNCountry(models.Model, CapitalizedNameMixin):
    _name = 'unloc.country'
    _description = 'The country model with country code'

    # Basic country information
    name = fields.Char(string='Country', required=True)
    code = fields.Integer(string='Country Code', required=True)
    alphaCode = fields.Char(string='ISO Alpha Code', required=True)
    
    # Relationships
    subregion_id = fields.Many2one('un.subregion', string='Subregion')
    continent_id = fields.Many2one(
        related='subregion_id.continent_id',
        store=True,
        string='Continent'
    )
    city_id = fields.One2many('unloc.city', 'country_id', string="City")
    city_names = fields.Char(
        string='Country Names',
        compute='_compute_city_names',
        store=False
    )
    
    # Computes a comma-separated list of all country names belonging to this continent
    def _compute_city_names(self):
        for record in self:
            record.city_names = ', '.join(set(record.city_id.mapped('name')))


    # # Database constraints
    # _sql_constraints = [
    #     ('unique_country_name', 'unique(name)', 'Country names must be unique.'),
    #     ('unique_country_code', 'unique(code)', 'Country codes must be unique.'),
    # ]
    _uniq_name = models.Constraint('unique(name)', 'Country names must be unique.')
    _uniq_code = models.Constraint('unique(code)', 'Country codes must be unique!')
    
class UNCity(models.Model, CapitalizedNameMixin):
    _name = 'unloc.city'
    _description = 'The city custom model'
    
    name = fields.Char(string='City', required=True)
    country_id = fields.Many2one('unloc.country', string="Country", required=True)
    country_code = fields.Integer(string="Country Code")
    zip_codes = fields.One2many('unloc.city.zip', 'un_city_id', string="Zip Codes")

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to automatically assign country_id based on country_code"""
        if isinstance(vals_list, dict):  # If a single record is passed, convert to a list
            vals_list = [vals_list]

        for vals in vals_list:
            if 'country_code' in vals:
                # Search for the country by the provided country code
                country = self.env['unloc.country'].search([('code', '=', str(vals['country_code']))], limit=1)
                if country:
                    vals['country_id'] = country.id  # Assign the Many2one field with an integer ID

        # Call the parent `create` method with the updated vals_list
        return super(UNCity, self).create(vals_list)


    @api.constrains('country_code')
    def _check_country_code(self):
        "prevent import if the country_code is invalid"
        for record in self:
            if record.country_code:
                country = self.env['unloc.country'].search([('code', '=', record.country_code)], limit=1)
                if not country:
                    raise ValidationError(f"Invalid country code: {record.country_code}. No matching country found.")
                


class UNCityZip(models.Model):
    _name = 'unloc.city.zip'
    _description = 'City Zip Codes'

    name = fields.Char(string="Zip Code", required=True)
    un_city_id = fields.Many2one('unloc.city', string="City", required=True, ondelete='cascade')
    
    @api.model_create_multi
    def create(self, vals_list):
        # Ensure the method works with both single and batch creates
        if isinstance(vals_list, dict):
            vals_list = [vals_list]  # Convert single record create to list
        
        for vals in vals_list:
            # If un_city_id is missing, attempt to set it using context
            if not vals.get('un_city_id') and self.env.context.get('default_unloc_city_id'):
                vals['un_city_id'] = self.env.context['default_unloc_city_id']
            elif not vals.get('un_city_id') and self.env.context.get('default_city_id'):
                vals['un_city_id'] = self.env.context['default_city_id']
        
        # Call the parent method to perform actual creation in batch
        return super(UNCityZip, self).create(vals_list)
