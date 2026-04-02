from odoo import fields, models, api
from .carrier_compute import CarrierCompute
from .carrier_onchange import CarrierOnchange
from .carrier_crud import CarrierCrud
from .carrier_constarins import CarrierConstrains

ADDRESS_FIELDS_CONTACTS = ('zip_code_id', 'unloc_city_id', 'street', 'street2', 'zip', 'city', 'state_id', 'country_id', 'line3', 'un_country_id', 'un_subregion_id')

class Carrier(models.Model, CarrierCompute, CarrierOnchange, CarrierCrud, CarrierConstrains):
    _inherit = 'res.partner'
    
    first_name = fields.Char(string='First Name', compute='_compute_name', inverse="_inverse_name", store=True)
    last_name = fields.Char(string='Last Name', compute='_compute_name', inverse="_inverse_name", store=True)
    address = fields.Char()
    description = fields.Text()
    route_id = fields.Many2one('omnifreight.route')
    last_updated = fields.Date(
        compute='_compute_write_date_only',
        string='Last Updated On',
        store=False
    ) 
    departure_frequency = fields.Selection([
        ('days', 'Days'),
        ('weekly', 'Weekly'),
        ('fortnight', 'Fortnight'),
        ('monthly', 'Monthly')
    ], default='weekly')

    is_employee = fields.Boolean(
        string="Is Employee",
        compute="_compute_is_employee",
        store=True,
        default=False
    )
    incoterm_ids = fields.Many2many('account.incoterms', string="Incoterm", help="Select the incoterms available for this contact")
    role_ids = fields.Many2many(
        'omnifreight.roles',
        string='Job Positions',
        relation='contact_role',  
        column1='contact_id',     
        column2='role_id',        
    )

    # Many-to-many relationship between contacts and companies
    company_ids = fields.Many2many(
        'res.partner',
        string='Companies',
        relation='contact_company_rel', 
        column1='contact_id',            
        column2='company_id',            
        domain=[('is_company', '=', True)],  
    )
    
    # EORI Fields
    own_eori_number = fields.Char(
        string="EORI Number", 
        help="Economic Operators Registration and Identification Number (Required for EU countries)."
    )
    
    # List of EU country codes.
    EU_COUNTRY_CODES = [
        'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR','GR','HR','HU',
        'IE','IT','LT','LU','LV','MT','NL','PL','PT','RO','SE','SI','SK'
    ]
    
    # Compute field to check if the carrier is located in the EU.
    is_in_eu = fields.Boolean(
        compute="_compute_is_in_eu",
        store=True
    )
    
    # Many-to-many relationship to link contacts with companies (non-company contacts).
    contact_ids = fields.Many2many(
        'res.partner',
        string='Linked Contacts',
        relation='contact_company_rel',
        column1='company_id',
        column2='contact_id',
        domain=[('is_company', '=', False)],
    )
    
    # Segment field to categorize the carrier's business or trade focus.
    segment = fields.Selection([
        ('segment_1', 'Segment 1:Trade with Africa'),
        ('segment_2', 'Segment 2:Geographical Position in Antwerp, Europe'),
        ('segment_3', 'Segment 3:Trade With Africa & Geographical Position in Antwerp, Europe')
    ], string="Segments")
    
    segment_id = fields.Many2many('omnifreight.segments', 'omnifreight_segments_one_rel', 'segment_id', 'target_id', string="Segment")
    
    segment_key = fields.Char(
        string="Segment Key",
        compute="_compute_segment_key"
    )

    # Many-to-one relationship to the target model based on the selected segment.
    target_id = fields.Many2one(
        'target',
        string="Target",
        domain="[('segment', '=', segment_key)]"
    )
    
    # Compute field to store a unique target key for the carrier.
    target_key = fields.Char(
        string="Target Key",
        compute="_compute_target_key",
        store=True
    )

    # Many-to-many field to store subcategories related to the carrier.
    subcategory_ids = fields.Many2many(
        'subcategory',
        'subcategory_two_rel',
        'target_id',
        'subcategory_id',
        string="Subcategories",
        domain="[('target', '=', target_segment_one)]" 
    )
    
    segment_id_two = fields.Many2many('omnifreight.segment.two', string="Segment Two")
    
    segment_keys = fields.Char(
        string="Segment Keys",
        compute="_compute_segment_keys"
    )

    # Many-to-one relationship to the target model based on the selected segment.
    target_id_segment_two = fields.Many2one(
        'target',
        string="Target Two",
        domain="[('segment', '=', segment_keys)]"
    )
    
    target_segment_one = fields.Selection([
        ('target_1a', '1A: Standalone Merchants Trading In/with Africa'),
        ('target_1b', '1B: SME\'s Trading in/with Africa'),
        ('target_1c', '1C: Freight Forwarders & Traders dealing with Africa')
    ])
    
    target_segment_two = fields.Selection([
        ('target_2a', '2A: SME\'s needing logistics services in Europe'),
        ('target_2b', '2B: Chinese companies in Europe'),
        ('target_2c', '2C: Freight Forwarders needing logistics solutions in Europe')
    ])
    
    # Compute field to store a unique target key for the carrier.
    target_keys = fields.Char(
        string="Target Keys",
        compute="_compute_target_keys",
        store=True
    )

    # Many-to-many field to store subcategories related to the carrier.
    subcategory_ids_segment_two = fields.Many2many(
        'subcategory',
        string="Subcategories Two",
        domain="[('target', '=', target_segment_two)]" 
    )
    
    requires_subcategory = fields.Boolean(compute="_compute_requires_subcategories")
    
    requires_subcategory_two = fields.Boolean(compute="_compute_requires_subcategories")
    
    # Field to define the type of address (contact, invoice, delivery, etc.).
    types = fields.Selection(
        selection=[('contact', 'Contact Address'), ('invoice', 'Invoice Address'), ('delivery', 'Delivery Address'), ('loading', 'Loading Address'), ('other', 'Other Address')],
        string='Type',
        default='contact'
    )
    
    # Selection field to assign a rating tag to the carrier.
    ratings_tag = fields.Selection([
        ('easy', 'Easy'),
        ('neutral', 'Neutral'),
        ('challenging', 'Challenging')
    ])
    
    # Boolean field to determine whether subcategories should be hidden.
    hide_subcategories = fields.Boolean(
        string="Hide Subcategories",
        default=False
    )
    
    hide_subcategories_two = fields.Boolean(
        string="Hide Subcategories Two",
        default=False
    )
    
    # Additional address line fields for carrier’s address.
    line3 = fields.Char(string="P.O. BOX")
    
    # Selection field for categorizing the company as either a client or a supplier.
    company_category = fields.Selection(
        [('client', 'Client'), ('supplier', 'Supplier'), ('organizations', 'Organizations')],
        string='Company Category',
        default="client",
        help="Specify whether the company is a Client or a Supplier",
    )
    
    # Supplier type field to specify if the supplier provides logistics services or general services.
    supplier_type = fields.Selection(
        [('logistics', 'Logistics  Services'), ('general', 'General Services')], string="Supplier Type"
    )
    
    # Many-to-many field to store available roles for the carrier.
    available_roles = fields.Many2many('omnifreight.roles', compute="_compute_available_roles", store=False)

    state_required = fields.Boolean(string="Requires State", compute="_compute_state_required", store=True)
    
    last_updated = fields.Date(compute='_compute_write_date_only')
    
    is_outdated = fields.Boolean(compute="_compute_is_outdated")
    
    is_linked_to_company = fields.Boolean(compute="_compute_is_other", store=True)

    unloc_city_id = fields.Many2one('unloc.city', string="Contact City", domain="[('country_id', '=', un_country_id)]")
    # ZIP Code selection field
    zip_code_id = fields.Many2one(
        'unloc.city.zip', 
        string="Zip Code", 
        domain="[('un_city_id', '=', unloc_city_id)]",
        context= {
            'create': True,
            'no_open': True,
        }
    )

    # Individual religion dropdown
    omnifreight_individual_religion = fields.Selection([
       ('christian', 'Christian'),
       ('muslim', 'Muslim'),
       ('hindu', 'Hindu'),
       ('buddhist', 'Buddhist'),
       ('jewish', 'Jewish'),
       ('other', 'Other')
   ], string="Religion")
  
    is_contact_completed = fields.Boolean()
  
    # New computed HTML field to show a badge
    contact_status_badge = fields.Html(
        string="Contact Status Badge",
        compute="_compute_contact_status_badge",
        store=False,
    )
    reffered_by = fields.Many2one('res.partner', string="Referred By", domain="[('is_company', '=', False)]")
    
    contact_tag_display = fields.Html(
        string="Contact Tag Display",
        compute="_compute_contact_tag_display",
        store=False,
    )
    @api.model
    def _address_fields(self):
        """Returns the list of address fields that are synced from the parent."""
        return list(ADDRESS_FIELDS_CONTACTS)
    
    def address_get(self, adr_pref=None):
        """ Find contacts/addresses of the right type(s) by doing a depth-first-search
        through descendants within company boundaries (stop at entities flagged ``is_company``)
        then continuing the search at the ancestors that are within the same company boundaries.
        Defaults to partners of type ``'default'`` when the exact type is not found, or to the
        provided partner itself if no type ``'default'`` is found either. """
        adr_pref = set(adr_pref or [])
        if 'contact' not in adr_pref:
            adr_pref.add('contact')
        result = {}
        visited = set()
        for partner in self:
            current_partner = partner
            while current_partner:
                to_scan = [current_partner]
                # Scan descendants, DFS
                while to_scan:
                    record = to_scan.pop(0)
                    visited.add(record)
                    if record.types in adr_pref and not result.get(record.types):
                        result[record.types] = record.id
                    if len(result) == len(adr_pref):
                        return result
                    to_scan = [c for c in record.child_ids
                                 if c not in visited
                                 if not c.is_company] + to_scan

                # Continue scanning at ancestor if current_partner is not a commercial entity
                if current_partner.is_company or not current_partner.parent_id or not current_partner.company_ids:
                    break
                current_partner = current_partner.parent_id if current_partner.parent_id else current_partner.company_ids

        # default to type 'contact' or the partner itself
        default = result.get('contact', self.id or False)
        for adr_type in adr_pref:
            result[adr_type] = result.get(adr_type) or default
        return result
class FormatContactAddressMixin(models.AbstractModel):
    _name = "format.contact.address.mixin"
    _description = 'Address Format'

    def _extract_fields_from_address(self, address_line):
        """
        Extract keys from the address line.
        For example, if the address line is "zip: %(zip)s, city: %(city)s.",
        this method will return ['zip', 'city'].
        """
        address_fields = ['%(' + field + ')s' for field in ADDRESS_FIELDS_CONTACTS]
        return sorted([field[2:-2] for field in address_fields if field in address_line], key=address_line.index)