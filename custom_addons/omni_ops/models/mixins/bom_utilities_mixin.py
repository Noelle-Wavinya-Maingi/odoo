# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BomUtilitiesMixin(models.AbstractModel):
    """Mixin for BOM utilities including field renaming and display name computation."""
    _name = 'omni.bom.utilities.mixin'
    _description = 'BOM Utilities Mixin'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('service_scope', 'product_tmpl_id')
    def _compute_display_name(self):
        """Compute display name for process templates with service scope."""
        for record in self:
            if hasattr(record, 'type') and hasattr(record, 'service_scope'):
                if record.type == 'service' and record.service_scope and record.product_tmpl_id:
                    # Get service scope labels
                    scope_mapping = {
                        'fob': 'FOB',
                        'freight': 'Freight',
                        'lod': 'Destination',
                        'fob_freight': 'FOB, Freight',
                        'freight_lod': 'Freight, Destination',
                        'fob_lod': 'FOB, Destination',
                        'fob_freight_lod': 'FOB, Freight, Destination',
                    }
                    
                    scope_label = scope_mapping.get(record.service_scope, record.service_scope)
                    record.display_name = f"Template for {scope_label}"
                else:
                    # Use default display name for non-service records
                    if hasattr(super(), '_compute_display_name'):
                        super(BomUtilitiesMixin, record)._compute_display_name()
                    else:
                        record.display_name = record.name or record.id
            else:
                # Fallback for records without service scope
                record.display_name = record.name or record.id

    @api.model
    def _rename_field_descriptions(self):
        """Rename field descriptions for better freight operations terminology."""
        # Get the mrp.bom model
        bom_model = self.env['mrp.bom']
        
        # Rename field descriptions
        if hasattr(bom_model, '_fields'):
            # Rename BoM Type to Process Type
            if 'type' in bom_model._fields:
                bom_model._fields['type'].string = 'Process Type'
            
            # Rename Product to Service
            if 'product_tmpl_id' in bom_model._fields:
                bom_model._fields['product_tmpl_id'].string = 'Service'
            
            # Rename Manufacturing Readiness to Operations Readiness
            if 'ready_to_produce' in bom_model._fields:
                bom_model._fields['ready_to_produce'].string = 'Operations Readiness'
