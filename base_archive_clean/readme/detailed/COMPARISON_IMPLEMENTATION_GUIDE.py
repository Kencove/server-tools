#!/usr/bin/env python3
"""
Archive Comparison Framework - Implementation Guide

This file provides templates and examples for implementing comparison
strategies without modifying module code. All configuration is database-driven.

==============================================================================
EXAMPLE 1: Enable OpenAI Semantic Comparison
==============================================================================

Set these parameters via Settings > Technical > Parameters or programmatically:

archive.comparison_strategy = 'semantic'
archive.ai_provider = 'openai'
archive.openai_api_key = 'sk-your-api-key-here'
archive.openai_model = 'gpt-3.5-turbo'
archive.ai_cost_max_per_record = '0.01'

Then in your code:
    comparison = env['archive.comparison'].create({
        'archive_job_id': job.id,
        'original_record_id': record.id,
    })
    result = comparison.compare_before_after(
        record_before={'subject': 'Meeting', 'body': '...'},
        record_after={'subject': 'Meeting', 'body': '...'},
        strategy='semantic'
    )

Result includes:
    'identical': bool
    'similarity': float (0.0-1.0)
    'differences': [{field: 'subject', before: '...', after: '...'}]
    'cost_usd': 0.001
    'metadata': {api_provider: 'openai', model: 'gpt-3.5-turbo'}
"""

# ==============================================================================
# EXAMPLE 2: Custom Comparison Prompt (Database-Driven)
# ==============================================================================

#
# Instead of modifying code, store custom prompts in ir.config.parameter:
#
# env['ir.config.parameter'].set_param(
#     'archive.semantic_prompt_email',
#     json.dumps({
#         'system_prompt': '''You are comparing email messages for archiving.
#             Focus on: subject line, sender, body content.
#             Ignore: timestamps, formatting, whitespace.
#             Return: similarity score (0-1) and key differences.''',
#         'check_similarity': True,
#         'threshold': 0.85,
#         'cost_max': 0.01,
#         'model': 'gpt-3.5-turbo'
#     })
# )
#
# Then use it in your comparison:
#     prompt = env['ir.config.parameter'].get_param(
#         'archive.semantic_prompt_email'
#     )
#     result = comparison._openai_comparison(
#         record_before,
#         record_after,
#         prompt_config=json.loads(prompt)
#     )
#
# Benefits:
# - Change prompt without releasing new code
# - A/B test different prompts in production
# - Tune cost thresholds by record type
#

# ==============================================================================
# EXAMPLE 3: Server Action - Find and Merge Duplicates
# ==============================================================================

# Create this server action in the UI (Settings > Actions > Server Actions):

# Name: Archive - Find & Merge Similar Messages
# Model: mail.message
# Code:
# ------
# Find messages similar to current record
# comparison = env["archive.comparison"]

# Get current message
# current_msg = record

# Find all messages with >85% similarity
# similar = comparison.search(
#     [
#         ("original_record_id", "=", current_msg.id),
#         ("strategy_used", "=", "semantic"),
#         ("similarity_score", ">", 0.85),
#     ]
# )

# merged_count = 0
# for sim in similar:
#     other_msg = env["mail.message"].browse(sim.restored_record_id)
#     if other_msg.id != current_msg.id:
#         # Merge: append other content and mark as duplicate
#         current_msg.body += f"\\n\\n[Merged duplicate]\\n{other_msg.body}"
#         other_msg.active = False
#         merged_count += 1

# message = f"Merged {merged_count} similar messages"

# ------

# Now users can:
# 1. Go to a message
# 2. Click "Archive" > "Find Duplicates"
# 3. System finds similar messages and merges them
# 4. Zero code changes needed to adjust similarity threshold

# ==============================================================================
# EXAMPLE 4: Monitoring & Cost Control
# ==============================================================================

# Create reports without code changes:

# 1. Cost Dashboard (Add to base_archive_clean/views/):
#    <report id="report_archive_costs" model="archive.comparison" string="Comparison Costs">
#        <field name="cost_usd" sum="Sum"/>
#        <field name="strategy_used"/>
#        <field name="create_date"/>
#    </report>

# 2. SQL report - Top cost comparisons:
#    SELECT
#        strategy_used,
#        COUNT(*) as count,
#        SUM(cost_usd) as total_cost,
#        AVG(cost_usd) as avg_cost
#    FROM archive_comparison
#    WHERE create_date > NOW() - INTERVAL '30 days'
#    GROUP BY strategy_used
#    ORDER BY total_cost DESC;

# 3. Scheduled Action - Cost Alert:
#    Create ir.cron that runs daily and checks:
#    - Cost exceeds monthly budget?
#    - Shut down semantic comparisons and fall back to 'simple'
#    - Send admin notification

# ==============================================================================
# EXAMPLE 5: Custom SQL Comparison Strategy
# ==============================================================================

#
# For complex logic, use 'custom_sql' strategy in database:
#
# env['ir.config.parameter'].set_param(
#     'archive.custom_sql_duplicate_check',
#     '''
#     -- Find messages that are likely duplicates by cross-joining
#     SELECT
#         m1.id as msg1,
#         m2.id as msg2,
#         (
#             -- Similarity: count matching words / total words
#             SELECT COUNT(DISTINCT word)::float /
#                    (SELECT COUNT(DISTINCT word) FROM (
#                        SELECT unnest(string_to_array(
#                            LOWER(m1.body), ' '
#                        )) as word
#                    ) t)
#             FROM (
#                 SELECT unnest(string_to_array(
#                     LOWER(m2.body), ' '
#                 )) as word
#             ) t2
#         ) as similarity_score
#     FROM mail_message m1
#     JOIN mail_message m2 ON m1.id < m2.id
#     WHERE
#         m1.author_id = m2.author_id AND
#         m1.create_date > NOW() - INTERVAL '7 days' AND
#         m2.create_date > NOW() - INTERVAL '7 days'
#     HAVING similarity_score > 0.85;
#     '''
# )
#
# Then use it:
#     comparison._execute_custom_sql_strategy(
#         sql=env['ir.config.parameter'].get_param(
#             'archive.custom_sql_duplicate_check'
#         ),
#         rule=rule
#     )
#
# Benefits:
# - Complex multi-record logic without Python
# - Database engine optimization
# - No Python dependencies
#

# ==============================================================================
# EXAMPLE 6: Cost Control - Reject Expensive Comparisons
# ==============================================================================

#
# In your archive job:
#
# max_cost = float(
#     env['ir.config.parameter'].get_param(
#         'archive.ai_cost_max_per_record', '0.01'
#     )
# )
#
# if strategy == 'semantic':
#     cost_estimate = comparison._get_strategy(strategy).cost_estimate(
#         record_count=len(records_to_archive)
#     )
#
#     if cost_estimate['cost_usd'] > max_cost * len(records_to_archive):
#         # Too expensive - fall back to simple
#         _logger.warning(
#             'Semantic comparison cost exceeds limit. Falling back to simple.'
#         )
#         strategy = 'simple'
#     else:
#         # Safe to proceed
#         comparison.compare_before_after(
#             record_before, record_after, strategy
#         )
#

# ==============================================================================
# EXAMPLE 7: Ollama Local LLM (Free, No API Key)
# ==============================================================================

#
# If you have Ollama running locally (free, no API key needed):
#
# 1. Install Ollama: https://ollama.ai
# 2. Pull model: ollama pull llama2
# 3. Start server: ollama serve
#
# 4. Configure in Odoo:
#    archive.ai_provider = 'ollama'
#    archive.ollama_endpoint = 'http://localhost:11434'
#    archive.ollama_model = 'llama2'
#    archive.ai_cost_max_per_record = '0'  # Free!
#
# 5. Use in code - same API, zero cost:
#    result = comparison.compare_before_after(
#        record_before, record_after, strategy='semantic'
#    )
#    # Internally: _ollama_comparison() called instead of _openai_comparison()
#    # Cost: $0.00
#

# ==============================================================================
# EXAMPLE 8: Monitoring - Cost Per Model Type
# ==============================================================================

#
# Create a report showing costs by record type:
#
# from odoo import fields, models
#
# class ArchiveComparisonReport(models.Model):
#     _name = 'archive.comparison.report'
#     _auto = False
#
#     model_name = fields.Char()
#     strategy = fields.Char()
#     total_cost = fields.Float()
#     count = fields.Integer()
#     avg_cost = fields.Float()
#
#     def init(self):
#         tools.drop_view_if_exists(self._cr, self._table)
#         self._cr.execute('''
#             CREATE VIEW archive_comparison_report AS (
#                 SELECT
#                     row_number() OVER () as id,
#                     aj.model_name,
#                     ac.strategy_used as strategy,
#                     SUM(ac.cost_usd) as total_cost,
#                     COUNT(*) as count,
#                     AVG(ac.cost_usd) as avg_cost
#                 FROM archive_comparison ac
#                 JOIN archive_job aj ON ac.archive_job_id = aj.id
#                 WHERE ac.cost_usd > 0
#                 GROUP BY aj.model_name, ac.strategy_used
#             )
#         ''')
#
# # Users can now go to Reports > Archive > Comparison Costs
# # and see detailed breakdowns per model and strategy
#

# ==============================================================================
# KEY PRINCIPLES
# ==============================================================================

#
# 1. DATABASE-DRIVEN CONFIGURATION
#    ✓ Change settings via UI (Settings > Parameters)
#    ✓ No code changes needed
#    ✓ Can revert instantly
#
# 2. STRATEGY PLUGGABILITY
#    ✓ Simple: built-in, no dependencies
#    ✓ Semantic: OpenAI or Ollama (optional)
#    ✓ Custom SQL: database-specific logic
#
# 3. COST AWARENESS
#    ✓ Track all API costs automatically
#    ✓ Enforce per-record limits
#    ✓ Report costs by strategy/model type
#    ✓ Support free LLMs (Ollama)
#
# 4. NO CODE RELEASE NEEDED FOR:
#    ✓ Changing strategy (simple ↔ semantic ↔ custom_sql)
#    ✓ Tuning similarity thresholds
#    ✓ Customizing prompts
#    ✓ Setting cost limits
#    ✓ Creating deduplication workflows
#
# 5. EXTENSIBILITY
#    ✓ Add new strategies as installed modules
#    ✓ Override strategy loading in hooks
#    ✓ Create custom server actions in UI
#    ✓ Store complex logic in database (SQL, prompts)
#
