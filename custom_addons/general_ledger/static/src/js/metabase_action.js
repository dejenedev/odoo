/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, xml, onWillStart, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

class MetabaseDashboard extends Component {
    static template = xml`
        <div class="o_action" style="height: 100%; width: 100%;">
            <iframe
                t-if="state.url"
                t-att-src="state.url"
                style="width: 100%; height: 100%; border: none;"
                allowfullscreen="true"
            />
            <div t-else="" class="d-flex align-items-center justify-content-center h-100">
                <div class="text-center text-muted">
                    <h3>BI Dashboard not configured</h3>
                    <p>Go to Accounting &gt; Configuration &gt; Settings &gt; BI Dashboard (Metabase) to set the Metabase URL and Dashboard UUID.</p>
                </div>
            </div>
        </div>
    `;
    static props = ["*"];

    setup() {
        this.state = useState({ url: "" });
        onWillStart(async () => {
            this.state.url = await rpc("/general_ledger/metabase_url", {});
        });
    }
}

registry.category("actions").add("metabase_dashboard", MetabaseDashboard);
