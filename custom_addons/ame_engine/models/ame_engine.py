# -*- coding: utf-8 -*-
import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AmeEngine(models.TransientModel):
    _name = 'ame.engine'
    _description = 'AME Evaluation Engine'

    @api.model
    def evaluate_and_build_chain(self, instance):
        """Evaluate all rules for a document, resolve approvers, build approval chain.

        :param instance: ame.approval.instance record
        """
        record = self.env[instance.res_model].browse(instance.res_id)
        if not record.exists():
            raise UserError(_("Document not found."))

        tt = instance.transaction_type_id
        rules = tt.rule_ids.filtered(
            lambda r: r.active and r.evaluate(record)
        ).sorted(key=lambda r: (r.priority, r.sequence))

        if not rules:
            if tt.auto_approve_on_no_rules:
                _logger.info("AME: No rules fired for %s/%s — auto-approving",
                             instance.res_model, instance.res_id)
                return []
            raise UserError(_(
                "No approval rules matched for this document. "
                "Check the AME configuration for '%s'."
            ) % tt.name)

        # Resolve approvers for each fired rule and build approval lines
        line_vals = []
        seen_approvers_by_priority = {}

        for rule in rules:
            approvers = rule.approver_action_id.resolve_approvers(record)
            if not approvers:
                _logger.warning(
                    "AME: Rule '%s' fired but resolved no approvers", rule.name)
                continue

            priority = rule.priority
            if priority not in seen_approvers_by_priority:
                seen_approvers_by_priority[priority] = set()

            for approver in approvers:
                # Deduplicate: same user at same priority level
                if approver.id in seen_approvers_by_priority[priority]:
                    continue
                seen_approvers_by_priority[priority].add(approver.id)

                # Check for active substitution
                substitute = self.env['ame.substitution'].get_active_substitute(approver)
                actual_approver = substitute.substitute_id if substitute else approver

                line_vals.append({
                    'instance_id': instance.id,
                    'rule_id': rule.id,
                    'approver_action_id': rule.approver_action_id.id,
                    'approver_id': actual_approver.id,
                    'priority': priority,
                    'sequence': rule.sequence,
                    'state': 'pending',
                    'sla_hours': tt.escalation_hours,
                })

        if not line_vals:
            if tt.auto_approve_on_no_rules:
                return []
            raise UserError(_(
                "Rules fired but no approvers could be resolved. "
                "Check approver action configuration."))

        # Create all lines
        lines = self.env['ame.approval.line'].create(line_vals)

        # Log submission
        self.env['ame.approval.log'].sudo().create({
            'instance_id': instance.id,
            'action': 'submitted',
            'user_id': self.env.user.id,
            'comment': _("Submitted for approval. %d approver(s) in %d level(s).") % (
                len(lines), len(seen_approvers_by_priority)),
        })

        return lines
