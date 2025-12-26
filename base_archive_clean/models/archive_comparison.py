# Copyright 2025 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from abc import ABC, abstractmethod

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ArchiveComparisonStrategy(ABC):
    """Base class for record comparison strategies."""

    name = None  # Override in subclass: 'simple', 'semantic', 'sql', etc.

    @abstractmethod
    def compare(self, record_before, record_after, rule=None):
        """
        Compare two record states.

        Args:
            record_before: Original record (dict or recordset)
            record_after: Restored record (dict or recordset)
            rule: archive.rule for context/configuration

        Returns:
            {
                'identical': bool,
                'similarity': 0.0-1.0,
                'differences': [
                    {'field': 'name', 'before': 'x', 'after': 'y', 'changed': True}
                ],
                'ignored_fields': ['create_date', 'write_date', ...],
                'metadata': {}  # Strategy-specific data
            }
        """

    @abstractmethod
    def cost_estimate(self, record_count=1):
        """Estimate cost in $ or API calls."""


class SimpleComparison(ArchiveComparisonStrategy):
    """Basic field-by-field comparison."""

    name = "simple"

    def compare(self, record_before, record_after, rule=None):
        """Simple dict comparison."""
        if isinstance(record_before, dict):
            before = record_before
        else:
            before = record_before.read(fields=None)[0]

        if isinstance(record_after, dict):
            after = record_after
        else:
            after = record_after.read(fields=None)[0]

        # Fields to ignore in comparison
        ignored = {
            "id",
            "create_date",
            "create_uid",
            "write_date",
            "write_uid",
            "__last_update",
        }

        differences = []
        for field_name in set(list(before.keys()) + list(after.keys())):
            if field_name in ignored:
                continue

            before_val = before.get(field_name)
            after_val = after.get(field_name)

            if before_val != after_val:
                differences.append(
                    {
                        "field": field_name,
                        "before": before_val,
                        "after": after_val,
                        "changed": True,
                    }
                )

        identical = len(differences) == 0
        similarity = 1.0 if identical else 0.9  # Arbitrary heuristic

        return {
            "identical": identical,
            "similarity": similarity,
            "differences": differences,
            "ignored_fields": list(ignored),
            "metadata": {"strategy": "simple", "comparison_time_ms": 0},
        }

    def cost_estimate(self, record_count=1):
        """No cost for simple comparison."""
        return {"cost_usd": 0, "api_calls": 0}


class ArchiveComparison(models.Model):
    """Manages record comparison before/after archiving and restoration."""

    _name = "archive.comparison"
    _description = "Archive Comparison Result"
    _rec_name = "archive_job_id"

    # Reference
    archive_job_id = fields.Many2one("archive.job", required=True, ondelete="cascade")
    archive_rule_id = fields.Many2one(
        "archive.rule", related="archive_job_id.archive_rule_id"
    )
    model_name = fields.Char(related="archive_job_id.model_name")

    # Record IDs
    original_record_id = fields.Integer(help="ID of original record before archiving")
    restored_record_id = fields.Integer(help="ID of restored record (if restored)")

    # Comparison Data
    strategy_used = fields.Selection(
        selection=[
            ("simple", "Simple Field Comparison"),
            ("semantic", "Semantic Comparison (LLM)"),
            ("custom_sql", "Custom SQL Query"),
        ],
        default="simple",
        help="Strategy used for comparison",
    )
    is_identical = fields.Boolean(compute="_compute_identical", store=True)
    similarity_score = fields.Float(
        help="Similarity 0.0-1.0 (1.0 = identical)", store=True
    )

    # Detailed Results
    comparison_result = fields.Json(
        help="Full comparison output {identical, similarity, differences[], ...}"
    )

    # Metadata
    comparison_timestamp = fields.Datetime(auto_now_add=True)
    cost_usd = fields.Float(help="Cost in USD (if AI strategy used)")
    notes = fields.Text()

    @api.depends("comparison_result")
    def _compute_identical(self):
        for record in self:
            if record.comparison_result:
                record.is_identical = record.comparison_result.get("identical", False)
            else:
                record.is_identical = False

    def compare_before_after(self, record_before, record_after, strategy=None):
        """
        Execute comparison using specified strategy.

        Args:
            record_before: Original record state
            record_after: Restored record state (or current state)
            strategy: Strategy name ('simple', 'semantic', etc) or None for default

        Returns:
            Comparison result dict
        """
        if strategy is None:
            strategy = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("archive.comparison_strategy", "simple")
            )

        strategy_obj = self._get_strategy(strategy)
        result = strategy_obj.compare(record_before, record_after, self.archive_rule_id)

        # Store result and metadata
        self.comparison_result = result
        self.strategy_used = strategy
        self.similarity_score = result.get("similarity", 0.0)
        self.cost_usd = result.get("cost_usd", 0.0)

        return result

    def _get_strategy(self, strategy_name):
        """Load comparison strategy by name."""
        strategies = {"simple": SimpleComparison()}

        # Register additional strategies
        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("archive.ai_provider", "disabled")
            != "disabled"
        ):
            strategies["semantic"] = self._get_semantic_strategy()

        if strategy_name not in strategies:
            _logger.warning(
                "Comparison strategy '%s' not found, using 'simple'", strategy_name
            )
            strategy_name = "simple"

        return strategies[strategy_name]

    def _get_semantic_strategy(self):
        """Get LLM-based semantic comparison (pluggable)."""
        ai_provider = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("archive.ai_provider", "disabled")
        )

        if ai_provider == "openai":
            return self._openai_comparison()
        elif ai_provider == "ollama":
            return self._ollama_comparison()
        else:
            return SimpleComparison()  # Fallback

    def _openai_comparison(self):
        """Semantic comparison via OpenAI."""
        # Placeholder - would integrate with openai library
        _logger.info("OpenAI semantic comparison not yet implemented")
        return SimpleComparison()

    def _ollama_comparison(self):
        """Semantic comparison via local Ollama."""
        # Placeholder - would integrate with ollama locally
        _logger.info("Ollama semantic comparison not yet implemented")
        return SimpleComparison()
