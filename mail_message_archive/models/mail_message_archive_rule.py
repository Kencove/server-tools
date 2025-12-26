# Copyright 2025 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MailMessageArchiveRule(models.Model):
    """Rules for archiving mail.message records."""

    _name = "mail.message.archive.rule"
    _description = "Mail Message Archive Rule"
    _inherit = ["archive.rule.mixin", "mail.thread"]

    # Specialized fields for mail archiving
    archive_empty_threads = fields.Boolean(
        default=True,
        help="If enabled, archive messages in threads with no remaining messages.",
    )
    min_messages_to_keep = fields.Integer(
        string="Minimum Messages to Keep",
        default=1,
        help="Keep at least this many recent messages per thread.",
    )
    archive_system_messages = fields.Boolean(
        default=True,
        help="Archive auto-generated system messages (status changes, assignments, etc.)",
    )
    archive_comment_only = fields.Boolean(
        string="Archive Comment-Only Messages",
        default=False,
        help="Archive messages that are just comments with no notification value.",
    )
    keep_attachment_references = fields.Boolean(
        default=True,
        help="Preserve attachment references even when archiving messages.",
    )
    archive_subtype_ids = fields.Many2many(
        comodel_name="mail.message.subtype",
        string="Archive Subtypes",
        help="Only archive messages of selected subtypes. Leave empty to archive all.",
    )
    exclude_subtype_ids = fields.Many2many(
        comodel_name="mail.message.subtype",
        string="Exclude Subtypes",
        relation="mail_message_archive_rule_exclude_subtype",
        help="Do NOT archive messages of these subtypes.",
    )
    model_ids = fields.Many2many(
        comodel_name="ir.model",
        string="Models to Archive From",
        help="Only archive messages related to these models. Leave empty for all models.",
    )

    @api.constrains("min_messages_to_keep")
    def _check_min_messages_to_keep(self):
        """Ensure minimum messages to keep is valid."""
        for rule in self:
            if rule.min_messages_to_keep < 0:
                raise UserError(_("Minimum messages to keep cannot be negative."))

    def _get_domain(self):
        """Build domain for messages to archive based on rule settings."""
        domain = super()._get_domain()
        domain += [("model", "!=", False)]  # Only archived messages related to models

        # Filter by model if specified
        if self.model_ids:
            domain += [("model", "in", self.model_ids.mapped("model"))]

        # Filter by subtype
        if self.archive_subtype_ids:
            domain += [("subtype_id", "in", self.archive_subtype_ids.ids)]
        elif self.exclude_subtype_ids:
            domain += [("subtype_id", "not in", self.exclude_subtype_ids.ids)]

        # Optionally exclude system messages
        if not self.archive_system_messages:
            domain += [("is_system_message", "=", False)]

        # Handle comment-only messages
        if not self.archive_comment_only:
            domain += [("is_comment", "=", False)]

        return domain

    def action_simulate_archive(self):
        """Simulate archiving without actually archiving."""
        self.ensure_one()
        domain = self._get_domain()
        messages = self.env["mail.message"].search(domain)

        return {
            "type": "ir.actions.act_window",
            "name": _("Messages to Archive (Simulation)"),
            "res_model": "mail.message",
            "view_mode": "tree,form",
            "domain": [("id", "in", messages.ids)],
            "context": {"create": False, "delete": False},
        }

    def action_dry_run(self):
        """Dry run of the archive process to estimate impact."""
        self.ensure_one()

        domain = self._get_domain()
        messages = self.env["mail.message"].search(domain)

        # Count messages by model
        message_by_model = {}
        for message in messages:
            model = message.model
            message_by_model[model] = message_by_model.get(model, 0) + 1

        # Count attachments that will be archived
        attachment_ids = messages.mapped("attachment_ids").ids
        total_attachment_size = sum(
            self.env["ir.attachment"].browse(attachment_ids).mapped("file_size")
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Archive Dry Run Report"),
            "res_model": "mail.message.archive.report",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_rule_id": self.id,
                "default_message_count": len(messages),
                "default_attachment_count": len(attachment_ids),
                "default_total_size": total_attachment_size,
                "default_message_by_model": str(message_by_model),
            },
        }
