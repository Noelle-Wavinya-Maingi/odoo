from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime


class OmniMrpProduction(models.Model):
    """Extend manufacturing orders to support Omnifreight service products."""
    _inherit = 'mrp.production'

    # === CONSTANTS ===
    PRODUCT_TYPES = ('consu', 'product', 'omni_service')

    # === FIELDS ===
    product_id = fields.Many2one(
        'product.product', 'Product',
        check_company=True, index=True,
        domain=f"[('type', 'in', {PRODUCT_TYPES})]",
        help="Product to be manufactured"
    )
    product_tmpl_id = fields.Many2one(
        'product.template', 'Omnifreight Product Template',
        check_company=True, index=True,
        domain=f"[('type', 'in', {PRODUCT_TYPES})]",
        help="Product to be manufactured"
    )

    # === SALES MODULE FIELDS ===
    route_id = fields.Many2one('omnifreight.route', string='Route', compute='_compute_sale_fields', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', compute='_compute_sale_fields', store=True)
    freight_carrier_id = fields.Many2one('res.partner', string='Carrier')
    buyer_id = fields.Many2one('res.partner', string='Buyer/ Consignee')
    seller_id = fields.Many2one('res.partner', string='Seller/ Shipper')
    incoterm_to = fields.Many2one(related='sale_line_id.order_id.incoterm_to_id', string='Incoterms To', store=True)
    incoterm_from = fields.Many2one(related='sale_line_id.order_id.incoterm_id', string='Incoterms From', store=True)
    transporter_id = fields.Many2one('res.partner', string='Haulier', compute='_compute_sale_fields', store=True)
    city_from = fields.Many2one('unloc.city', string='City From', compute='_compute_sale_fields', store=True)
    city_to = fields.Many2one('unloc.city', string='City To', compute='_compute_sale_fields', store=True)
    supplier_id = fields.Many2one('res.partner', string='Transporter', compute='_compute_sale_fields', store=True)
    
    # Package Details
    package_details = fields.Many2one('omnifreight.package.details', string='Package Details', compute='_compute_sale_fields', store=True)
    container_type = fields.Selection(related='package_details.container_type', string='Container Type', store=True)
    contents = fields.Many2many(related='package_details.contents', string='Contents')
    content_classification = fields.Selection(related='package_details.content_classification', string='Content Classification', store=True)
    soc = fields.Boolean(related='package_details.soc', string='SOC', store=True)
    weight = fields.Float(related='package_details.weight', string='Weight', store=True, readonly=False)
    volume = fields.Float(related='package_details.volume', string='Volume', store=True, readonly=False)
    
    # Shipment fields
    pol = fields.Char(string='POL', compute='_compute_port_fields', store=True)
    pod = fields.Char(string='POD', compute='_compute_port_fields', store=True)

    # === OPERATIONS FIELDS ===
    booking_ref = fields.Char(string='Booking Reference')
    carrier_agent_id = fields.Many2one('res.partner', string='Carrier Agent', compute='_compute_carrier_agent_id', store=True)
    vessel_id = fields.Many2one('freight.vessel', string='Vessel')
    etd = fields.Datetime(string='ETD')
    eta = fields.Datetime(string='ETA')
    
    # === BOM OPERATIONS DISPLAY ===
    service_scope = fields.Selection(related='bom_id.service_scope', string='Service Scope', store=True)
    bom_type = fields.Selection(related='bom_id.type', string='BOM Type', store=True)
    quote_type = fields.Selection(related='sale_line_id.order_id.quote_type', string='Quote Type', store=True)
    document_ids = fields.One2many('omnifreight.documents', 'production_id', string='Documents')
    
    # Computed field to determine which service scopes are active based on quote_type
    has_fob_service = fields.Boolean(string='Has FOB Service', compute='_compute_service_flags')
    has_freight_service = fields.Boolean(string='Has Freight Service', compute='_compute_service_flags')
    has_lod_service = fields.Boolean(string='Has LOD Service', compute='_compute_service_flags')
    
    @api.depends('quote_type', 'service_scope')
    def _compute_service_flags(self):
        """Determine which services are active based on quote_type or service_scope."""
        for production in self:
            # Map quote types to service flags
            # Check quote_type first (from sale order), then fall back to service_scope (from BOM)
            service_type = production.quote_type or production.service_scope or ''
            
            # Map quote_type values to service components
            # quote_type values: fob_only, fob_freight, freight_only, lod_only, fob_freight_lod, freight_dap
            # service_scope values: fob, fob_freight, freight, lod, fob_freight_lod, freight_lod
            if service_type in ('fob_only', 'fob'):
                production.has_fob_service = True
                production.has_freight_service = False
                production.has_lod_service = False
            elif service_type in ('fob_freight',):
                production.has_fob_service = True
                production.has_freight_service = True
                production.has_lod_service = False
            elif service_type in ('freight_only', 'freight'):
                production.has_fob_service = False
                production.has_freight_service = True
                production.has_lod_service = False
            elif service_type in ('lod_only', 'lod'):
                production.has_fob_service = False
                production.has_freight_service = False
                production.has_lod_service = True
            elif service_type in ('fob_freight_lod',):
                production.has_fob_service = True
                production.has_freight_service = True
                production.has_lod_service = True
            elif service_type in ('freight_dap', 'freight_lod'):
                production.has_fob_service = False
                production.has_freight_service = True
                production.has_lod_service = True
            else:
                production.has_fob_service = False
                production.has_freight_service = False
                production.has_lod_service = False
    
    # Service operation categories - now editable directly
    fob_operations = fields.One2many('mrp.workorder', 'production_id', 
                                    domain=[('freight_service_type', '=', 'fob')], 
                                    string='FOB Operations')
    freight_operations = fields.One2many('mrp.workorder', 'production_id', 
                                        domain=[('freight_service_type', '=', 'freight')], 
                                        string='Freight Operations')
    destination_operations = fields.One2many('mrp.workorder', 'production_id', 
                                            domain=[('freight_service_type', '=', 'lod')], 
                                            string='Destination Operations')
    additional_operations_ids = fields.One2many('additional.file.operations', 'production_id', string='Additional Operations', help="Additional operations specific to this manufacturing order")
    
    # === BUDGET FIELDS ===
    budget_ids = fields.One2many(
        'omni.mrp.budget', 
        'production_id', 
        string='Budgets'
    )
    budget_id = fields.Many2one(
        'omni.mrp.budget',
        string='Active Budget',
        compute='_compute_active_budget',
        store=True
    )
    has_budget = fields.Boolean(
        'Has Budget', 
        compute='_compute_has_budget', 
        store=True
    )
    budget_state = fields.Selection(
        related='budget_id.state', 
        string='Budget Status',
        readonly=True
    )
    
    # === ONCHANGE METHODS ===
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Handle product changes for omni_service products."""
        super()._onchange_product_id()
        if self.product_id and self.product_id.type == 'omni_service':
            self.product_uom_id = self.product_id.uom_id
            self.product_qty = 1.0

    # === NAME GENERATION ===
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to use custom file numbering for freight operations."""
        for vals in vals_list:
            # Check if this is a freight/service operation MO
            if vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                # Use custom naming for service products
                if product.type == 'omni_service':
                    if not vals.get('name') or vals['name'] == _('New'):
                        # Use custom file numbering sequence
                        vals['name'] = self.env['ir.sequence'].next_by_code('omni.mrp.production.file') or _('New')
            # For non-service MOs, let the default logic handle it
        return super().create(vals_list)
    
    # === CONSTRAINTS ===
    @api.constrains('bom_id', 'product_id')
    def _check_service_bom_compatibility(self):
        """Validate that service BOMs are only used with service products."""
        for production in self:
            if (production.bom_id and production.bom_id.type == 'service' and
                production.product_id and production.product_id.type != 'omni_service'):
                raise ValidationError(_(
                    "Service BOMs can only be used with Omnifreight service products. "
                    "Product '%s' is not a service product." % production.product_id.name
                ))

    # === BUSINESS METHODS ===
    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id')
    def _compute_workorder_ids(self):
        """Override to handle service BOMs properly."""
        if self.bom_id and self.bom_id.type == 'service':
            self._create_service_workorders()
        else:
            super()._compute_workorder_ids()

    def _create_service_workorders(self):
        """Create work orders for service BOMs without work centers."""
        self.ensure_one()
        self.workorder_ids.unlink()
        
        if not self.bom_id or not self.bom_id.operation_ids:
            return
            
        workorder_vals = []
        for operation in self.bom_id.operation_ids.sorted('sequence'):
            # Get or create a workcenter for this service type
            workcenter_id = False
            if operation.service_type:
                workcenter = self.env['mrp.workcenter'].search([
                    ('name', 'ilike', operation.service_type)
                ], limit=1)
                if not workcenter:
                    workcenter = self.env['mrp.workcenter'].create({
                        'name': f'{operation.service_type.upper()} Operations',
                        'code': operation.service_type.upper(),
                    })
                workcenter_id = workcenter.id
            
            workorder_vals.append({
                'name': operation.name,
                'operation_id': operation.id,
                'production_id': self.id,
                'product_uom_id': self.product_uom_id.id,
                'qty_produced': 0.0,
                'qty_remaining': self.product_qty,
                'state': 'pending',
                'sequence': operation.sequence,
                'workcenter_id': workcenter_id,
            })
        
        if workorder_vals:
            self.workorder_ids = [(0, 0, vals) for vals in workorder_vals]
            # Skip dependency setup for service BOMs to avoid cyclic dependency errors
            # Service operations can run independently without complex dependencies

    def _setup_operation_dependencies(self):
        """Set up operation dependencies to ensure proper sequencing for service operations."""
        self.ensure_one()
        if not self.workorder_ids:
            return
            
        # Group work orders by operation category and sort by sequence
        workorder_groups = {
            'fob': self.workorder_ids.filtered(lambda wo: wo.operation_id and wo.operation_id.service_type == 'fob').sorted('sequence'),
            'freight': self.workorder_ids.filtered(lambda wo: wo.operation_id and wo.operation_id.service_type == 'freight').sorted('sequence'),
            'lod': self.workorder_ids.filtered(lambda wo: wo.operation_id and wo.operation_id.service_type == 'lod').sorted('sequence')
        }
        
        # Set up dependencies: FOB -> Freight -> Destination
        # Only create dependencies between the last FOB and first Freight, and last Freight and first LOD
        self._add_sequential_dependencies(workorder_groups['freight'], workorder_groups['fob'])
        self._add_sequential_dependencies(workorder_groups['lod'], workorder_groups['freight'])
    
    def _add_sequential_dependencies(self, target_workorders, source_workorders):
        """Add sequential dependencies between work order groups to avoid cycles."""
        if not target_workorders or not source_workorders:
            return
        
        # Get the last work order from source group and first from target group
        last_source_wo = source_workorders[-1] if source_workorders else None
        first_target_wo = target_workorders[0] if target_workorders else None
        
        if last_source_wo and first_target_wo:
            # Only create dependency from last source to first target
            if last_source_wo not in first_target_wo.blocked_by_workorder_ids:
                first_target_wo.blocked_by_workorder_ids = [(4, last_source_wo.id)]


    # === COMPUTE METHODS ===
    @api.depends('sale_line_id')
    def _compute_carrier_agent_id(self):
        """Compute carrier_agent_id from carrier_id in connected sale order."""
        for production in self:
            order = production.sale_line_id.order_id if production.sale_line_id else None# safe attribute access with default
            production.carrier_agent_id = getattr(order, 'freight_carrier_id', False) if order else False

    @api.depends('sale_line_id')
    def _compute_sale_fields(self):
        """Compute fields from connected sale order."""
        for production in self:
            order = production.sale_line_id.order_id if production.sale_line_id else None
            if order:
                production.route_id = order.route_id
                production.partner_id = order.partner_id
                production.package_details = order.package_details_id
                production.city_to = order.lod_service_city
                production.city_from = order.city_id
                production.supplier_id = order.selected_lod_transport_rate_id.supplier_id
                selected_fob_rate = order.rate_link_ids.filtered(lambda r: r.is_selected_fob)
                if selected_fob_rate:
                    production.transporter_id = selected_fob_rate[0].rate_id.supplier_id

    @api.depends('route_id', 'sale_line_id.order_id.port_of_loading', 'sale_line_id.order_id.port_of_dispatch', 'service_scope', 'quote_type')
    def _compute_port_fields(self):
        """Compute port fields from route or individual ports based on service scope."""
        for production in self:
            if production.route_id:
                # Multi-port scenario: use route ports
                production.pol = production.route_id.departure_port_id.name
                production.pod = production.route_id.arrival_port_id.name
            else:
                # Single-port scenarios: determine based on service scope or quote_type
                order = production.sale_line_id.order_id if production.sale_line_id else None
                if order:
                    # Use quote_type if available, otherwise fall back to service_scope
                    service_type = production.quote_type or production.service_scope or ''
                    
                    if service_type in ('fob_only', 'fob') or production.has_fob_service:
                        # FOB only: POL is the port of loading
                        production.pol = order.port_of_loading.name if order.port_of_loading else False
                        production.pod = False
                    elif service_type in ('lod_only', 'lod'):
                        # LOD only: POD is the port of dispatch
                        production.pol = False
                        production.pod = order.port_of_dispatch.name if order.port_of_dispatch else False
                    else:
                        # Other scopes without route: clear both
                        production.pol = False
                        production.pod = False
                else:
                    # No order: clear both
                    production.pol = False
                    production.pod = False


    @api.onchange('date_start', 'date_finished', 'etd', 'eta')
    def _onchange_service_operation_dates(self):
        """Sync ETD/ETA with date_start/date_finished in both directions."""
        for production in self:
            if production.etd and production.etd != production.date_start:
                production.date_start = production.etd
            if production.eta and production.eta != production.date_finished:
                production.date_finished = production.eta
            if production.date_start and production.date_start != production.etd:
                production.etd = production.date_start
            if production.date_finished and production.date_finished != production.eta:
                production.eta = production.date_finished
         
    # === BUDGET METHODS ===
    
    @api.depends('budget_ids')
    def _compute_has_budget(self):
        """Check if manufacturing order has a budget."""
        for production in self:
            production.has_budget = bool(production.budget_ids)
    
    @api.depends('budget_ids')
    def _compute_active_budget(self):
        """Set the active budget (most recent non-closed budget)."""
        for production in self:
            if production.budget_ids:
                # Get most recent budget (by create_date desc)
                active_budget = production.budget_ids.sorted('create_date', reverse=True)[0]
                production.budget_id = active_budget.id
            else:
                production.budget_id = False
    
    def action_create_budget(self):
        """Create a budget for this manufacturing order."""
        self.ensure_one()
        
        if self.budget_ids:
            raise ValidationError(_("This manufacturing order already has a budget."))
        
        # Get currency from sale order or use company currency
        currency_id = self.env.company.currency_id
        if self.sale_line_id and self.sale_line_id.order_id:
            currency_id = self.sale_line_id.order_id.currency_id
        
        budget = self.env['omni.mrp.budget'].create({
            'production_id': self.id,
            'currency_id': currency_id.id,
        })
        
        # Automatically copy charges from quotation
        if self.sale_line_id and self.sale_line_id.order_id:
            budget.action_copy_charges_from_quotation()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget'),
            'res_model': 'omni.mrp.budget',
            'res_id': budget.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_budget(self):
        """View the budget for this manufacturing order."""
        self.ensure_one()
        
        if not self.budget_id:
            raise ValidationError(_("No budget found for this manufacturing order."))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget'),
            'res_model': 'omni.mrp.budget',
            'res_id': self.budget_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_open_budgets(self):
        """Open all budgets for this manufacturing order."""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Budgets'),
            'res_model': 'omni.mrp.budget',
            'domain': [('production_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
        }
         
    def write(self, vals):
        """Override write to track document changes and attach files to chatter."""
        # Capture original state before write
        original_states = self._get_original_document_states()
    
        result = super().write(vals)
    
        if 'document_ids' in vals:
            self._process_document_changes(original_states)
    
        return result

    def _get_original_document_states(self):
        """Get the original state of documents before write operation."""
        original_states = {}
        for production in self:
            original_states[production.id] = {
                'document_ids': production.document_ids.ids,
                'document_names': {doc.id: doc.filename for doc in production.document_ids}
            }
        return original_states

    def _process_document_changes(self, original_states):
        """Process document additions and removals after write operation."""
        for production in self:
            original_data = original_states.get(production.id, {})
            current_docs = production.document_ids
        
            # Find document changes
            new_docs, removed_doc_data = self._find_document_changes(original_data, current_docs)
        
            # Handle new documents
            if new_docs:
                self._handle_new_documents(production, new_docs)
        
            # Handle removed documents
            if removed_doc_data:
                self._handle_removed_documents(production, removed_doc_data)

    def _find_document_changes(self, original_data, current_docs):
        """Identify newly added and removed documents."""
        original_ids = set(original_data.get('document_ids', []))
        current_ids = set(current_docs.ids)
    
        # Find new documents
        new_doc_ids = current_ids - original_ids
        new_docs = current_docs.filtered(lambda doc: doc.id in new_doc_ids)
    
        # Find removed documents data
        removed_doc_ids = original_ids - current_ids
        removed_filenames = [
            filename for doc_id, filename in original_data.get('document_names', {}).items()
            if doc_id in removed_doc_ids and filename
        ]
    
        return new_docs, removed_filenames

    def _handle_new_documents(self, production, new_docs):
        """Handle newly added documents by creating attachments and posting messages."""
        valid_docs = new_docs.filtered(lambda doc: doc.document_upload and doc.filename)
    
        if not valid_docs:
            return
    
        attachments = []
        document_names = []
    
        for document in valid_docs:
            attachment = self._create_chatter_attachment(production, document)
            attachments.append(attachment.id)
            document_names.append(document.filename)
    
        if document_names:
            self._post_addition_message(production, document_names, attachments)

    def _handle_removed_documents(self, production, removed_filenames):
        """Handle removed documents by deleting attachments."""
        if removed_filenames:
            self._remove_chatter_attachments(production, removed_filenames)

    def _create_chatter_attachment(self, production, document):
        """Create a chatter attachment for a document."""
        return self.env['ir.attachment'].create({
            'name': document.filename,
            'datas': document.document_upload,
            'res_model': 'mrp.production',
            'res_id': production.id,
            'type': 'binary',
        })

    def _post_addition_message(self, production, document_names, attachments):
        """Post notifications about document additions to chatter."""
        document_list = "\n".join([f"• {name}" for name in document_names])
    
        production.message_post(
            body=_("The following document(s) were added:\n%s") % document_list,
            message_type="notification",
        )

    def _remove_chatter_attachments(self, production, filenames):
        """Remove chatter attachments for deleted documents."""
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.production'),
            ('res_id', '=', production.id),
            ('name', 'in', filenames)
        ])
        attachments.unlink()