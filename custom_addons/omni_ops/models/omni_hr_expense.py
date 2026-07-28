# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OmniHrExpense(models.Model):
    """Extend hr.expense to link with manufacturing orders and budget lines."""
    _inherit = 'hr.expense'

    # === OPERATIONS MODULE FIELDS ===
    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order / File Number',
        help='Manufacturing order (file number) this expense is related to',
        tracking=True,
        index=True,
    )
    # budget_line_id itself is defined generically on operations.budget_line's
    # hr.expense extension (operations/models/hr_expense.py) — only the freight-specific
    # domain narrowing is overridden here.
    budget_line_id = fields.Many2one(
        domain="[('budget_id.production_id', '=', production_id), ('expense_id', '=', False)]",
    )
    file_number = fields.Char(
        string='File Number',
        related='production_id.name',
        store=True,
        readonly=True,
        help='File number from the manufacturing order',
    )

    bill_reference = fields.Char(string='Bill Reference')

    # === ONCHANGE METHODS ===
    @api.onchange('production_id')
    def _onchange_production_id(self):
        """Clear budget_line_id when production_id changes."""
        if self.production_id != self._origin.production_id:
            self.budget_line_id = False

    @api.onchange('budget_line_id')
    def _onchange_budget_line_id_production(self):
        """Set production_id from the selected budget line's header. Name/payment_mode
        generation is handled generically by operations' own onchange on this field."""
        if self.budget_line_id and self.budget_line_id.budget_id:
            self.production_id = self.budget_line_id.budget_id.production_id

    # === METHODS ===
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to update budget line actual_amount when expense is created with budget_line_id."""
        expenses = super().create(vals_list)

        # Update budget line for expenses created with budget_line_id and amount
        for expense in expenses:
            if expense.budget_line_id and expense.total_amount_currency:
                expense._update_budget_line_amount()

        return expenses

    def write(self, vals):
        """Override write to update budget line actual_amount when expense is linked."""
        # Track if budget_line_id or total_amount_currency is being changed
        budget_line_changed = 'budget_line_id' in vals
        amount_changed = 'total_amount_currency' in vals

        # Get old budget_line_id before write
        old_budget_line_ids = {}
        if budget_line_changed:
            for expense in self:
                old_budget_line_ids[expense.id] = expense.budget_line_id

        result = super().write(vals)

        # Update budget line actual_amount when expense is linked or amount changes
        if budget_line_changed or amount_changed:
            for expense in self:
                # If budget_line_id was set, update the budget line
                if expense.budget_line_id:
                    expense._update_budget_line_amount()

                # If budget_line_id was removed, clear the link on the old budget line
                old_budget_line = old_budget_line_ids.get(expense.id)
                if old_budget_line and old_budget_line != expense.budget_line_id:
                    if old_budget_line.expense_id == expense:
                        old_budget_line.sudo().with_context(
                            skip_expense_update=True
                        ).write({'expense_id': False})

        # NOTE: in Odoo 19, hr.expense.sheet no longer exists and approval lives
        # directly on hr.expense via approval_state, not a separate 'state' write.
        if vals.get('approval_state') == 'approved':
            self._validate_linked_bill()

        return result

    # === POSTING OVERRIDE (replaces the old hr.expense.sheet action_sheet_move_post) ===
    def action_post(self):
        """
        Override core action_post so that company-account expenses do NOT get an
        auto-generated payment/move from Odoo's standard _create_company_paid_moves().
        Instead, the real accounting record for these is the separately-linked vendor
        bill (matched via bill_reference and validated in _validate_linked_bill()).
        Employee-paid (own_account) expenses keep the standard Odoo 19 wizard flow.
        """
        company_expenses = self.filtered(lambda e: e.payment_mode == 'company_account')
        employee_expenses = self - company_expenses

        # Company-paid: skip Odoo's own move/payment creation entirely.
        # approval_state is already 'approved' (set via _do_approve), and the
        # linked vendor bill is validated separately — nothing else to do here.
        if company_expenses:
            company_expenses._validate_linked_bill()

        # Employee-paid: defer to standard Odoo 19 behavior (creates the wizard-driven
        # receipt/move as usual).
        if employee_expenses:
            return super(OmniHrExpense, employee_expenses).action_post()

        return True

    # === BILL VALIDATION ===
    def _validate_linked_bill(self):
        """Find and validate the bill linked to this expense via bill_reference."""
        for expense in self:
            if expense.payment_mode != 'company_account':
                continue

            if not expense.bill_reference:
                continue

            bill = self.env['account.move'].search([
                '|',
                ('ref', '=', expense.bill_reference),
                ('name', '=', expense.bill_reference),
                ('move_type', '=', 'in_invoice'),
                ('company_id', '=', expense.company_id.id),
            ], limit=1)

            if not bill:
                expense.message_post(body="⚠️ No bill found for reference: %s" % expense.bill_reference)
                continue

            if bill.status == 'awaiting_validation':
                bill._validate_from_expense_approval()
                expense.message_post(body="✅ Linked vendor bill %s has been validated." % (bill.ref or bill.name))
            else:
                expense.message_post(body="ℹ️ Bill %s status is %s — no update needed." % (bill.ref or bill.name, bill.status))

    def _update_budget_line_amount(self):
        """Update the linked budget line's actual_amount from expense amount."""
        self.ensure_one()
        if not self.budget_line_id:
            return

        # Update actual_amount from expense total_amount_currency
        # Use context flag to prevent circular updates from budget_line.write()
        # Always update, even if amount is 0 (to clear the amount if expense is set to 0)
        budget_line = self.budget_line_id.sudo().with_context(skip_expense_update=True)
        budget_line.write({
            'actual_amount': self.total_amount_currency or 0.0,
            'expense_id': self.id,
            'date_actual': self.date
        })

        # Explicitly trigger parent budget recomputation
        if budget_line.budget_id:
            budget_line.budget_id._compute_actual_costs()