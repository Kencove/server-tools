# Archive Comparison Framework

This document explains the comparison strategy architecture, how to extend it, and how to use it for validation, deduplication, and cost control.

## Overview

The `archive.comparison` model provides extensible comparison strategies for validating that records are identical before/after archiving or restoration. Instead of hard-coding comparison logic, strategies are:

- **Pluggable**: Register new strategies without releasing module code
- **Configuration-driven**: Switch strategies via `ir.config.parameter`
- **Cost-aware**: Each strategy reports API cost (for AI-based approaches)
- **AI-friendly**: OpenAI, Ollama, and custom LLM integration ready

## Built-in Strategies

### 1. Simple (Default)

```python
strategy_used = "simple"
```

Field-by-field comparison. Ignores system fields (create_date, write_date, etc).

**Cost**: $0
**Use when**: Validating data integrity, field-level accuracy

**Example**:
```python
comparison = self.env['archive.comparison'].create({
    'archive_job_id': job.id,
})
result = comparison.compare_before_after(original_record, restored_record)
```

### 2. Semantic (LLM-based, Optional)

```python
strategy_used = "semantic"
```

Uses OpenAI or Ollama to understand "meaning" of changes. Detects cases like:
- User changed formatting only (minor difference)
- Semantic duplication (different fields, same meaning)
- Content summarization matches

**Cost**: ~$0.001-0.01 per record (OpenAI), free (Ollama)
**Use when**: Handling text-heavy records, detecting meaningful duplicates

**Configuration**:
```
ir.config_parameter:
  archive.ai_provider = 'openai' | 'ollama' | 'disabled'
  archive.openai_api_key = 'sk-...'
  archive.ollama_endpoint = 'http://localhost:11434'
```

### 3. Custom SQL (Enterprise)

```python
strategy_used = "custom_sql"
```

Define comparison as raw SQL for complex logic (e.g., comparing related records, computed fields).

**Cost**: $0
**Use when**: Complex multi-record validation, custom domain rules

## Creating Custom Strategies

### Option 1: Python Class (Installed Module)

```python
# my_archive_strategy/__init__.py
from .comparison_strategy import MyCustomStrategy

# my_archive_strategy/comparison_strategy.py
from archive_comparison import ArchiveComparisonStrategy

class MyCustomStrategy(ArchiveComparisonStrategy):
    name = "my_custom"

    def compare(self, record_before, record_after, rule=None):
        # Your logic here
        return {
            'identical': True,
            'similarity': 1.0,
            'differences': [],
            'ignored_fields': [...],
            'metadata': {'custom_field': 'value'}
        }

    def cost_estimate(self, record_count=1):
        return {'cost_usd': 0, 'api_calls': 0}

# Register in hook
def _register_my_strategy():
    Strategy = MyCustomStrategy()
    # Global registry or env-based registration
```

### Option 2: Configuration-Driven (No Code Release)

Define comparison logic without changing module code:

```python
# data/archive_comparison_config.xml
<odoo>
  <data>
    <!-- Store custom comparison prompts/strategies in database -->
    <record id="semantic_email_dedup" model="ir.config.parameter">
      <field name="key">archive.comparison_prompt_email_dedup</field>
      <field name="value">{
        "system_prompt": "You are comparing email messages...",
        "check_similarity": true,
        "threshold": 0.85,
        "cost_max": 0.01
      }</field>
    </record>
  </data>
</odoo>
```

Then in your server action or Python code:
```python
custom_prompt = self.env['ir.config.parameter'].get_param(
    'archive.comparison_prompt_email_dedup'
)
# Use custom_prompt in LLM call
```

## Integration Points

### 1. Before Archiving (Validation)

Ensure archiving won't lose data:

```python
# In archive.job.execute()
def _execute_batch(self):
    for record_id in batch.record_ids:
        record = self.env[self.model_name].browse(record_id)

        # Capture state before archiving
        before_state = record.read(fields=None)[0]

        # Archive record
        self._archive_record(record)

        # Store state for later comparison
        comparison = self.env['archive.comparison'].create({
            'archive_job_id': self.id,
            'original_record_id': record_id,
            'comparison_result': {
                'before': before_state,
                'archive_location': batch.location_uri,
                'backup_checksum': batch.checksum,
            }
        })
```

### 2. On Restoration (Validation)

Verify restored record matches original:

```python
# In archive.batch.restore()
def _restore_record(self, record_id):
    restored = self._deserialize_and_restore(record_id)
    original_state = self.comparison_id.comparison_result.get('before')

    comparison = self.env['archive.comparison'].create({
        'archive_job_id': self.archive_job_id,
        'original_record_id': record_id,
        'restored_record_id': restored.id,
    })

    result = comparison.compare_before_after(
        original_state,
        restored,
        strategy='simple'  # or from config
    )

    if not result['identical']:
        _logger.warning(
            "Restored record differs: %s",
            result['differences']
        )
        return {
            'status': 'restored_with_warnings',
            'differences': result['differences']
        }

    return {'status': 'restored_identical'}
```

### 3. Deduplication (Cost Control)

Find and merge duplicates before archiving:

```python
# Server action or scheduled action
action_dedup = self.env['ir.actions.server'].create({
    'name': 'Archive: Detect Message Duplicates',
    'model_id': self.env['ir.model'].search([
        ('model', '=', 'mail.message')
    ]).id,
    'code': '''
# Find messages with semantic similarity > 0.95
comparison = self.env['archive.comparison']
duplicates = comparison.search([
    ('strategy_used', '=', 'semantic'),
    ('similarity_score', '>', 0.95),
])

for dup in duplicates:
    _logger.info(
        f"Merge {dup.original_record_id} <- {dup.restored_record_id}"
    )
    # Merge logic here
''',
    'state': 'code'
})
```

## Configuration Parameters

Add to `base_archive_clean/data/archive_config.xml`:

```xml
<record id="param_comparison_strategy" model="ir.config.parameter">
  <field name="key">archive.comparison_strategy</field>
  <field name="value">simple</field>
  <!-- Options: simple, semantic, custom_sql -->
</record>

<record id="param_ai_provider" model="ir.config.parameter">
  <field name="key">archive.ai_provider</field>
  <field name="value">disabled</field>
  <!-- Options: disabled, openai, ollama -->
</record>

<record id="param_ai_cost_max" model="ir.config.parameter">
  <field name="key">archive.ai_cost_max_per_record</field>
  <field name="value">0.01</field>
  <!-- Max $0.01 per comparison -->
</record>

<record id="param_ai_threshold" model="ir.config.parameter">
  <field name="key">archive.ai_similarity_threshold</field>
  <field name="value">0.85</field>
  <!-- 0.85 = consider records >85% similar as duplicates -->
</record>
```

## Cost Control

Strategies report costs automatically:

```python
strategy = comparison._get_strategy('semantic')
cost = strategy.cost_estimate(record_count=1000)
# Returns: {'cost_usd': 10.00, 'api_calls': 1000}
```

In your archiving job, check cost before proceeding:

```python
def _execute_batch(self):
    if self.strategy_used == 'semantic':
        cost = self._estimate_comparison_cost()
        max_cost = float(
            self.env['ir.config.parameter'].get_param(
                'archive.max_comparison_cost_per_run', '100.00'
            )
        )

        if cost > max_cost:
            raise ValidationError(
                f"Estimated cost ${cost:.2f} exceeds limit ${max_cost:.2f}"
            )
```

## UI/UX Considerations

### Archive Dashboard
- Show comparison statistics: "89% identical after restoration"
- Cost summary: "$12.34 spent on semantic comparisons this month"
- Action buttons: "View Differences", "Merge Duplicates"

### Archive Rule Form
- Strategy dropdown (simple, semantic, custom_sql)
- Cost estimate when AI selected
- Test button: "Run sample comparison on 10 records"

### Server Actions
Allow users to create custom comparison workflows without code:

```
Server Actions:
├── Validate Restored Messages
│   └── Compare original vs restored (simple)
├── Find Duplicate Emails
│   └── Compare semantic similarity (OpenAI)
└── Clean Up Before Archive
    └── Merge similar records (custom SQL)
```

## Migration Path

1. **Phase 1** (Current): Simple strategy, no AI
2. **Phase 2**: Add ir.config.parameter for strategy selection
3. **Phase 3**: Add OpenAI integration (optional dependency)
4. **Phase 4**: Add custom SQL strategy
5. **Phase 5**: Ollama local LLM support

No breaking changes. Each phase is backward compatible and optional.
