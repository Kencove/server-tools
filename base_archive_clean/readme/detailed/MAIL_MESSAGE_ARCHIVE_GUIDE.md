# Mail Message Archive - Implementation Guide

## Overview

The `mail_message_archive` module demonstrates how to extend the `base_archive_clean` framework for a specific use case: archiving old mail.message records (chatter/activity streams) to reduce database bloat.

This module can handle mail messages from ANY related model:
- Sale Orders
- Partners
- Invoices
- Products
- Bills of Materials
- Purchase Orders
- Helpdesk Tickets (with helpdesk_archive extension)
- CRM Leads/Opportunities (with crm_archive extension)

## Architecture

```
base_archive_clean (core framework)
    ├── archive.rule.mixin
    ├── archive.backend (S3, Azure, etc)
    ├── archive.job.mixin
    └── archive.policy

mail_message_archive (specific implementation)
    ├── mail.message.archive.rule
    ├── mail.message (extended with archive fields)
    ├── mail.message.archive.job
    └── mail.message.archive.report
```

## Key Components

### 1. Archive Rules (mail.message.archive.rule)

Defines WHAT to archive:

```python
rule = env["mail.message.archive.rule"].create({
    "name": "Archive old chatter",
    "is_active": True,
    "auto_archive": True,
    "archive_backend_id": backend.id,

    # Time-based (inherited from base)
    "older_than_days": 365,  # Only messages > 1 year old

    # Mail-specific settings
    "archive_system_messages": True,
    "archive_comment_only": False,
    "min_messages_to_keep": 1,  # Keep at least 1 per thread

    # Selective archiving
    "model_ids": [(6, 0, [sale_model_id, partner_model_id])],  # Only these models
    "archive_subtype_ids": [(6, 0, [comment_subtype_id])],  # Only comments
})
```

### 2. Archive Jobs (mail.message.archive.job)

Executes the archiving:

```python
# Jobs are created automatically by cron or manually
job = env["mail.message.archive.job"].create({
    "rule_id": rule.id,
    "backend_id": backend.id,
    "name": "Archive old chatter - 2025-01-15",
})

# Execute
job.action_execute()

# Check results
print(f"Archived: {job.archived_count}")
print(f"Failed: {job.failed_count}")
print(f"Total size: {job.total_size_archived} bytes")
```

### 3. Message Archive State

Each mail.message now tracks its archive status:

```python
# Check state
for message in env["mail.message"].search([("archive_state", "=", "archived")]):
    print(f"Message {message.id} archived in {message.archive_backend_id.name}")
    print(f"Reference: {message.archive_reference}")
    print(f"Archived at: {message.archive_timestamp}")
    print(f"Original size: {message.original_size} bytes")
```

## Usage Patterns

### Pattern 1: Archive by Time + Model

Archive messages older than 1 year related to sales orders only:

```python
rule = env["mail.message.archive.rule"].create({
    "name": "Archive old sales chatter",
    "older_than_days": 365,
    "model_ids": [(6, 0, [env.ref("sale.model_sale_order").id])],
    "archive_backend_id": env.ref("archive_clean.backend_s3").id,
    "is_active": True,
    "auto_archive": True,
})
```

### Pattern 2: Archive System Messages Only

Archive only system-generated messages to save space:

```python
rule = env["mail.message.archive.rule"].create({
    "name": "Archive system messages",
    "older_than_days": 30,
    "archive_system_messages": True,
    "archive_comment_only": False,
    "is_active": True,
})
```

### Pattern 3: Smart Thread Cleanup

Archive messages but keep recent ones from each thread:

```python
rule = env["mail.message.archive.rule"].create({
    "name": "Smart thread cleanup",
    "older_than_days": 90,
    "min_messages_to_keep": 2,  # Keep 2 most recent per thread
    "archive_empty_threads": True,
    "is_active": True,
})
```

### Pattern 4: Selective Subtype Archiving

Only archive messages of certain types:

```python
# Get subtypes
comment_subtype = env.ref("mail.mt_comment")
activity_subtype = env.ref("mail.mt_note")

rule = env["mail.message.archive.rule"].create({
    "name": "Archive comments and notes",
    "archive_subtype_ids": [(6, 0, [comment_subtype.id, activity_subtype.id])],
    "exclude_subtype_ids": [(6, 0, [env.ref("mail.mt_email").id])],
    "older_than_days": 180,
    "is_active": True,
})
```

## Dry-Run & Preview

Before archiving, always dry-run to see impact:

```python
# Dry-run (estimates impact)
results = rule.action_dry_run()

# Simulate (shows actual records)
action = rule.action_simulate_archive()
# Opens tree view with records that WILL be archived
```

## Monitoring & Reporting

### Check Job Status

```python
jobs = env["mail.message.archive.job"].search([("state", "=", "running")])
for job in jobs:
    progress = job.archived_count / job.total_messages * 100
    print(f"{job.name}: {progress:.1f}% complete")
```

### Archive Statistics

```python
# Count archived messages per model
archived_by_model = {}
for message in env["mail.message"].search([("archive_state", "=", "archived")]):
    model = message.model
    archived_by_model[model] = archived_by_model.get(model, 0) + 1

print("Archived messages by model:")
for model, count in archived_by_model.items():
    print(f"  {model}: {count}")
```

### Storage Savings

```python
total_original = sum(
    env["mail.message"]
    .search([("archive_state", "=", "archived")])
    .mapped("original_size")
)
total_compressed = sum(
    env["mail.message"]
    .search([("archive_state", "=", "archived")])
    .mapped("compressed_size")
)

savings = (total_original - total_compressed) / total_original * 100
print(f"Storage savings: {savings:.1f}%")
print(f"Original: {total_original / 1024 / 1024:.1f} MB")
print(f"Compressed: {total_compressed / 1024 / 1024:.1f} MB")
```

## Restoration

### Restore Specific Messages

```python
# Restore by date range
messages_to_restore = env["mail.message"].search([
    ("archive_state", "=", "archived"),
    ("archive_timestamp", ">=", "2024-01-01"),
    ("model", "=", "sale.order"),
])

messages_to_restore.action_restore()
```

### Restore with Verification

```python
results = messages_to_restore.action_restore_with_verification()
print(f"Restored: {results['restored']}")
print(f"Verified: {results['verified']}")
print(f"Failed: {results['failed']}")
```

## Scheduled Archiving

The module includes a cron job that automatically runs archiving:

```xml
<!-- Runs daily at 2 AM -->
<record id="mail_archive_cron_daily" model="ir.cron">
    <field name="name">Archive old mail messages</field>
    <field name="model_id" ref="mail_message_archive.model_mail_message_archive_job"/>
    <field name="state">code</field>
    <field name="code">model._create_recurring_jobs()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
    <field name="numbercall">-1</field>
    <field name="doall">True</field>
</record>
```

To disable automatic archiving:
```python
env["ir.cron"].search([("name", "=", "Archive old mail messages")]).active = False
```

## Configuration Best Practices

### 1. Start Small

Don't archive everything at once:

```python
# First: Archive only very old messages (2+ years)
rule1 = create_rule(older_than_days=730)

# After verification: Archive 1+ year old
rule2 = create_rule(older_than_days=365)

# Finally: Archive 6 month+ old
rule3 = create_rule(older_than_days=180)
```

### 2. Archive by Model

Separate rules per model for better control:

```python
for model in ["sale.order", "account.move", "crm.lead"]:
    env["mail.message.archive.rule"].create({
        "name": f"Archive {model} messages",
        "model_ids": [(6, 0, [env.ref(f"model_{model}").id])],
        "older_than_days": 365,
        "is_active": True,
    })
```

### 3. Regular Cleanup

Permanently delete very old archived messages:

```python
# Keep archived for 90 days, then delete
env["mail.message"]._delete_old_archived_messages(days=90)
```

## Troubleshooting

### Job Stuck

```python
# Check lock status
job = env["mail.message.archive.job"].browse(job_id)
if job.is_locked:
    # Force unlock if stuck
    job.action_force_unlock()
```

### Restore Not Working

```python
# Check backend connectivity
backend = env["archive.backend"].browse(backend_id)
if not backend.verify_connectivity():
    print("Backend not accessible!")
```

### Partial Failures

```python
# Resume from checkpoint
job = env["mail.message.archive.job"].browse(job_id)
job.action_resume()  # Continues from last checkpoint
```

## Performance Tuning

### Adjust Batch Size

```python
# Default is 100, adjust based on message size
rule.batch_size = 500  # Larger batches = faster but more memory
```

### Adjust Checkpoint Frequency

```python
# Default is 100, more frequent = better recovery but slower
rule.checkpoint_count = 50  # Checkpoint every 50 records
```

### Parallel Jobs

```python
config = env["archive.config"].get_singleton()
config.max_job_workers = 4  # Run up to 4 jobs in parallel
```

## Security Considerations

1. **Access Control**: Only archive managers can modify rules
2. **Audit Trail**: All archive actions are logged
3. **Encryption**: Use encrypted backends for sensitive data
4. **Retention**: Auto-delete archived after configured period
5. **Verification**: Restore with integrity checking

## Integration with Other Modules

### With CRM Archive

```python
# Archive both mail messages and CRM-specific data
env["mail.message.archive.rule"].create({
    "name": "Archive old CRM data",
    "model_ids": [(6, 0, [
        env.ref("crm.model_crm_lead").id,
        env.ref("crm.model_crm_phonecall").id,
    ])],
    "older_than_days": 180,
})

env["crm.phonecall.archive.rule"].create({
    "name": "Archive old calls",
    "older_than_days": 365,
})
```

### With Helpdesk Archive

```python
# Archive old helpdesk tickets and their messages
env["mail.message.archive.rule"].create({
    "name": "Archive old helpdesk chatter",
    "model_ids": [(6, 0, [env.ref("helpdesk.model_helpdesk_ticket").id])],
    "older_than_days": 90,
})

env["helpdesk.ticket.archive.rule"].create({
    "name": "Archive old tickets",
    "older_than_days": 365,
})
```

## Conclusion

The mail_message_archive module provides a production-ready solution for managing large message volumes across the entire Odoo system, with the ability to extend to model-specific archiving (CRM, Helpdesk) as needed.

The base_archive_clean framework handles the heavy lifting (backends, jobs, policies) while mail_message_archive provides domain-specific intelligence (thread management, system messages, deduplication).
