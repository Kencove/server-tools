# Copyright 2025 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Archive Policy Model - Classification & Prioritization Logic

This model provides sophisticated rules for CLASSIFYING which records
to archive/keep and HOW to handle them.

Think of it as a "smart filter" that makes intelligent decisions:
- Keep latest N versions of a document
- Prefer certain file types over others
- Keep records based on business importance
- Handle duplicates intelligently

EXAMPLE USE CASES:
1. Sale Orders: "Keep last 3 invoices, archive older PDFs"
2. Mail Messages: "Keep unread, archive read messages > 1 year"
3. Attachments: "Keep max 2 versions per document type"
"""

import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class ArchivePolicy(models.Model):
    """Intelligent Classification & Prioritization Rules"""

    _name = "archive.policy"
    _description = "Archive Classification Policy"
    _order = "priority, name"

    # ============================================================================
    # FIELDS - Basic Configuration
    # ============================================================================

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(
        default=10,
        help="Lower = higher priority. When multiple policies match, highest priority wins.",
    )
    description = fields.Text(help="Describe what this policy does and when it applies")

    # ============================================================================
    # FIELDS - Policy Application Scope
    # ============================================================================

    model_ids = fields.Many2many(
        "ir.model",
        string="Applicable Models",
        help="Models to which this policy applies",
    )

    # TODO: Consider adding subtype filtering for mail.message
    # message_subtype_ids = fields.Many2many('mail.message.subtype')

    record_state_domain = fields.Text(
        string="Record State Filter",
        help="Python domain. E.g., [('state', 'in', ['done', 'cancel'])]",
    )

    # ============================================================================
    # FIELDS - Version Control (for attachments/documents)
    # ============================================================================

    max_file_versions = fields.Integer(
        default=0,
        help="Keep this many latest versions. 0 = unlimited\n"
        "Example: max_file_versions=2 keeps latest 2 invoices per SO",
    )

    version_strategy = fields.Selection(
        [
            ("newest", "Keep Newest N Versions"),
            ("oldest", "Keep Oldest N Versions"),
            ("largest", "Keep Largest Files"),
            ("smallest", "Keep Smallest Files"),
        ],
        default="newest",
        help="Which versions to keep when max_file_versions is exceeded",
    )

    # ============================================================================
    # FIELDS - File Type Preferences (for attachments)
    # ============================================================================

    preferred_mime_types = fields.Char(
        string="Preferred MIME Types",
        help="Comma-separated list. E.g., 'application/pdf,image/jpeg'\n"
        "When deduplicating, prefer these types",
    )

    archive_mime_types = fields.Char(
        string="Always Archive MIME Types",
        help="Comma-separated list of types to always archive (even if newer)",
    )

    # ============================================================================
    # FIELDS - Size & Age Thresholds
    # ============================================================================

    min_age_days = fields.Integer(
        default=0,
        help="Don't archive records newer than this (days). 0 = no minimum",
    )

    large_file_threshold_mb = fields.Float(
        default=0.0,
        help="Files larger than this are considered 'large'. 0 = no threshold\n"
        "Useful for: 'Archive large PDFs but keep small ones'",
    )

    large_file_action = fields.Selection(
        [
            ("archive", "Archive Large Files First"),
            ("keep", "Keep Large Files, Archive Small"),
            ("ignore", "Size Doesn't Matter"),
        ],
        default="archive",
    )

    # ============================================================================
    # FIELDS - Business Logic Filters
    # ============================================================================

    keep_if_referenced = fields.Boolean(
        default=True,
        help="Don't archive if record is referenced by active records\n"
        "Example: Don't archive attachments still linked to open sales orders",
    )

    archive_if_unused = fields.Boolean(
        default=False,
        help="Archive even recent records if they haven't been accessed",
    )

    unused_threshold_days = fields.Integer(
        default=90,
        help="Consider record 'unused' if not accessed for this many days",
    )

    # ============================================================================
    # FIELDS - Deduplication Configuration
    # ============================================================================

    enable_dedup_analysis = fields.Boolean(
        string="Enable Deduplication Analysis",
        default=False,
        help="Analyze for duplicates before applying policy",
    )

    dedup_strategy = fields.Selection(
        [
            ("checksum", "By Checksum (exact duplicates)"),
            ("name", "By Filename"),
            ("content_similarity", "By Content Similarity (slow)"),
        ],
        default="checksum",
        help="How to identify duplicates",
    )

    dedup_action = fields.Selection(
        [
            ("keep_newest", "Keep Newest, Archive Others"),
            ("keep_largest", "Keep Largest File"),
            ("keep_preferred_type", "Keep Preferred MIME Type"),
        ],
        default="keep_newest",
    )

    # ============================================================================
    # FIELDS - Statistics
    # ============================================================================

    applied_count = fields.Integer(
        readonly=True,
        help="Times this policy has been applied",
    )

    # ============================================================================
    # CONSTRAINTS
    # ============================================================================

    @api.constrains("max_file_versions")
    def _check_max_versions(self):
        for policy in self:
            if policy.max_file_versions < 0:
                raise exceptions.ValidationError(
                    _("Max file versions cannot be negative")
                )

    @api.constrains("record_state_domain")
    def _check_domain_syntax(self):
        """Validate domain is valid Python"""
        for policy in self.filtered(lambda p: p.record_state_domain):
            try:
                compile(policy.record_state_domain, "<string>", "eval")
            except SyntaxError as e:
                raise exceptions.ValidationError(
                    _("Invalid domain syntax: %s") % str(e)
                ) from e

    # ============================================================================
    # CORE POLICY METHODS
    # ============================================================================

    def _build_domain(self, model_name):
        """
        Build search domain incorporating this policy's rules

        PSEUDOCODE:
        domain = []

        # Model filter
        if self.model_ids and model_name not in self.model_ids.mapped('model'):
            return False  # Policy doesn't apply to this model

        # State filter
        if self.record_state_domain:
            domain = safe_eval(self.record_state_domain)

        # Age filter
        if self.min_age_days > 0:
            limit_date = today - self.min_age_days days
            domain.append(('create_date', '<', limit_date))

        # Reference filter
        if self.keep_if_referenced:
            # TODO: This is complex - need to check foreign keys
            # domain.append(('__referenced_by_active__', '=', False))
            pass

        return domain
        """
        # TODO: Implement domain construction
        return []

    def classify_records(self, records):
        """
        Classify recordset into: KEEP, ARCHIVE, DELETE

        Returns: dict with keys 'keep', 'archive', 'delete'
        Each value is a recordset

        PSEUDOCODE:
        keep_records = env[model].browse()
        archive_records = env[model].browse()
        delete_records = env[model].browse()

        FOR each record in records:
            # Apply version control logic
            IF self.max_file_versions > 0:
                versions = get_all_versions(record)
                IF len(versions) > max_file_versions:
                    keep_records |= select_versions_to_keep(versions)
                    archive_records |= remaining_versions

            # Apply size threshold logic
            IF self.large_file_threshold_mb > 0:
                IF record.file_size > threshold:
                    IF large_file_action == 'archive':
                        archive_records |= record
                    ELSE:
                        keep_records |= record

            # Apply age logic
            IF record.age < min_age_days:
                keep_records |= record

            # Apply reference logic
            IF keep_if_referenced AND record.has_active_references:
                keep_records |= record

        return {
            'keep': keep_records,
            'archive': archive_records,
            'delete': delete_records,
        }
        """
        self.ensure_one()

        # TODO: Implement classification logic
        return {
            "keep": records.browse(),
            "archive": records,
            "delete": records.browse(),
        }

    def analyze_duplicates(self, records):
        """
        Find duplicate records according to dedup_strategy

        Returns: list of tuples (master_record, duplicate_records)

        PSEUDOCODE:
        IF not self.enable_dedup_analysis:
            return []

        duplicates = []

        IF dedup_strategy == 'checksum':
            # Group by checksum field
            checksums = {}
            FOR record in records:
                IF hasattr(record, 'checksum'):
                    checksums.setdefault(record.checksum, []).append(record)

            FOR checksum, record_list in checksums.items():
                IF len(record_list) > 1:
                    master = select_master(record_list, dedup_action)
                    dupes = [r for r in record_list if r != master]
                    duplicates.append((master, dupes))

        ELIF dedup_strategy == 'name':
            # Similar logic but group by name/filename

        ELIF dedup_strategy == 'content_similarity':
            # TODO: This is advanced - use fuzzy matching
            # Might need external library or AI

        return duplicates
        """
        self.ensure_one()

        # TODO: Implement deduplication analysis
        _logger.info(
            "TODO: Implement duplicate analysis for policy %s with strategy %s",
            self.name,
            self.dedup_strategy,
        )
        return []

    def _select_master_record(self, records):
        """
        From a list of duplicates, select which one to keep

        PSEUDOCODE:
        IF dedup_action == 'keep_newest':
            return max(records, key=lambda r: r.create_date)

        ELIF dedup_action == 'keep_largest':
            return max(records, key=lambda r: r.file_size or 0)

        ELIF dedup_action == 'keep_preferred_type':
            preferred_types = parse_mime_types(self.preferred_mime_types)
            FOR mime_type in preferred_types:
                matches = records.filtered(lambda r: r.mimetype == mime_type)
                IF matches:
                    return matches[0]
            # Fallback to newest if no preferred type found
            return max(records, key=lambda r: r.create_date)
        """
        # TODO: Implement master selection logic
        return records[0] if records else False

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def _parse_mime_types(self, mime_string):
        """Convert comma-separated MIME types to list"""
        if not mime_string:
            return []
        return [mt.strip() for mt in mime_string.split(",") if mt.strip()]

    def _check_has_active_references(self, record):
        """
        Check if record is referenced by any active records

        PSEUDOCODE:
        # Find all foreign key fields pointing to this record
        referencing_fields = find_all_fk_fields(record._name)

        FOR field_info in referencing_fields:
            referencing_model = field_info['model']
            referencing_field = field_info['field']

            # Search for active records referencing this one
            domain = [
                (referencing_field, "=", record.id),
                "|",
                ("active", "=", True),
                ("active", "!=", False),  # Handle missing active field
            ]

            IF self.env[referencing_model].search_count(domain) > 0:
                return True

        return False
        """
        # TODO: Implement reference checking
        return False

    # ============================================================================
    # UI ACTIONS
    # ============================================================================

    def action_test_policy(self):
        """
        Test this policy on sample records

        UI Action: "Test Policy" button
        """
        self.ensure_one()

        # TODO: Find sample records
        # TODO: Run classify_records
        # TODO: Show results in wizard or report

        return {
            "type": "ir.actions.act_window",
            "name": _("Policy Test Results"),
            "res_model": "archive.policy.test.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_policy_id": self.id,
            },
        }
