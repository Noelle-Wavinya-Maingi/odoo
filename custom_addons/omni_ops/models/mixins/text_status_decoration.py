from odoo import models, api

class ColorStatusDecorationMixin(models.AbstractModel):
    _name = 'omni.color.status.decoration.mixin'
    _description = 'Color Status Decoration Mixin'

    @api.model
    def get_variance_status_decoration(self, variance_amount):
        """Get decoration class for variance amount.
        
        Returns:
            - 'decoration-success' (green) when variance < 0 (spending less than budgeted)
            - 'decoration-danger' (red) when variance > 0 (spending more than budgeted)
            - '' (no decoration) when variance == 0
        """
        if variance_amount is None:
            return ''
        if variance_amount < 0:
            return 'decoration-success'
        elif variance_amount > 0:
            return 'decoration-danger'
        return ''
    
    @api.model
    def get_expense_submitted_decoration(self, expense_id):
        """Get decoration for expense link when expense is submitted, approved, or done.
        
        Returns 'decoration-expense-submitted' (custom purple #714B67) when expense is submitted, approved, or done, otherwise empty string.
        """
        if not expense_id:
            return ''
        
        expense = self.env['hr.expense'].browse(expense_id)
        if not expense.exists():
            return ''
        
        # Check if expense state is submitted, approved, or done
        # Also check expense sheet states: submit, approve, post, done
        expense_state = expense.state
        sheet_state = expense.sheet_id.state if expense.sheet_id else False
        if (expense_state in ('submitted', 'approved', 'done') or
            (sheet_state and sheet_state in ('submit', 'approve', 'post', 'done'))):
            return 'decoration-expense-submitted'
        return ''

