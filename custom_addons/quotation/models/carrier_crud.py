from odoo import models, api

class CarrierCrud(models.AbstractModel):
    _name = 'carrier.crud'
    _description = 'Carrier CRUD Methods'
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create method to handle both company type and employee status"""
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
        
        for vals in vals_list:
            # Process company associations if provided 
            if 'company_ids' in vals and vals.get('company_ids'):
                new_company_ids = []
                for command in vals['company_ids']:
                    if command[0] == 6:
                        new_company_ids = command[2]
                    elif command[0] == 4:
                        new_company_ids.append(command[1])
                 
                # Assign the first company as the parent if available 
                if new_company_ids:
                    vals['parent_id'] = new_company_ids[0]
            
            
            
        res = super().create(vals_list)
        
        res._compute_name()
        
        # Automatically set as an employee if context allows for it
        if self.env.context.get('default_work_contact_id') or 'hr.employee' in self.env.context.get('active_model', ''):
            res.is_employee = True
            
        return res
    
    def write(self, vals):
        """Override write method to handle both company type and employee status updates."""
        

        # Handle company association
        if 'company_ids' in vals:
            company_ids_commands = vals.get('company_ids')  
           
            self.ensure_one()
            existing_company_ids = self.company_ids.ids

            new_company_ids = list(existing_company_ids)
            removed_ids = []
            has_replace_command = False

            for command in company_ids_commands:
                if command[0] == 6:
                    has_replace_command = True
                    new_company_ids = command[2]
                elif command[0] == 4:
                    if command[1] not in new_company_ids:
                        new_company_ids.append(command[1])
                elif command[0] == 3:
                    if command[1] in new_company_ids:
                        new_company_ids.remove(command[1])
                    removed_ids.append(command[1])
            
            # Determine if parent_id should be updated   
            current_parent_id = self.parent_id.id if self.parent_id else False
            
            if new_company_ids:
                if has_replace_command or (current_parent_id and current_parent_id in removed_ids) or not current_parent_id:
                    vals['parent_id'] = new_company_ids[0]
            elif current_parent_id and current_parent_id in removed_ids:
                vals['parent_id'] = False
                
                # Clear VAT if parent_id is cleared
                if self.vat:
                    vals['vat'] = False
                
        res = super().write(vals)
        
        self._compute_is_employee()
        
        if 'name' in vals:
            self._compute_name()
            
        return res
    
    @api.model
    def _update_employee_status(self):
        """Update employee status for all partners."""
        records = self.search([])
        
        if records:
            records._compute_is_employee()
            
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        context = self._context
        
        record_id = context.get('default_parent_id') or context.get('active_id')
        if record_id:
            record = self.browse(record_id)
            
            # Compute available_roles based on the record
            role_types = set()
            if record.company_category == 'client':
                role_types.add('client')
            elif record.company_category == 'supplier':
                if record.supplier_type == 'logistics':
                    role_types.add('logistics_supplier')
                elif record.supplier_type == 'general':
                    role_types.add('general_supplier')
            
            # Search for roles based on role_types
            if role_types:
                available_roles = self.env['omnifreight.roles'].search([('role_type', 'in', list(role_types))])
                res['available_roles'] = available_roles.ids
        
        return res