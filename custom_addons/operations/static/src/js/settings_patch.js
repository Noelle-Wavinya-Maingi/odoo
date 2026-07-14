/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    /**
     * Override save to call execute for res.config.settings.
     * This makes the native save button behave like Apply
     */
    async save(params = {}) {
        if (this.props.resModel === "res.config.settings") {
            return await this._applySettings();
        }
        return await super.save(...arguments);
    },
    
    /**
     * Apply the current settings.
     */
    async _applySettings() {
        try {
            const saved = await this.model.root.save({stayInEdition: true});

            if (!saved) return false;

            const resId = this.model.root.resId;

            if (!resId) {
                console.error("No resId after save - cannot apply settings");
                return false;
            }

            await this.env.services.orm.call(
                "res.config.settings",
                "execute",
                [[resId]]
            );

            this.env.services.action.doAction({type: "ir.actions.act_window_close"});
            window.location.reload();
            return true;
        } catch (e) {
            console.error("Settings apply failed:", e);
            return false;
        }
    },

    async discard() {
        if (this.props.resModel === "res.config.settings") {
            this.env.services.action.doAction({type: "ir.actions.act_window_close"});
            return;
        }
        return await super.discard(...arguments);
    }
});