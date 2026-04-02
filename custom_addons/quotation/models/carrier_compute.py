from odoo import api, fields, models
from .route_logic import compute_write_date_only

class CarrierCompute(models.AbstractModel):
    _name = 'carrier.compute'
    _description = 'Contacts'
    
    # Computes the first and last name from the 'name' field, splitting by the first space.
    @api.depends('name', 'write_date')
    def _compute_name(self):
        for record in self:
            if record.name:
                names = record.name.strip().split(' ', 1)
                record.first_name = names[0] if len(names) > 0 else ''
                record.last_name = names[1].upper() if len(names) > 1 else ''
            else:
                record.first_name = ''
                record.last_name = ''

    @api.onchange('name', 'is_company')
    def _onchange_name_caps(self):
        for record in self:
            if record.is_company and record.name:
                record.name = record.name.upper()

                
    # Updates the 'name' field when either 'first_name' or 'last_name' is changed.
    def _inverse_name(self):
        """Update the name field when first_name or last_name is modified."""
        for record in self:
            # Ensure the last name is in uppercase
            last_name = (record.last_name or '').upper()
            computed_name = f"{record.first_name or ''} {last_name}".strip()
            record.name = computed_name

                
    # Computes whether a partner is an employee by checking the HR employee data.
    def _compute_is_employee(self):
        """Compute whether partner is an employee."""
        employee_partners = self.env['hr.employee'].search([('work_contact_id', 'in', self.ids)]).mapped('work_contact_id')
        
        for record in self:
            is_employee = record in employee_partners
            
            if record.is_employee != is_employee:
                record.sudo().write({'is_employee': is_employee})
                
    # Calls a method to compute the write date logic for the 'route_logic' model.
    def _compute_write_date_only(self):
        compute_write_date_only(self)
        
    # Determines if the country of the carrier is part of the EU based on the country code.
    @api.depends('country_id')
    def _compute_is_in_eu(self):
        for record in self:
            record.is_in_eu = record.country_id.code in self.EU_COUNTRY_CODES
        
    # Computes a 'target_key' based on the 'target_id' field and maps it to a string value.
    @api.depends('target_id')
    def _compute_target_key(self):
        for record in self:
            if record.target_id:
                # Map target_id to the corresponding string value
                target_mapping = {
                    16: 'target_1a',  
                    17: 'target_1b',  
                    18: 'target_1c',  
                }
                record.target_key = target_mapping.get(record.target_id.id, False)
            else:
                record.target_key = False
                
     # Computes a 'target_key' based on the 'target_id' field and maps it to a string value.
    @api.depends('target_id_segment_two')
    def _compute_target_keys(self):
        for record in self:
            if record.target_id_segment_two:
                # Map target_id to the corresponding string value
                target_mapping = {
                    19: 'target_2a',  
                    20: 'target_2b',  
                    21: 'target_2c',
                }
                record.target_keys = target_mapping.get(record.target_id_segment_two.id, False)
            else:
                record.target_keys = False
                
    @api.depends('segment_id')
    def _compute_segment_key(self):
        for record in self:
            if record.segment_id:
                # Get the segment codes from the related segments.
                # It is assumed that the segment model has a field "code".
                codes = record.segment_id.mapped('code')
                if 'segment_1' in codes:
                    record.segment_key = 'segment_1'
                else:
                    record.segment_key = False
            else:
                record.segment_key = False
                
    @api.depends('segment_id_two')
    def _compute_segment_keys(self):
        for record in self:
            if record.segment_id_two:
                # Get the segment codes from the related segments.
                # It is assumed that the segment model has a field "code".
                codes = record.segment_id_two.mapped('code')
                if 'segment_2' in codes:
                    record.segment_keys = 'segment_2'
                else:
                    record.segment_keys = False
            else:
                record.segment_keys = False

    # Computes whether to hide subcategories based on specific target names.
    @api.depends('target_id')
    def _compute_hide_subcategories(self):
        for record in self:
            record.hide_subcategories = record.target_id.name in [
                'Target 1C: Worldwide Freight Forwarders & Traders dealing with Africa', 
            ]
            
     # Computes whether to hide subcategories based on specific target names.
    @api.depends('target_id_segment_two')
    def _compute_hide_subcategories_two(self):
        for record in self:
            record.hide_subcategories_two = record.target_id_segment_two.name in [
                'Target 2C: Worldwide Freight Forwarders needing logistics solutions in Europe',
                'Target 2B: Chinese companies in Europe'
            ]
    
    # Computes the available roles based on the company categories and parent-child relationships.
    @api.depends('company_ids', 'company_ids.company_category', 'company_ids.supplier_type', 'parent_id')
    def _compute_available_roles(self):
        for record in self:
            valid_roles = self.env['omnifreight.roles']
            role_types = set()

            # Check both parent and company IDs for roles
            companies_to_check = []
        
            if record.parent_id:
                companies_to_check.append(record.parent_id)
            if record.company_ids:
                companies_to_check.extend(record.company_ids)

            # Loop through companies to determine valid role types.
            if companies_to_check:
                for company in companies_to_check:
                    if company.company_category == 'client':
                        role_types.add('client')
                    elif company.company_category == 'supplier':
                        if company.supplier_type == 'logistics':
                            role_types.add('logistics_supplier')
                        elif company.supplier_type == 'general':
                            role_types.add('general_supplier')
                    elif company.company_category == 'organizations':
                        role_types.add('organization')
            else:
                # If no companies, determine role based on the current record.
                if record.company_category == 'client':
                    role_types.add('client')
                elif record.company_category == 'supplier':
                    if record.supplier_type == 'logistics':
                        role_types.add('logistics_supplier')
                    elif record.supplier_type == 'general':
                        role_types.add('general_supplier')
                elif record.company_category == 'organizations':
                    role_types.add('organization')
                        

            # Fetch the valid roles from the 'omnifreight.roles' model.
            if role_types:
                valid_roles = self.env['omnifreight.roles'].search([('role_type', 'in', list(role_types))])
                
            # Assign valid roles to the record.
            record.available_roles = valid_roles
            
    @api.depends('country_id')
    def _compute_state_required(self):
        """Compute whether the country requires a state (US or Australia)"""
        # This method sets the `state_required` field to `True` if the selected country is the United States or Australia
        for record in self:
            if record.country_id.name in ['United States', 'Australia']:
                record.state_required = True
            else:
                record.state_required = False
                
    @api.depends('last_updated')
    def _compute_is_outdated(self):
        """Computes if the last_updated date is older than 30 days"""
        today = fields.Date.today()
        for record in self:
            record.is_outdated = (record.last_updated and (today - record.last_updated).days >= 30)
            
    @api.depends('parent_id', 'company_ids')
    def _compute_is_other(self):
        """Computes if the individual is linked to any company"""
        for record in self:
            record.is_linked_to_company = bool(record.parent_id or record.company_ids)

    @api.onchange('country_id')
    def _onchange_country_id(self):
        """Clear the city and ZIP code when the country changes."""
        self.unloc_city_id = False
        self.zip_code_id = False
        
    @api.depends('segment_id', 'segment_id_two')
    def _compute_requires_subcategories(self):
        for record in self:
            record.requires_subcategory = bool(record.segment_id)
            record.requires_subcategory_two = bool(record.segment_id_two)
            
    @api.depends('is_contact_completed')
    def _compute_contact_status_badge(self):
        """Compute the status badge HTML based on is_contact_completed.
        Returns a green 'Completed' badge if true, otherwise a red 'Incomplete' badge."""
        for record in self:
            if record.is_contact_completed:
                record.contact_status_badge = '<span style="color:green">Completed</span>'
            else:
                record.contact_status_badge = '<span style="color:red">Incomplete</span>'        
    
    @api.depends('company_category', 'company_type')
    def _compute_contact_tag_display(self):
        """Compute the contact tag HTML with colors, border, and darker text.
        Returns blue 'Client' badge if client, purple 'Supplier' badge if supplier and teal 'Organization' badge if organization and no tag for individual contacts."""
        for record in self:
            if record.company_type == 'person':
                record.contact_tag_display = ''
                continue
            
            if record.company_category == 'client':
                record.contact_tag_display = (
                    '<span style="'
                    'color:#0369a1;'
                    'border: 1px solid #0284c7;'
                    'background-color:#eff6ff;'
                    'padding: 1px 12px;'
                    'border-radius: 16px;'
                    'font-weight: 500;'
                    'display: inline-block;'
                    '">Client</span>'
                )
            elif record.company_category == 'supplier':
                record.contact_tag_display = (
                    '<span style="'
                    'color:#6b21a8;'
                    'border: 1px solid #9333ea;'
                    'background-color:#faf5ff;'
                    'padding: 1px 12px;'
                    'border-radius: 16px;'
                    'font-weight: 500;'
                    'display: inline-block;'
                    '">Supplier</span>'
                )
            elif record.company_category == 'organizations':
                record.contact_tag_display = (
                    '<span style="'
                    'color:#065f46;'
                    'border: 1px solid #10b981;'
                    'background-color:#ecfdf5;'
                    'padding: 1px 12px;'
                    'border-radius: 16px;'
                    'font-weight: 500;'
                    'display: inline-block;'
                    '">Organization</span>'
                )
            else:
                record.contact_tag_display = ''

           