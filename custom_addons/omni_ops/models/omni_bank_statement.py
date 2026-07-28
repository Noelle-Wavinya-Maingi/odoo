from odoo import api, fields, models
import re


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'
    
    # Add a selection field to indicate match quality
    match_quality = fields.Selection(
        selection=[
            ('perfect', 'Perfect Match'),
            ('partial', 'Partial Match'),
        ], 
        string="Match Quality", 
        compute="_compute_match_quality", 
        store=True
    )
    
    def _is_special_banking_transaction(self, move_id):
        """
        Check if this is a special banking transaction based on the account description.
        These should be marked as PERFECT match even if not linked to an invoice/bill, 
        as they represent internal transfers, forex gains/losses or bank fees which 
        typically do not have invoices/bills.
        """
        if not move_id:
            return False
        
        account_names = []
        labels = []
        
        # Regex patterns to identify bank fees/charges
        bank_charge_patterns = [
            r'bank\s*charge',
            r'bank\s*fee',
            r'service\s*charge',
            r'maintenance\s*fee',
            r'monthly\s*fee',
            r'transaction\s*fee',
            r'wire\s*fee',
            r'transfer\s*fee',
            r'atm\s*fee',
            r'overdraft\s*fee',
            r'late\s*fee',
            r'interest\s*charge',
            r'processing\s*fee',
            r'foreign\s*transaction',
            r'international\s*fee',
        ]
        
        # Extract account names and labels from move lines for pattern matching
        for move_line in move_id.line_ids:
            if move_line.account_id.name:
                account_names.append(move_line.account_id.name.lower())
            if move_line.name:
                labels.append(move_line.name.lower())
            if move_line.ref:
                labels.append(move_line.ref.lower())
        
        # Check for keywords in account names that indicate internal transfers, forex gains/losses or bank fees
        for name in account_names:
            if 'money movement' in name or 'internal transfer' in name or 'fund transfer' in name:
                return True
            if 'capital gain' in name or 'forex' in name or 'exchange' in name:
                return True
            
            for pattern in bank_charge_patterns:
                if re.search(pattern, name):
                    return True
        
        # Check transaction labels against bank charge patterns
        for label in labels:
            if label:
                for pattern in bank_charge_patterns:
                    if re.search(pattern, label):
                        return True
        
        return False
    
    def _is_tolerance_account(self, account_code):
        """Check if the account code indicates a tolerance account for small discrepancies."""
        
        tolerance_accounts = ['655000', '755000']
        return account_code in tolerance_accounts
                    
    def _has_invoice_link(self, move_id):
        """
        Check if transaction is linked to an invoice/bill by following the partial reconciliation chain.
        Returns:
        - has_any_invoice: bool, True if any line is linked to invoice
        - all_lines_have_invoice: bool, True ONLY if all lines are linked to invoices
        - has_tolerance_account: bool, True if any line uses tolerance accounts
        """
        if not move_id:
            return {'has_any_invoice': False, 'all_lines_have_invoice': False, 'has_tolerance_account': False}
        
        has_any_invoice = False
        all_lines_have_invoice = True
        has_tolerance_account = False

        # Bank account types to skip
        bank_account_types = ['liquidity', 'asset_cash']
    
        # Loop through each journal item of the transaction
        for move_line in move_id.line_ids:
            # Skip the bank account line (usually the main statement line)
            if move_line.account_id.account_type in bank_account_types:
                continue
                
            if self._is_tolerance_account(move_line.account_id.code):
                has_tolerance_account = True
                continue

            line_has_invoice = False
            partial_recs = move_line.matched_debit_ids + move_line.matched_credit_ids
            
            # Check each partial reconciliation to find the linked document
            for rec in partial_recs:
                opposite_line = rec.debit_move_id if rec.debit_move_id != move_line else rec.credit_move_id
                
                if opposite_line and opposite_line.move_id:
                    move_type = opposite_line.move_id.move_type
                    
                    # Check if the opposite line is an actual invoice/bill document
                    if move_type in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund'):
                        line_has_invoice = True
                        has_any_invoice = True
                        break
            
            if not line_has_invoice:
                all_lines_have_invoice = False
        
        return {
            'has_any_invoice': has_any_invoice,
            'all_lines_have_invoice': all_lines_have_invoice,
            'has_tolerance_account': has_tolerance_account
        }
          
    @api.depends('is_reconciled', 'move_id', 'amount_residual')
    def _compute_match_quality(self):
        """
        Compute match quality for each bank statement line.
        If the line is not reconciled, match_quality is False.
        If reconciled, determine if it's a perfect match (either special banking transaction or has bill/invoice) or partial match
        """
        for line in self:
            # Transaction is not reconciled
            if not line.is_reconciled:
                line.match_quality = False
                continue
        
            is_special = False
            has_invoice = False
            has_tolerance = False
            all_invoices = False
            
            # Only check if there's a journal entry linked to this statement line
            if line.move_id:
                is_special = self._is_special_banking_transaction(line.move_id)
                
                # Get detailed invoice link info
                invoice_info = self._has_invoice_link(line.move_id)
                has_tolerance = invoice_info['has_tolerance_account']
                has_invoice = invoice_info['has_any_invoice']
                all_invoices = invoice_info['all_lines_have_invoice']
                
            # Determine match quality based on flags and residual amount
            if is_special and line.amount_residual == 0:
                line.match_quality = 'perfect'
            # Special banking transaction with amount mismatch (rare)
            elif is_special and line.amount_residual != 0:
                line.match_quality = 'partial'
            # Invoice/bill payment with exact amount
            elif all_invoices and line.amount_residual == 0:
                line.match_quality = 'perfect'
            # Partial payment on an invoice/bill
            elif has_invoice and not all_invoices and not has_tolerance:
                line.match_quality = 'partial'
            
            # Has invoices but partial payment
            elif has_invoice and line.amount_residual != 0:
                if has_tolerance:
                    line.match_quality = 'perfect'
                else:
                    line.match_quality = 'partial'
            
            # Uses tolerance account without invoice
            elif has_tolerance:
                line.match_quality = 'perfect'
            
            # Direct account match with no invoice/bill or not special transaction or tolerance accounts
            else:
                line.match_quality = 'partial'
             
                    
    def write(self, vals):
        """
        Override write method to force recomputation of match_quality when reconciliation happens.
        When a statement line is reconciled or unreconciled, the is_reconciled or move_id fields change.
        This triggers our compute method to update the match_quality accordingly.
        """
        result = super().write(vals)
        
        # If reconciliation status changed, recompute match_quality for all affected lines
        if 'is_reconciled' in vals or 'move_id' in vals:
            self._compute_match_quality()
            
            for line in self:
                if line.match_quality:
                    super(AccountBankStatementLine, line).write({'match_quality': line.match_quality})
        
        return result