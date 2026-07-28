# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class OperationsBudgetLine(models.Model):
    """Shared budget line, reused across industries.

    This model carries no anchor field of its own (no production_id, no trade_id) to
    avoid a circular module dependency: each industry module adds its own anchor via
    `_inherit` (e.g. omni_ops adds `budget_id` -> omni.mrp.budget, trading adds
    `trade_id` -> trading.trade) and overrides the hook methods below to plug its
    anchor into the generic create/write/expense-management flow implemented here.

    Section/note support (display_type) follows the exact same convention as
    sale.order.line / purchase.order.line / account.move.line: a line with
    display_type set is a pure organizational/annotation row with no real
    amount, expense, or invoice/bill behind it. The web list renderer recognizes
    a field literally named `display_type` with these two values and renders
    that row full-width automatically -- no extra view plumbing needed beyond
    adding the field and the "Add a section"/"Add a note" controls.
    """
    _name = 'operations.budget.line'
    _description = 'Budget Line'
    _order = 'sequence, id'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # === BASIC FIELDS ===
    name = fields.Char('Description', required=True, tracking=True)
    sequence = fields.Integer('Sequence', default=10)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    # === DISPLAY TYPE (section/note rows) ===
    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note'),
    ], string='Display Type', default=False, help=(
        'Technical field for UI purposes only. A Section row is a pure organizational '
        'header (e.g. "Transport", "Documentation", "Out-of-pocket") with no amount, '
        'vendor, or expense of its own -- every real transaction still lives in its own '
        'ordinary line underneath it. A Note row is free text with no amount either.'
    ))

    # === LINE TYPE ===
    line_type = fields.Selection([
        ('expense', 'Cost'),
        ('charge', 'Revenue'),
        ('other', 'Other / Credit'),
    ], string='Line Type', default='expense')

    # === AMOUNTS ===
    budgeted_amount = fields.Float(
        'Budgeted Amount',
        default=0.0,
        digits=(16, 2),
        tracking=True,
        help='Planned amount for this budget line'
    )
    actual_amount = fields.Float(
        'Actual Amount',
        default=0.0,
        digits=(16, 2),
        tracking=True,
        help='Actual cost/revenue incurred'
    )
    variance_amount = fields.Float(
        'Variance',
        compute='_compute_variance',
        store=True,
        digits=(16, 2),
        help='Difference between actual and budgeted amounts'
    )
    amount_company_currency = fields.Float(
        'Amount in Company Currency',
        compute='_compute_amount_company_currency',
        store=True,
        digits=(16, 2)
    )

    # === VENDOR/CUSTOMER ===
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor/Customer',
        tracking=True,
        help='Supplier or customer for this budget line'
    )

    # === REFERENCES ===
    product_id = fields.Many2one('product.product', string='Product/Service', tracking=True)
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        help='Optional account for future accounting integration'
    )

    # === DETAILS ===
    description = fields.Text('Detailed Description')

    # === DATES ===
    date_planned = fields.Date('Planned Date')
    date_actual = fields.Date('Actual Date')

    # === STATUS ===
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
    ], string='Status', default='draft', tracking=True)

    # === EXPENSE INTEGRATION ===
    expense_id = fields.Many2one(
        'hr.expense',
        string='Expense',
        tracking=True,
        help='Expense record linked to this budget line. Can be created automatically or linked manually.',
        ondelete='set null'
    )
    expense_is_submitted = fields.Boolean(
        'Expense Submitted',
        compute='_compute_expense_is_submitted',
        store=False,
        help='True if the linked expense has been submitted'
    )

    # === ALREADY-COVERED-BY-A-DOCUMENT INTEGRATION ===
    account_move_id = fields.Many2one(
        'account.move',
        string='Invoice/Bill',
        tracking=True,
        domain=[('state', '=', 'posted')],
        ondelete='set null',
        help='If this line\'s actual amount is already represented by a posted invoice/bill '
             '(e.g. one already linked to the parent record), link it here instead of entering '
             'the amount manually. When set, no expense is auto-created for this line and the '
             'line does not separately contribute to any cost/revenue ledger — the '
             'invoice/bill\'s own posting is what counts.'
    )
    
    source_reference = fields.Reference(
        selection=[('account.move', 'Invoice/Bill'), ('hr.expense', 'Expense')],
        string="Source",
        compute='_compute_source_reference',
    )
    
    @api.depends('account_move_id', 'expense_id')
    def _compute_source_reference(self):
        for line in self:
            if line.account_move_id:
                line.source_reference = f'account.move, {line.account_move_id.id}'
            elif line.expense_id:
                line.source_reference = f'hr.expense, {line.expense_id.id}'
            else:
                line.source_reference = False

    # === HOOKS FOR INDUSTRY-SPECIFIC MODULES TO OVERRIDE ===
    def _get_anchor_record(self):
        """Return the parent business record this line belongs to (e.g. a trade or a
        production order), used for validation and chatter. Empty recordset by default."""
        return self.env['operations.budget.line']

    def _get_anchor_expense_vals(self):
        """Return extra vals (e.g. {'trade_id': ...}) to merge into a newly created
        hr.expense. Empty dict means "no anchor to attach" (create will be blocked)."""
        return {}

    def _get_display_name_prefix(self):
        """Human-readable prefix (e.g. a trade or file number) used to format the
        auto-generated expense name as "{prefix} / {line name}"."""
        return ''

    def _notify_anchor_of_amount_change(self):
        """Called whenever an amount/line_type/account_move_id changes, so an industry
        module can recompute its own aggregates (e.g. a budget header's totals, or a
        trade's additional_costs/additional_revenue ledger). No-op by default."""
        return

    def _get_conversion_company(self):
        """Company to use for currency conversion / expense company_id. Override to
        point at the anchor's own company if it differs from the current user's."""
        return self.env.company

    def _get_target_currency(self):
        """Currency to convert amount_company_currency into. Defaults to this line's
        own currency (i.e. no conversion) since the core model doesn't know the
        anchor's reporting currency."""
        return self.currency_id

    # === COMPUTED FIELDS ===
    @api.depends('expense_id', 'expense_id.state')
    def _compute_expense_is_submitted(self):
        """Compute whether the linked expense is submitted/approved/done.

        Odoo 19 removed hr.expense.sheet entirely — expenses are approved
        individually now (auto-validated if the employee has no manager set),
        so this only needs the expense's own state, not a separate sheet.
        """
        for line in self:
            line.expense_is_submitted = bool(line.expense_id) and line.expense_id.state in ('submitted', 'approved', 'done')

    @api.depends('budgeted_amount', 'actual_amount')
    def _compute_variance(self):
        """Compute variance between budgeted and actual amounts.

        Deliberately side-effect-free (no anchor notification here): writing to other
        records from inside a compute method is fragile in Odoo (recompute/flush
        ordering). create()/write() below call _notify_anchor_of_amount_change()
        explicitly and safely instead, covering every case this would have."""
        for line in self:
            line.variance_amount = line.actual_amount - line.budgeted_amount

    @api.depends('actual_amount', 'budgeted_amount', 'currency_id')
    def _compute_amount_company_currency(self):
        """Convert amounts to the industry's target currency for aggregation."""
        for line in self:
            company = line._get_conversion_company()
            target_currency = line._get_target_currency()
            amount = line.actual_amount or line.budgeted_amount or 0.0

            if line.currency_id and target_currency and line.currency_id != target_currency:
                line.amount_company_currency = line.currency_id._convert(
                    amount, target_currency, company, fields.Date.today()
                )
            else:
                line.amount_company_currency = amount

    # === ONCHANGE ===
    @api.onchange('actual_amount', 'budgeted_amount')
    def _onchange_amounts(self):
        """Force live recomputation on the anchor while editing in the UI."""
        self._notify_anchor_of_amount_change()

    @api.onchange('account_move_id')
    def _onchange_account_move_id(self):
        """Convenience prefill only — the linked move is the actual source of truth,
        this just saves a manual re-entry when nothing has been entered yet."""
        if self.account_move_id and not self.actual_amount:
            self.actual_amount = abs(self.account_move_id.amount_total)
            self.date_actual = self.account_move_id.invoice_date or self.account_move_id.date

    @api.onchange('display_type')
    def _onchange_display_type(self):
        """When a line becomes a Section/Note, clear every field that wouldn't make
        sense on it -- mirrors sale.order.line's _onchange_display_type. When it's
        turned back into a normal line, line_type needs a real default again."""
        if self.display_type:
            self.update({
                'line_type': False,
                'budgeted_amount': 0.0,
                'actual_amount': 0.0,
                'partner_id': False,
                'product_id': False,
                'account_id': False,
                'date_planned': False,
                'date_actual': False,
                'expense_id': False,
                'account_move_id': False,
            })
        elif not self.line_type:
            self.line_type = 'expense'

    # === CONSTRAINTS ===
    @api.constrains('budgeted_amount', 'actual_amount')
    def _check_positive_amounts(self):
        """Ensure amounts are positive. Section/note rows are always 0.0 and skipped."""
        for line in self:
            if line.display_type:
                continue
            if line.budgeted_amount < 0:
                raise ValidationError(_("Budgeted amount cannot be negative for line '%s'.") % line.name)
            if line.actual_amount < 0:
                raise ValidationError(_("Actual amount cannot be negative for line '%s'.") % line.name)

    @api.constrains('display_type', 'line_type')
    def _check_line_type_required(self):
        """A real (non-section/note) line must have a line_type; a section/note must not."""
        for line in self:
            if not line.display_type and not line.line_type:
                raise ValidationError(_("Line '%s' must have a Line Type (Cost/Revenue/Other).") % (line.name or ''))
            if line.display_type and line.line_type:
                raise ValidationError(_("A Section/Note line cannot have a Line Type."))

    @api.constrains('display_type', 'account_move_id', 'expense_id')
    def _check_no_document_on_section(self):
        """A section/note can never be linked to a real invoice/bill or expense."""
        for line in self:
            if line.display_type and (line.account_move_id or line.expense_id):
                raise ValidationError(_("A Section/Note line cannot be linked to an Invoice/Bill or Expense."))

    # === METHODS ===
    def action_confirm(self):
        """Confirm the budget line."""
        for line in self:
            line.write({'state': 'confirmed'})

    def action_done(self):
        """Mark the budget line as done."""
        for line in self:
            line.write({'state': 'done'})

    def _should_create_expense(self):
        """Only cost-side lines with no already-linked invoice/bill auto-create an
        expense. Revenue ('charge') lines never do — an expense represents outflow.
        Section/note rows never do either — they carry no real amount."""
        self.ensure_one()
        return (
            not self.display_type and
            self.line_type in ('expense', 'other') and
            not self.account_move_id and
            self.actual_amount and self.actual_amount > 0 and
            not self.expense_id
        )

    def _should_unlink_expense(self):
        """An expense should be dropped if the line no longer has a positive actual
        amount, or is now covered by a linked invoice/bill instead."""
        self.ensure_one()
        return bool(self.expense_id) and (
            self.account_move_id or not self.actual_amount or self.actual_amount <= 0
        )

    def _create_expense_from_budget_line(self):
        """Create or update the hr.expense record backing this budget line."""
        self.ensure_one()

        if not self._should_create_expense() and not self.expense_id:
            return False
        if not self.actual_amount or self.actual_amount <= 0:
            return False

        employee = self.env.user.employee_id
        if not employee:
            raise ValidationError(_(
                "Cannot create expense: User '%s' has no associated employee record. "
                "Please create an employee record for this user."
            ) % self.env.user.name)

        anchor_vals = self._get_anchor_expense_vals()
        if not anchor_vals:
            raise ValidationError(_(
                "Cannot create expense: Budget line '%s' is not linked to a parent record."
            ) % self.name)

        expense_name = self.name or _('Expense from Budget Line')
        prefix = self._get_display_name_prefix()
        formatted_name = f"{prefix} / {expense_name}" if prefix else expense_name

        expense_vals = {
            'name': formatted_name,
            'employee_id': employee.id,
            'product_id': self.product_id.id if self.product_id else False,
            'total_amount_currency': self.actual_amount,
            'currency_id': self.currency_id.id,
            'date': self.date_actual or fields.Date.today(),
            'company_id': self._get_conversion_company().id,
            'payment_mode': 'company_account',
            'budget_line_id': self.id,
            'description': self.description or '',
            **anchor_vals,
        }
        if self.partner_id:
            expense_vals['vendor_id'] = self.partner_id.id

        if self.expense_id:
            self.expense_id.write(expense_vals)
            return self.expense_id
        return self.env['hr.expense'].create(expense_vals)

    def _create_expense_for_line(self):
        """Create expense for this line, handling errors gracefully."""
        self.ensure_one()
        try:
            expense = self._create_expense_from_budget_line()
            if expense:
                self.sudo().write({'expense_id': expense.id})
        except ValidationError:
            raise
        except Exception as e:
            _logger.warning("Failed to create expense for budget line %s: %s", self.id, str(e))

    def _unlink_expense_for_line(self):
        """Unlink (and remove) the expense currently backing this line."""
        self.ensure_one()
        expense_to_unlink = self.expense_id
        self.sudo().write({'expense_id': False})
        if expense_to_unlink.budget_line_id == self:
            expense_to_unlink.write({'budget_line_id': False})
        expense_to_unlink.unlink()

    def _handle_actual_amount_or_source_change(self):
        """Create, update, or unlink expenses based on the current state of the line."""
        if self._context.get('skip_expense_update'):
            return
        for line in self:
            if line.display_type:
                continue
            if line._should_create_expense():
                line._create_expense_for_line()
            elif line._should_unlink_expense():
                line._unlink_expense_for_line()

    def _get_initial_tracking_values(self, vals):
        """Get initial field values before write for tracking purposes."""
        initial_values = {}
        tracked_fields = self._fields
        for line in self:
            initial_values[line.id] = {}
            for field_name in vals.keys():
                if field_name in tracked_fields and getattr(tracked_fields[field_name], 'tracking', False):
                    initial_values[line.id][field_name] = line[field_name]
        return initial_values

    def _post_tracking_messages(self, vals, initial_values):
        """Post tracking messages to the anchor record for tracked field changes."""
        if self._context.get('mail_notrack'):
            return

        tracked_fields = self._fields
        for line in self:
            anchor = line._get_anchor_record()
            if not anchor:
                continue

            changes = {}
            for field_name in vals.keys():
                if field_name not in tracked_fields:
                    continue
                field_info = tracked_fields[field_name]
                if not getattr(field_info, 'tracking', False):
                    continue

                old_value = initial_values.get(line.id, {}).get(field_name)
                new_value = line[field_name]
                if old_value != new_value:
                    field_string = field_info.string or field_name
                    old_display = line._format_tracking_value(field_name, old_value, field_info)
                    new_display = line._format_tracking_value(field_name, new_value, field_info)
                    changes[field_string] = (old_display, new_display)

            if changes:
                body_parts = [f"{field}: {old_val} → {new_val}" for field, (old_val, new_val) in changes.items()]
                body = f"Budget line '{line.name}' updated: {', '.join(body_parts)}"
                anchor.message_post(
                    body=body,
                    subtype_xmlid='mail.mt_note',
                    author_id=self.env.user.partner_id.id
                )

    def _format_tracking_value(self, field_name, value, field_info):
        """Format a field value for display in tracking messages."""
        if value is False or value is None:
            return _('(empty)')

        field_type = field_info.type
        if field_type == 'many2one':
            return value.name if value else _('(empty)')
        elif field_type in ('many2many', 'one2many'):
            return ', '.join(value.mapped('name')) if value else _('(empty)')
        elif field_type == 'selection':
            return dict(field_info.selection).get(value, value) if field_info.selection else str(value)
        elif field_type == 'boolean':
            return _('Yes') if value else _('No')
        elif field_type in ('float', 'monetary'):
            if hasattr(field_info, 'get_digits'):
                digits = field_info.get_digits(self.env) or (16, 2)
            else:
                digits = getattr(field_info, '_digits', None) or (16, 2)
            return f"{value:,.{digits[1]}f}"
        else:
            return str(value)

    # === CRUD ===
    @api.model_create_multi
    def create(self, vals_list):
        """Create lines, auto-manage expenses for any that already carry a positive
        actual amount, and notify each anchor (some anchors, like a trade's additive
        ledger, have nothing that recomputes automatically on record creation).
        Section/note rows skip all of this — they have nothing to sync."""
        lines = super().create(vals_list)
        for line in lines:
            if line.display_type:
                continue
            if line._should_create_expense():
                line._create_expense_for_line()
            line._notify_anchor_of_amount_change()
        return lines

    def write(self, vals):
        """Track field changes, sync expenses, and notify the anchor of amount/source
        changes."""
        initial_values = self._get_initial_tracking_values(vals)
        result = super().write(vals)

        self._post_tracking_messages(vals, initial_values)

        if 'expense_id' in vals:
            for line in self:
                if line.expense_id and not line._context.get('skip_expense_update'):
                    expense_vals = {'budget_line_id': line.id}
                    line.expense_id.write(expense_vals)
                    if not line.actual_amount and line.expense_id.total_amount_currency:
                        line.actual_amount = line.expense_id.total_amount_currency

        if any(f in vals for f in ('actual_amount', 'line_type', 'account_move_id')):
            self._handle_actual_amount_or_source_change()

        if any(f in vals for f in ('actual_amount', 'budgeted_amount', 'line_type', 'account_move_id')):
            for line in self:
                if line.display_type:
                    continue
                line._notify_anchor_of_amount_change()

        return result