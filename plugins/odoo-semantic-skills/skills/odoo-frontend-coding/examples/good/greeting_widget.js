/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/**
 * Reference "good" OWL 2.x component (Odoo v16-v18). Passes verify-frontend.sh:
 * - the ui service is wrapped in useState (class-2 reactivity preserved, v16-18 canonical)
 * - handlers are auto-bound (t-on-click="onIncrement") or explicit-this arrows
 * - no raw contenteditable, no hardcoded palette
 */
export class GreetingWidget extends Component {
    static template = "my_module.GreetingWidget";

    setup() {
        this.ui = useState(useService("ui"));
        this.state = useState({ count: 0 });
    }

    onIncrement() {
        this.state.count = this.state.count + 1;
    }

    // class-3 precision check: a `contenteditable` CSS *selector* string in JS is
    // legitimate (it is NOT a raw contenteditable template attribute) and must NOT
    // block — class-3 only applies to .xml/.html templates with a quoted attribute.
    findEditable() {
        return this.el.querySelector("[contenteditable=true]");
    }
}

registry.category("public_components").add("my_module.GreetingWidget", GreetingWidget);
