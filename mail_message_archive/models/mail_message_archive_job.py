# Copyright 2025 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MailMessageArchiveJob(models.Model):
    """Job execution record for mail message archiving."""

    _name = "mail.message.archive.job"
    _description = "Mail Message Archive Job"
    _inherit = ["archive.job.mixin"]

    rule_id = fields.Many2one(
        comodel_name="mail.message.archive.rule",
        string="Archive Rule",
        required=True,
        ondelete="cascade",
    )
    backend_id = fields.Many2one(
        comodel_name="archive.backend",
        string="Archive Backend",
        required=True,
    )
    total_messages = fields.Integer(string="Total Messages to Archive")
    archived_count = fields.Integer(string="Messages Archived", default=0)
    failed_count = fields.Integer(default=0)
    skipped_count = fields.Integer(default=0)
    total_size_archived = fields.Integer(string="Total Size (bytes)", default=0)
    compression_ratio = fields.Float(
        help="Compressed size / Original size",
    )

    def action_execute(self):
        """Execute the archiving job."""
        self.ensure_one()

        if self.state != "draft":
            raise UserError(
                _("Only draft jobs can be executed. Current state: {}").format(
                    self.state
                )
            )

        try:
            self.write({"state": "running", "started_at": datetime.now()})

            # Get messages to archive
            domain = self.rule_id._get_domain()
            messages = self.env["mail.message"].search(domain)

            self.total_messages = len(messages)

            if not messages:
                _logger.info(f"No messages to archive for job {self.id}")
                self.write(
                    {
                        "state": "done",
                        "completed_at": datetime.now(),
                        "notes": "No messages matched archiving criteria.",
                    }
                )
                return

            # Archive in batches
            batch_size = 100
            for i in range(0, len(messages), batch_size):
                batch = messages[i : i + batch_size]
                self._archive_batch(batch)

            # Mark job as done
            self.write(
                {
                    "state": "done",
                    "completed_at": datetime.now(),
                }
            )

            _logger.info(
                f"Completed archive job {self.id}: "
                f"{self.archived_count} archived, {self.failed_count} failed"
            )

        except Exception as e:
            _logger.error(f"Archive job {self.id} failed: {e}")
            self.write(
                {
                    "state": "error",
                    "completed_at": datetime.now(),
                    "error_message": str(e),
                }
            )

    def _archive_batch(self, messages):
        """Archive a batch of messages."""
        for message in messages:
            try:
                # Prepare archive data
                archive_data = message._prepare_archive_data()

                # Archive to backend
                archive_reference = self.backend_id.archive_record(
                    archive_data,
                    model="mail.message",
                    record_id=message.id,
                    job_id=self.id,
                    rule_id=self.rule_id.id,
                )

                # Calculate sizes
                original_size = len(str(message.body).encode("utf-8"))
                compressed_size = original_size  # TODO: calculate actual compression

                # Update message
                message.write(
                    {
                        "archive_state": "archived",
                        "archive_backend_id": self.backend_id.id,
                        "archive_reference": archive_reference,
                        "archive_timestamp": datetime.now(),
                        "original_size": original_size,
                        "compressed_size": compressed_size,
                    }
                )

                # Update job stats
                self.archived_count += 1
                self.total_size_archived += original_size

            except Exception as e:
                self.failed_count += 1
                _logger.warning(f"Failed to archive message {message.id}: {e}")

    @api.model
    def _create_recurring_jobs(self):
        """Create recurring archive jobs based on rules with auto-archive enabled."""
        rules = self.env["mail.message.archive.rule"].search(
            [("is_active", "=", True), ("auto_archive", "=", True)]
        )

        for rule in rules:
            # Check if job already running for this rule
            existing = self.search(
                [
                    ("rule_id", "=", rule.id),
                    ("state", "in", ["draft", "running"]),
                ]
            )

            if existing:
                _logger.info(f"Job already exists for rule {rule.name}")
                continue

            # Create new job
            self.create(
                {
                    "rule_id": rule.id,
                    "backend_id": rule.archive_backend_id.id
                    or self.env["archive.backend"]
                    .search([("is_default", "=", True)], limit=1)
                    .id,
                    "name": f"Archive job for {rule.name}",
                }
            )

            _logger.info(f"Created archive job for rule {rule.name}")
