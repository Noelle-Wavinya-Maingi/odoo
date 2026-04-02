from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)

class WorkflowStage(models.Model):
    """Configurable workflow stages per industry"""
    _name = 'workflow.stage'
    _description = 'Workflow Stage'
    _order = 'industry_id, sequence'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    
    industry_id = fields.Many2one(
        'industry.type', 
        string='Industry', 
        required=True, 
        ondelete='cascade',
        index=True
    )
    
    # Stage properties
    fold = fields.Boolean(
        string='Folded in Kanban',
        help="This stage is folded in the kanban view when empty"
    )
    requires_approval = fields.Boolean(string='Requires Approval')
    approver_group = fields.Many2one(
        'res.groups', 
        string='Approver Group',
        help="Group that can approve this stage"
    )
    
    # Allowed transitions
    allowed_next_stages = fields.Many2many(
        'workflow.stage', 
        'workflow_stage_transition_rel',
        'stage_id', 'next_stage_id',
        string='Allowed Next Stages',
        domain="[('industry_id', '=', industry_id)]"
    )
    
    # Automation
    auto_trigger_action = fields.Selection([
        ('create_invoice', 'Create Invoice'),
        ('create_picking', 'Create Picking'),
        ('send_email', 'Send Email'),
        ('update_inventory', 'Update Inventory'),
        ('create_task', 'Create Task'),
        ('notify_user', 'Notify User'),
    ], string='Auto Trigger Action')
    
    auto_action_model = fields.Char(
        string='Auto Action Model',
        help="Technical model name for auto action"
    )
    auto_action_method = fields.Char(
        string='Auto Action Method',
        help="Technical method name for auto action"
    )
    
    # UI Properties
    color = fields.Integer(string='Color Index', default=0)
    description = fields.Text(string='Description')
    
    # Statistics
    stage_duration = fields.Integer(
        string='Expected Duration (hours)',
        help="Expected time to complete this stage"
    )
    
    # Constraints
    # _constraints = [
    #     Constraint(name='unique_industry_code', sql_constraint='unique(industry_id, code)', 
    #                message="Stage code must be unique per industry!"),
    # ]
    
    _uniq_code = models.Constraint('unique(industry_id, code)', 'Stage code must be unique per industry!')

    @api.constrains('allowed_next_stages')
    def _check_allowed_next_stages(self):
        """Prevent self-referential transitions"""
        for record in self:
            if record in record.allowed_next_stages:
                raise ValidationError(
                    f"Stage '{record.name}' cannot transition to itself"
                )

    def get_next_stages(self):
        """Get all possible next stages"""
        self.ensure_one()
        return self.allowed_next_stages or self.search([
            ('industry_id', '=', self.industry_id.id),
            ('sequence', '>', self.sequence)
        ])

    def execute_auto_action(self, record):
        """Execute auto action on a record"""
        self.ensure_one()
        if not self.auto_trigger_action:
            return False
        
        try:
            if self.auto_action_model and self.auto_action_method:
                model = self.env.get(self.auto_action_model)
                if model and hasattr(model, self.auto_action_method):
                    getattr(model, self.auto_action_method)(record)
                    return True
        except Exception as e:
            _logger.error(f"Error executing auto action: {e}")
        
        return False