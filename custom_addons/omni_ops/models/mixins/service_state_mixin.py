# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ServiceStateMixin(models.AbstractModel):
    """Mixin for service state management (start, done, cancel actions).
    
    Supports both custom service_state field and standard Odoo state field.
    Models can use standard Odoo state by implementing _use_standard_state().
    """
    _name = 'service.state.mixin'
    _description = 'Service State Management Mixin'

    # Expected fields in models using this mixin:
    # - state: Standard Odoo state field with states (pending, progress, done, cancel)
    # - date_start: Datetime field [optional, for tracking when operation started]
    # - date_finished: Datetime field [optional, for tracking when operation completed]
    # - is_end_date_manual: Boolean field [optional, for tracking manual end dates]
    # - actual_duration: Float field [optional, for duration tracking]

    # === UTILITY METHODS ===
    def _use_standard_state(self):
        """Check if this model uses standard Odoo state field instead of service_state.
        
        By default, all models use standard Odoo state field.
        Override this method in models to return False if using custom service_state field.
        """
        return True

    def _get_current_state(self):
        """Get current state from standard state field."""
        return getattr(self, 'state', False)

    def _get_service_operation_name(self):
        """Get the name to display in service operation messages.
        
        Override this method in models using the mixin to customize the name shown in messages.
        """
        # Default to 'name' field, fallback to id
        return getattr(self, 'name', None) or getattr(self, 'operation_title', None) or str(self.id)

    def _get_message_target(self):
        """Get the record to post messages to.
        
        Override this method in models using the mixin to customize where messages are posted.
        Returns the record itself by default.
        """
        return self

    def _can_start(self):
        """Check if operation can be started."""
        current_state = self._get_current_state()
        # All models now use standard state field
        return current_state not in ('done', 'cancel', 'progress')

    def _can_complete(self):
        """Check if operation can be completed."""
        current_state = self._get_current_state()
        # All models now use standard state field
        return current_state == 'progress'

    def _can_cancel(self):
        """Check if operation can be cancelled."""
        current_state = self._get_current_state()
        # All models now use standard state field
        return current_state == 'done'

    # === STATE MANAGEMENT METHODS ===
    def _do_service_start(self):
        """Start the service operation using standard Odoo state field."""
        for record in self:
            if not record._can_start():
                raise ValidationError(_("Cannot start an operation that is already done, cancelled, or in progress."))
            
            # Use standard Odoo button_start if available (for workorders)
            if hasattr(record, 'button_start'):
                try:
                    record.button_start(raise_on_invalid_state=True)
                except Exception:
                    # Fallback: directly set state
                    record.with_context(bypass_duration_calculation=True).write({
                        'state': 'progress',
                        'date_start': fields.Datetime.now()
                    })
            else:
                # Direct write for non-workorder models
                vals = {'state': 'progress'}
                if hasattr(record, 'date_start') and not record.date_start:
                    vals['date_start'] = fields.Datetime.now()
                record.write(vals)
            
            # Post message
            target = record._get_message_target()
            operation_name = record._get_service_operation_name()
            target.message_post(
                body=_("Service operation '%s' started by %s") % (operation_name, self.env.user.name),
                subtype_xmlid='mail.mt_note'
            )

    def _do_service_done(self):
        """Mark the service operation as done using standard Odoo state field."""
        for record in self:
            if not record._can_complete():
                continue  # Skip if already done/cancelled
            
            # Use standard Odoo button_finish if available (for workorders)
            if hasattr(record, 'button_finish'):
                try:
                    record.button_finish()
                except Exception:
                    # Fallback: directly set state
                    record.with_context(bypass_duration_calculation=True).write({
                        'state': 'done',
                        'date_finished': fields.Datetime.now()
                    })
            else:
                # Direct write for non-workorder models
                vals = {'state': 'done'}
                if hasattr(record, 'is_end_date_manual') and hasattr(record, 'date_finished'):
                    if not record.is_end_date_manual and not record.date_finished:
                        vals['date_finished'] = fields.Datetime.now()
                record.write(vals)
            
            # Post message with duration if available
            target = record._get_message_target()
            operation_name = record._get_service_operation_name()
            
            if hasattr(record, 'actual_duration') and record.actual_duration > 0:
                hours = int(record.actual_duration // 60)
                minutes = int(record.actual_duration % 60)
                duration_str = _("%d hours %d minutes") % (hours, minutes) if hours > 0 else _("%d minutes") % minutes
                target.message_post(
                    body=_("Service operation '%s' completed by %s. Actual duration: %s") % (operation_name, self.env.user.name, duration_str),
                    subtype_xmlid='mail.mt_note'
                )
            else:
                target.message_post(
                    body=_("Service operation '%s' completed by %s") % (operation_name, self.env.user.name),
                    subtype_xmlid='mail.mt_note'
                )

    def _do_service_cancel(self):
        """Cancel the service operation using standard Odoo state field."""
        for record in self:
            if not record._can_cancel():
                raise ValidationError(_("Only completed service operations can be cancelled."))
            
            vals = {'state': 'cancel'}
            if hasattr(record, 'is_end_date_manual') and hasattr(record, 'date_finished'):
                if not record.is_end_date_manual and not record.date_finished:
                    vals['date_finished'] = fields.Datetime.now()
            record.with_context(bypass_duration_calculation=True).write(vals)
            
            # Post message
            target = record._get_message_target()
            operation_name = record._get_service_operation_name()
            target.message_post(
                body=_("Service operation '%s' cancelled by %s") % (operation_name, self.env.user.name),
                subtype_xmlid='mail.mt_note'
            )

    # === ACTION METHODS ===
    def action_service_start(self):
        """Start service operation action."""
        self._do_service_start()
        return True

    def action_service_done(self):
        """Complete service operation action."""
        self._do_service_done()
        return True

    def action_service_cancel(self):
        """Cancel service operation action."""
        self._do_service_cancel()
        return True

    def action_cycle_service_state(self):
        """
        Single button that acts depending on current state:
          pending/ready/waiting -> start (progress)
          progress -> done (done)
          done -> cancel (cancel)
        """
        for record in self:
            current_state = record._get_current_state()
            
            if current_state in ('pending', 'ready', 'waiting'):
                record._do_service_start()
            elif current_state == 'progress':
                record._do_service_done()
            elif current_state == 'done':
                record._do_service_cancel()
        return True

