# Copyright 2025 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    """Extend mail.message to support archiving."""

    _inherit = "mail.message"

    # Archive state tracking
    archive_state = fields.Selection(
        selection=[
            ("active", "Active"),
            ("archived", "Archived"),
            ("restored", "Restored"),
        ],
        default="active",
        index=True,
        help="Track whether message has been archived to cloud storage.",
    )
    archive_backend_id = fields.Many2one(
        comodel_name="archive.backend",
        string="Archive Backend",
        readonly=True,
        help="Backend where message was archived.",
    )
    archive_reference = fields.Char(
        readonly=True,
        help="Reference ID in the archive backend (S3 key, Azure path, etc).",
    )
    archive_timestamp = fields.Datetime(
        string="Archived At",
        readonly=True,
        help="When message was archived.",
    )
    original_size = fields.Integer(
        string="Original Size (bytes)",
        readonly=True,
        help="Size of message before compression/archiving.",
    )
    compressed_size = fields.Integer(
        string="Compressed Size (bytes)",
        readonly=True,
        help="Size after compression (if applicable).",
    )
    is_system_message = fields.Boolean(
        string="System Message",
        compute="_compute_is_system_message",
        store=True,
        index=True,
        help="Auto-generated system message (not user-authored).",
    )
    is_comment = fields.Boolean(
        string="Comment Only",
        compute="_compute_is_comment",
        store=True,
        index=True,
        help="Message is a comment with no other content.",
    )
    thread_message_count = fields.Integer(
        string="Messages in Thread",
        compute="_compute_thread_message_count",
        help="Number of messages in this message's thread.",
    )
    archive_eligible = fields.Boolean(
        compute="_compute_archive_eligible",
        help="Can this message be archived?",
    )
    attachment_count = fields.Integer(
        compute="_compute_attachment_count",
        store=True,
    )

    @api.depends("subtype_id", "message_type")
    def _compute_is_system_message(self):
        """Detect system-generated messages."""
        for message in self:
            # System messages typically have no subtype or email_from is noreply
            is_system = (
                not message.subtype_id
                or message.subtype_id.name in ["System"]
                or (message.email_from and "noreply" in message.email_from)
                or message.message_type == "notification"
            )
            message.is_system_message = is_system

    @api.depends("body", "subtype_id")
    def _compute_is_comment(self):
        """Detect comment-only messages (no metadata, just text)."""
        for message in self:
            # Comment-only if it has body text, no subject, and no subtype
            is_comment = message.body and not message.subject and not message.subtype_id
            message.is_comment = is_comment

    @api.depends("message_id")
    def _compute_thread_message_count(self):
        """Count messages in the same thread."""
        for message in self:
            if message.message_id:
                # Find all messages with same message_id (thread)
                count = self.search_count([("message_id", "=", message.message_id)])
                message.thread_message_count = count
            else:
                message.thread_message_count = 1

    @api.depends("archive_state", "model", "archive_eligible")
    def _compute_archive_eligible(self):
        """Determine if message can be archived."""
        for message in self:
            # Can archive if:
            # - Not already archived
            # - Related to a model
            # - Not a draft
            eligible = (
                message.archive_state == "active"
                and message.model
                and message.state != "draft"
            )
            message.archive_eligible = eligible

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        """Count attachments."""
        for message in self:
            message.attachment_count = len(message.attachment_ids)

    def action_archive(self, backend=None, rule=None):
        """Archive this message to backend storage.

        Args:
            backend: archive.backend record to use (optional)
            rule: mail.message.archive.rule that triggered archiving (optional)

        Returns:
            dict with results: {'archived_count': int, 'failed_count': int}
        """
        results = {"archived_count": 0, "failed_count": 0}

        if not backend:
            # Use default backend from rule or system
            if rule and rule.archive_backend_id:
                backend = rule.archive_backend_id
            else:
                backend = self.env["archive.backend"].search(
                    [("is_default", "=", True)], limit=1
                )

        if not backend:
            _logger.warning("No archive backend configured for mail message archiving")
            return results

        for message in self.filtered(lambda m: m.archive_eligible):
            try:
                # Prepare message for archiving
                archive_data = message._prepare_archive_data()

                # Call backend to store
                archive_reference = backend.archive_record(
                    archive_data,
                    model="mail.message",
                    record_id=message.id,
                    rule_id=rule.id if rule else None,
                )

                # Update message with archive info
                message.write(
                    {
                        "archive_state": "archived",
                        "archive_backend_id": backend.id,
                        "archive_reference": archive_reference,
                        "archive_timestamp": datetime.now(),
                        "original_size": len(str(message.body).encode("utf-8")),
                    }
                )

                results["archived_count"] += 1
                _logger.info(f"Archived mail.message {message.id} to {backend.name}")

            except Exception as e:
                results["failed_count"] += 1
                _logger.error(f"Failed to archive mail.message {message.id}: {e}")
                # Continue with other messages

        return results

    def _prepare_archive_data(self):
        """Prepare message data for archiving.

        Returns:
            dict with all message data for archiving
        """
        self.ensure_one()

        return {
            "id": self.id,
            "message_id": self.message_id,
            "subject": self.subject,
            "body": self.body,
            "author_id": self.author_id.id if self.author_id else None,
            "author_name": self.author_id.name if self.author_id else None,
            "email_from": self.email_from,
            "create_date": self.create_date.isoformat() if self.create_date else None,
            "write_date": self.write_date.isoformat() if self.write_date else None,
            "model": self.model,
            "res_id": self.res_id,
            "message_type": self.message_type,
            "subtype": self.subtype_id.name if self.subtype_id else None,
            "attachment_count": len(self.attachment_ids),
            "attachment_names": [a.name for a in self.attachment_ids],
        }

    def action_restore(self):
        """Restore archived message from backend storage."""
        archived_messages = self.filtered(lambda m: m.archive_state == "archived")

        if not archived_messages:
            return

        results = {"restored_count": 0, "failed_count": 0}

        for message in archived_messages:
            try:
                if not message.archive_backend_id:
                    _logger.warning(
                        f"Cannot restore message {message.id}: no backend reference"
                    )
                    results["failed_count"] += 1
                    continue

                # Backend restores message (marks as active)
                message.archive_backend_id.restore_record(
                    message.archive_reference,
                    model="mail.message",
                    record_id=message.id,
                )

                # Mark as restored
                message.write(
                    {
                        "archive_state": "restored",
                    }
                )

                results["restored_count"] += 1
                _logger.info(f"Restored mail.message {message.id}")

            except Exception as e:
                results["failed_count"] += 1
                _logger.error(f"Failed to restore mail.message {message.id}: {e}")

        return results

    @api.model
    def _delete_old_archived_messages(self, days=90, limit=1000):
        """Permanently delete archived messages after retention period.

        Args:
            days: days after archiving to allow deletion (default 90)
            limit: max messages to delete per run (default 1000)
        """
        cutoff_date = fields.Datetime.to_datetime(datetime.now() - timedelta(days=days))

        to_delete = self.search(
            [
                ("archive_state", "=", "archived"),
                ("archive_timestamp", "<", cutoff_date),
            ],
            limit=limit,
        )

        deleted_count = len(to_delete)
        to_delete.unlink()

        _logger.info(
            f"Deleted {deleted_count} archived messages older than {days} days"
        )
        return deleted_count
