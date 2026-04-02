from odoo import api, models

class CarrierOnchange(models.AbstractModel):
    _name = 'carrier.onchange'
    _description = 'Carrier Onchange method'
    
    _last_warning_time = 0
    
    
    @api.onchange('ratings_tag')
    def _onchange_ratings_tag(self):
        """
        Handle rating tag changes:
        1. Keep only the last selected tag
        2. Show warning if removing existing tags
        """
        warning = None
        
        if self._origin and  self._origin.ratings_tag and self._origin.ratings_tag != self.ratings_tag:
            return {
                    'warning': {
                        'title': 'Warning!',
                        'message': f'You are about to change a rating tag. '
                                'This may affect customer classification and reporting.'
                    }
                }

        if warning:
            return {'warning': warning}
        
    @api.onchange('segment_id')
    def _onchange_segment(self):
        """Clear target_id when segment changes"""
        warning = None
        
        self.target_segment_one = False
        
        if self._origin and  self._origin.segment_id and self._origin.segment_id != self.segment_id:
            return {
                    'warning': {
                        'title': 'Warning!',
                        'message': f'You have deselected a segment. '
                                'This may affect selected target and subcategories.'
                    }
                }
            
        if (self._origin and not self._origin.segment_id and self.segment_id):
            return {
                'warning': {
                    'title': 'Notice!',
                    'message': 'You have selected a segment. Please ensure the target and subcategories are filled.'
                }
            }
             

        if warning:
            return {'warning': warning}
        
        
    @api.onchange('segment_id_two')
    def _onchange_segment_two(self):
        """Clear target_id_segment_two when segment changes"""
        self.target_segment_two = False
        
        warning = None
        
        if self._origin and self._origin.segment_id_two and self._origin.segment_id_two != self.segment_id_two:
             return {
                    'warning': {
                        'title': 'Warning!',
                        'message': f'You have deselected a segment. '
                                'This may affect selected target and subcategories.'
                    }
                }
            
        if (self._origin and not self._origin.segment_id_two and self.segment_id_two):
            return {
                'warning': {
                    'title': 'Notice!',
                    'message': 'You have selected a segment. Please ensure the target and subcategories are filled.'
                }
            }
            
        if warning:
            return {'warning': warning}
            
        
    @api.onchange('target_segment_one')
    def _onchange_target(self):
        """Clear subcategories when target_id changes"""
        self.subcategory_ids = False
        
    @api.onchange('target_segment_two')
    def _onchange_target_two(self):
        """Clear subcategories when target_id_segment_two changes"""
        self.subcategory_ids_segment_two = False
        
        
    @api.onchange('company_ids')
    def _onchange_company_ids(self):
        """Detect additions and removals of associated companies and warn user."""
        if not self._origin.company_ids and not self.company_ids:
            return
        
        original_company_ids = set(self._origin.company_ids.ids)
        current_company_ids = set(self.company_ids.ids)
        
        removed_ids = original_company_ids - current_company_ids
        
        if not removed_ids:
            return
        
        removed_companies = self.env['res.partner'].browse(list(removed_ids))
        
        warning = None
        
        if removed_companies:
            company_names = ', '.join(removed_companies.mapped('name'))
            return{
                'warning': {
                    'title': 'Warning: Companies Removed',
                    'message': f'You are about to remove the following companies: {company_names}. '
                          'This may affect related operations and records.'
                }
            }
            
        if warning:
            self.env.context = dict(self.env.context, pending_warning=warning)
            return self.with_delay()._show_company_warning()

        
    @api.onchange('incoterm_ids')
    def _onchange_incoterm_ids(self):
        """Detect additions and removals of incoterms and warn user."""
        if not self._origin.incoterm_ids and not self.incoterm_ids:
            return
        
        original_incoterm_ids = set(self._origin.incoterm_ids.ids)
        current_incoterm_ids = set(self.incoterm_ids.ids)
        
        removed_ids = original_incoterm_ids - current_incoterm_ids
       
        if not removed_ids:
            return
        
        removed_incoterms = self.env['incoterms'].browse(list(removed_ids))
        
        warning = None

        if removed_incoterms:
            incoterm_names = ', '.join(removed_incoterms.mapped('name'))
            return{
                'warning': {
                    'title': 'Warning!',
                    'message': f'You are about to remove: {incoterm_names}. '
                              'This may affect shipping and delivery terms for related orders.'
                }
            }
            
        if warning:
            self.env.context = dict(self.env.context, pending_warning=warning)
            return self.with_delay()._show_incoterms_warning()
        
    @api.model
    def with_delay(self):
        """Helper method to add delay to the warning"""
        def delayed_warning():
            warning = self.env.context.get('pending_warning')
            if warning:
                return {'warning': warning}
        return delayed_warning

    def _show_company_warning(self):
        """Show the warning after a delay"""
        return self.env.context.get('pending_warning')
    
    def _show_incoterms_warning(self):
        """Show the warning after a delay"""
        return self.env.context.get('pending_warning')
    
    
    @api.onchange('unloc_city_id')
    def _onchange_unloc_city(self):
        """Auto-fill the country based on the selected city."""
        if self.unloc_city_id:
            self.un_country_id = self.unloc_city_id.country_id
        else:
            self.un_country_id = False
        # Clear the zip code when the city changes
        self.zip_code_id  = False 
        self.zip = ''   
        self.city = ''

    @api.onchange('zip_code_id')
    def _onchange_zip_code(self):
        """ Auto-assign city when a ZIP code is selected """
        if self.zip_code_id:
            self.unloc_city_id = self.zip_code_id.un_city_id  
            self.zip = self.zip_code_id.name
        else:
            self.zip = ''

    @api.onchange('country_id')
    def _onchange_country_id_clear_fields(self):
        """Clear the city and zip code when the country changes."""
        self.unloc_city_id = False
        self.zip_code_id = False 
        self.zip = ''
        
    @api.onchange('street', 'street2', 'zip', 'city', 'state_id', 'country_id', 'line3', 'unloc_city_id', 'zip_code_id')
    def _onchange_address_fields(self):
        """Update the 'contact_address' and related fields whenever address components change."""
        for record in self:
            # Lookup state by the name of the UNLOC city
            if record.unloc_city_id:
                state = self.env['res.country.state'].search([('name', '=', record.unloc_city_id.name)], limit=1)
                if state:
                    record.state_id = state.id
                record.city = record.unloc_city_id.name  # Always set city from UNLOC

            # Keep zip in sync with zip_code_id
            if record.zip_code_id:
                record.zip = record.zip_code_id.name

            # Build contact_address dynamically
            parts = []
            if record.street:
                parts.append(record.street)
            if record.street2:
                parts.append(record.street2)
            if record.line3:
                parts.append(record.line3)

            zip_part = record.zip or ''
            city_part = record.city or ''
            if zip_part and city_part:
                parts.append(f"{zip_part} {city_part}")
            elif zip_part:
                parts.append(zip_part)
            elif city_part:
                parts.append(city_part)

            if record.state_id:
                parts.append(record.state_id.name)
            if record.country_id:
                parts.append(record.country_id.name)

            # Include parent company name if exists
            address_text = "\n".join(parts)
            if record.parent_id:
                address_text = f"{record.parent_id.name}\n{address_text}"

            # Update the contact_address field
            record.contact_address = address_text 