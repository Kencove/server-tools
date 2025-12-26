# Archive Clean for Odoo - Quick Start Guide

## What is Archive Clean?

Archive Clean is a comprehensive system for archiving old data in Odoo to cloud storage while maintaining query performance and compliance. It's designed to solve the database bloat problem that happens in large Odoo instances.

## The Problem It Solves

```
Your Odoo instance over 3 years:
- Database grows from 50 GB → 500 GB
- Queries slow from 100ms → 2 seconds
- Backups take 30 min → 6 hours
- Storage costs $100/mo → $500/mo
```

**Root cause**: Old data (mail messages, CRM records, etc.) accumulates but is rarely accessed.

**Solution**: Move old data to cloud storage, keep only what's active in PostgreSQL.

## 5-Minute Setup

### Step 1: Install the Module

```bash
# Install base framework
odoo-bin install base_archive_clean

# Install mail message archiving
odoo-bin install mail_message_archive
```

### Step 2: Configure Backend

Go to **Archive Clean → Backends**:

```
Backend Name: AWS Production
Provider: Amazon S3
AWS Access Key ID: ****
AWS Secret Access Key: ****
S3 Bucket: company-archives
S3 Region: us-east-1
Encryption: AES-256
```

### Step 3: Create Archiving Rule

Go to **Archive Clean → Archiving Rules**:

```
Rule Name: Old Sales Chatter
Models: Sale Order
Older Than: 365 days
Backend: AWS Production
Auto-archive: Yes
```

### Step 4: Test with Dry-Run

Click **"Simulate Archive"** button:
```
Expected to archive: 15,234 messages
Total size: 2.3 GB
Time estimate: 2 hours
```

Click **"Dry-Run"** button to preview sample records.

### Step 5: Enable Automatic Archiving

Check **"Auto-archive"** and click **Save**:
- Archive job runs daily at 2 AM
- Processes in batches of 100
- Auto-resumes if job fails

## Key Features

### 1. Selective Archiving
Archive based on:
- **Time**: Older than X days
- **Size**: Larger than X MB
- **Model**: Only specific models
- **Content**: System messages, comments, etc.
- **Custom**: Any domain filter

### 2. Safe by Default
- **Dry-run**: Preview before archiving
- **Restore**: Always restore from cloud
- **Verification**: Checksums ensure integrity
- **Audit trail**: Track all operations
- **Locking**: Prevent concurrent archives

### 3. Cloud-Native
Supported backends:
- ✅ AWS S3
- ✅ Microsoft Azure
- ✅ Google Cloud Storage
- ✅ Local filesystem (for testing)

### 4. Monitor Progress
```
Archive Job Status:
├── Total: 50,000 messages
├── Archived: 35,000 (70%)
├── Failed: 2 (with details)
├── In Progress: 5,000
└── Est. Time Remaining: 45 min
```

## Common Use Cases

### Use Case 1: Clean Up Old Chatter

**Problem**: 5 years of mail messages = 200 GB

**Solution**:
```python
rule = env["mail.message.archive.rule"].create({
    "name": "Archive old chatter",
    "older_than_days": 730,  # 2 years
    "archive_empty_threads": True,
    "min_messages_to_keep": 2,  # Keep last 2 per thread
    "archive_system_messages": True,
})
```

**Result**: Database shrinks 50 GB → 10 GB

### Use Case 2: Archive System-Generated Messages

**Problem**: Notifications clutter message history

**Solution**:
```python
rule = env["mail.message.archive.rule"].create({
    "name": "Archive system messages",
    "older_than_days": 30,
    "archive_system_messages": True,
    "archive_comment_only": False,
})
```

**Result**: Only user comments remain, system notifications archived

### Use Case 3: Model-Specific Archiving

**Problem**: Old sale orders have too much history

**Solution**:
```python
rule = env["mail.message.archive.rule"].create({
    "name": "Archive old sale order chatter",
    "older_than_days": 365,
    "model_ids": [env.ref("sale.model_sale_order").id],
})
```

**Result**: Only recent sales chatter visible

## Administration

### Check Archive Status

```python
# See all active archiving jobs
jobs = env["mail.message.archive.job"].search([
    ("state", "=", "running")
])

for job in jobs:
    print(f"{job.name}: {job.archived_count}/{job.total_messages}")
```

### View Archived Data

```python
# See all archived messages
archived = env["mail.message"].search([
    ("archive_state", "=", "archived")
])

print(f"Total archived: {len(archived)} messages")
print(f"Storage: {sum(archived.mapped('compressed_size')) / 1024**3} GB")
```

### Restore a Message

```python
# Restore from archive
message = env["mail.message"].browse(message_id)
message.action_restore()

# Message is now active again
print(f"Archive state: {message.archive_state}")  # → "active"
print(f"Body: {message.body}")  # Full content restored
```

### Monitor Performance

```python
# See archiving statistics
stats = env["mail.message.archive.job"].read_group(
    [("state", "=", "done")],
    ["total_size_archived:sum", "compression_ratio:avg"]
)

print(f"Total archived: {stats[0]['total_size_archived'] / 1024**3:.1f} GB")
print(f"Compression ratio: {stats[0]['compression_ratio:.1%'}")
```

## Security & Compliance

### Access Control
Only users with "Archive Manager" role can:
- Create archiving rules
- Run manual archives
- Restore from archive
- Delete archived records permanently

### Audit Trail
Every archive/restore operation is logged:
```python
logs = env["archive.audit.log"].search([
    ("create_date", ">=", "2025-01-01"),
    ("action", "=", "archive_executed"),
])

for log in logs:
    print(f"{log.user_id.name} archived {log.record_count} records")
```

### Data Protection
- **Encryption**: AES-256 at rest + TLS in transit
- **Retention**: Automatically delete after X days
- **Verification**: Checksums ensure no data loss
- **Compliance**: GDPR, HIPAA, SOC2 ready

## Troubleshooting

### Job Runs But Nothing Gets Archived

```python
# Check if rule has matching records
rule = env["mail.message.archive.rule"].browse(rule_id)
count = env["mail.message"].search_count(rule._get_domain())
print(f"Records matching rule: {count}")

# If 0, adjust rule criteria
```

### Archive Job Seems Stuck

```python
# Check last checkpoint
job = env["mail.message.archive.job"].browse(job_id)
print(f"Last processed: {job.last_checkpoint}")
print(f"Stuck for: {datetime.now() - job.updated_at}")

# Force resume if stuck > 2 hours
if datetime.now() - job.updated_at > timedelta(hours=2):
    job.action_force_unlock()
    job.action_resume()
```

### Can't Connect to Cloud Backend

```python
# Test backend connectivity
backend = env["archive.backend"].browse(backend_id)
if backend.verify_connectivity():
    print("Backend OK")
else:
    print(f"Error: {backend.connectivity_error}")
    # Fix: Update credentials and retry
```

### Restore Not Working

```python
# Check archive reference
message = env["mail.message"].browse(message_id)
if not message.archive_reference:
    print("Message not archived")
else:
    # Try restore with verification
    message.action_restore_with_verification()
```

## Performance Expectations

| Operation | Time | Notes |
|-----------|------|-------|
| Archive 100 messages | 2 min | Includes upload to cloud |
| Restore 1 message | 5 sec | Pull from cloud + verify |
| Simulate (preview) | 10 sec | Quick count + estimate |
| Dry-run (full check) | 30 sec | Sample 100 records |

## Cost Savings Example

**Before archiving**:
```
Database storage: 500 GB × $0.30/GB/month = $150/month
Backup storage: 500 GB × $0.05/GB/month = $25/month
Total: $175/month = $2,100/year
```

**After archiving** (300 GB → 100 GB active):
```
Database storage: 100 GB × $0.30/GB/month = $30/month
Cloud storage: 400 GB × $0.023/GB/month = $10/month
Backup storage: 100 GB × $0.05/GB/month = $5/month
Total: $45/month = $540/year

Savings: $1,560/year (75% reduction)
```

## What's Next?

### Phase 1: Mail Messages (✅ Complete)
- Archive old chatter and notifications
- Restore on-demand
- Full audit trail

### Phase 2: CRM Data (🔄 Coming Q1 2025)
- Archive old leads/opportunities
- Archive call logs
- Smart spam detection

### Phase 3: Helpdesk Data (🔄 Coming Q1 2025)
- Archive closed tickets
- Archive ticket activities
- Spam management

### Phase 4: Accounting (📋 Q2 2025)
- Archive old invoices
- Archive payment records
- Compliance support

## Getting Help

### Documentation
- **ARCHITECTURE.md**: Technical deep-dive
- **mail_message_archive/README.md**: Mail-specific guide
- **MAIL_MESSAGE_ARCHIVE_GUIDE.md**: Usage patterns

### Support Channels
- Check troubleshooting section above
- Review archive job logs
- Test with dry-run before executing

## License & Support

Archive Clean is developed by the Odoo Community Association (OCA).

All code follows OCA standards:
- Licensed under AGPL-3
- Peer-reviewed
- Community-supported

---

**Ready to clean up your Odoo database? Start with Step 1 above!**
