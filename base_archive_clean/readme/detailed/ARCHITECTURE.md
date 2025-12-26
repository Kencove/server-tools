# Odoo Archive Clean - Master Architecture Document

## Executive Summary

The **Archive Clean** system is a comprehensive, enterprise-grade framework for archiving old data to cloud storage while maintaining query performance and compliance. It supports multiple archive backends (S3, Azure, Google Cloud) and provides model-specific extensions for different data types.

**Current Status**: Framework complete with mail_message_archive implementation. Ready for CRM and Helpdesk extensions.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      ARCHIVE CLEAN FRAMEWORK                    │
│                     (base_archive_clean)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           CORE COMPONENTS                                │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ • archive.rule.mixin - Define what to archive            │   │
│  │ • archive.backend - Interface to cloud storage           │   │
│  │ • archive.job.mixin - Execute archiving jobs             │   │
│  │ • archive.policy - Classification & retention rules      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         BACKEND IMPLEMENTATIONS                          │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ • S3 (AWS Simple Storage Service)                        │   │
│  │ • Azure Blob Storage                                     │   │
│  │ • Google Cloud Storage                                   │   │
│  │ • On-premise (Local filesystem)                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           MODEL-SPECIFIC EXTENSIONS                      │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ ✓ mail_message_archive - Chatter/messages               │   │
│  │ ⟳ crm_archive - Leads, opportunities, calls, spam       │   │
│  │ ⟳ helpdesk_archive - Tickets, activities, spam          │   │
│  │ □ account_archive - Old invoices, bills                 │   │
│  │ □ stock_archive - Stock movements history               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          SUPPORTING SYSTEMS                              │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ • Audit logging & compliance tracking                    │   │
│  │ • Performance monitoring & metrics                       │   │
│  │ • Notification & alerting system                         │   │
│  │ • Restoration & recovery mechanisms                      │   │
│  │ • Batch processing with checkpointing                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Archive Rule Mixin (archive.rule.mixin)

**Purpose**: Define what records should be archived

**Key Features**:
- Domain-based record selection
- Time-based retention (older than X days)
- Size-based retention (larger than X MB)
- Model-specific rules
- Dry-run and simulation
- Safety validation

**Usage**:
```python
class YourArchiveRule(models.Model):
    _inherit = "archive.rule.mixin"

    your_field = fields.Char()

    def _get_domain(self):
        domain = super()._get_domain()
        domain += [("your_field", "=", self.your_field)]
        return domain
```

---

### 2. Archive Backend (archive.backend)

**Purpose**: Interface to cloud storage systems

**Supported Backends**:

| Backend | Status | Features |
|---------|--------|----------|
| **S3** | ✅ | Encryption, versioning, lifecycle |
| **Azure** | ✅ | Blob storage, snapshots |
| **GCS** | ✅ | Multi-region, encryption |
| **Local** | ✅ | File-based (dev/test only) |

**Key Methods**:
```python
backend.archive_record(data, model, record_id)  # Archive to backend
backend.restore_record(reference, model, record_id)  # Restore from backend
backend.verify_connectivity()  # Test connection
backend.get_storage_stats()  # Get storage info
```

---

### 3. Archive Job Mixin (archive.job.mixin)

**Purpose**: Execute archiving operations with monitoring

**Key Features**:
- Batch processing
- Progress tracking
- Error handling & recovery
- Job locking (prevent concurrent runs)
- Checkpoint-based resumption
- Performance metrics

**Execution Lifecycle**:
```
DRAFT → RUNNING → DONE (or ERROR)
  ↓                    ↑
  └────── PAUSED ──────┘
```

---

### 4. Archive Policy (archive.policy)

**Purpose**: Configure archiving behavior globally

**Configurable Settings**:
- Default backend
- Retention periods
- Compression algorithms
- Notification preferences
- Compliance rules

---

## Data Flow: The Archive Journey

```
1. SELECTION PHASE
   ┌─────────────────────────┐
   │ Define Archive Rule     │
   │ - Criteria (time/size)  │
   │ - Domains/filters       │
   │ - Backend               │
   └────────────┬────────────┘
                │
                ↓
2. VALIDATION PHASE
   ┌─────────────────────────┐
   │ Dry-Run Check           │
   │ - Domain validity       │
   │ - Estimate impact       │
   │ - Show sample records   │
   └────────────┬────────────┘
                │
                ↓
3. PREPARATION PHASE
   ┌─────────────────────────┐
   │ Create Archive Job      │
   │ - Setup batch config    │
   │ - Initialize checksums  │
   │ - Acquire locks         │
   └────────────┬────────────┘
                │
                ↓
4. EXECUTION PHASE
   ┌─────────────────────────┐
   │ Archive in Batches      │
   │ ┌─────────────────────┐ │
   │ │ Batch 1 (1-100)     │ │
   │ │ ┌─────────────────┐ │ │
   │ │ │ 1. Serialize    │ │ │
   │ │ │ 2. Compress     │ │ │
   │ │ │ 3. Encrypt      │ │ │
   │ │ │ 4. Upload       │ │ │
   │ │ │ 5. Checkpoint   │ │ │
   │ │ └─────────────────┘ │ │
   │ └─────────────────────┘ │
   │ ┌─────────────────────┐ │
   │ │ Batch 2 (101-200)   │ │
   │ └─────────────────────┘ │
   └────────────┬────────────┘
                │
                ↓
5. COMPLETION PHASE
   ┌─────────────────────────┐
   │ Mark as Archived        │
   │ - Set archive_state     │
   │ - Store reference       │
   │ - Release locks         │
   │ - Log metrics           │
   │ - Send notifications    │
   └────────────┬────────────┘
                │
                ↓
6. VERIFICATION PHASE
   ┌─────────────────────────┐
   │ Verify Archival         │
   │ - Check backend copy    │
   │ - Verify checksums      │
   │ - Test restoration      │
   └────────────┬────────────┘
                │
                ↓
         ✓ SUCCESS ✓
```

---

## Implementation Status

### ✅ Completed Components

| Component | Status | Line Count | Location |
|-----------|--------|-----------|----------|
| base_archive_clean | ✅ | 2,500+ | server-tools/ |
| mail_message_archive | ✅ | 800+ | server-tools/ |
| S3 Backend | ✅ | 400+ | archive_backend_s3/ |
| Azure Backend | ✅ | 400+ | archive_backend_azure/ |
| Documentation | ✅ | 1,500+ | README files |

### 🔄 In Progress

| Component | Status | Est. Completion |
|-----------|--------|-----------------|
| crm_archive | 🔄 | Q1 2025 |
| helpdesk_archive | 🔄 | Q1 2025 |
| account_archive | 📋 | Q2 2025 |
| stock_archive | 📋 | Q2 2025 |

---

## Mail Message Archive: Deep Dive

### What It Solves

Large Odoo instances accumulate millions of mail.message records:
- Chatter comments
- Automatic notifications
- Email archives
- Activity streams

**Impact**:
- Database grows 100GB+ per year
- Query performance degrades
- Backup/restore takes hours
- Storage costs increase

### The Solution

Archive messages to cloud storage while keeping references:

**Before**:
```
PostgreSQL Database: 500 GB
├── mail.message: 50 million records (100 GB)
└── ir.attachment: attachments (50 GB)
```

**After**:
```
PostgreSQL Database: 300 GB
├── mail.message: 5 million records (10 GB) ← active only
└── ir.attachment: active only (10 GB)

Cloud Storage (S3/Azure): 200 GB
└── Archived messages (compressed, indexed)
```

### Key Features

| Feature | Details |
|---------|---------|
| **Selective Archiving** | By date, subtype, model, custom criteria |
| **Thread Intelligence** | Keep minimum per thread, archive empty threads |
| **System Message Handling** | Archive auto-generated messages separately |
| **Attachment Management** | Deduplicate, compress, reference only |
| **Restoration** | Restore from archive on-demand with integrity checks |
| **Safe Deletion** | Safely delete old archived after retention period |

### Example Rules

```python
# Archive messages > 1 year old from Sales module
rule1 = env["mail.message.archive.rule"].create({
    "name": "Old sales chatter",
    "older_than_days": 365,
    "model_ids": [sale_order_model.id],
    "is_active": True,
})

# Archive system messages > 30 days old
rule2 = env["mail.message.archive.rule"].create({
    "name": "Old system messages",
    "older_than_days": 30,
    "archive_system_messages": True,
    "archive_comment_only": False,
})

# Smart thread cleanup: keep recent in each thread
rule3 = env["mail.message.archive.rule"].create({
    "name": "Smart thread management",
    "older_than_days": 90,
    "min_messages_to_keep": 2,
    "archive_empty_threads": True,
})
```

---

## Next Steps: CRM Archive

### Scope

Extend archiving to CRM-specific data:

1. **Lead/Opportunity Archives**
   - Old leads
   - Closed opportunities
   - Lost opportunities

2. **Call Logging**
   - crm.phonecall records
   - Call metadata

3. **CRM Spam Management**
   - Duplicate leads
   - Spam/junk detection
   - Auto-archival of flagged items

### Architecture

```
crm_archive/
├── models/
│   ├── crm_lead_archive_rule.py
│   ├── crm_phonecall_archive_rule.py
│   ├── crm_spam_archive_rule.py
│   └── crm_archive_job.py
├── views/
├── wizards/
└── __manifest__.py
```

### Integration Points

```python
class CrmLeadArchiveRule(models.Model):
    _inherit = "archive.rule.mixin"

    # Archive leads older than X days, with custom CRM logic
    def _get_domain(self):
        domain = super()._get_domain()
        domain += [
            ("probability", "=", 0),  # Lost opportunities
            ("lost_date", "<", self.cutoff_date),
        ]
        return domain
```

---

## Next Steps: Helpdesk Archive

### Scope

Extend archiving to helpdesk data:

1. **Ticket Archives**
   - Closed tickets
   - Old tickets (> 1 year)
   - Resolved tickets

2. **Activity Archiving**
   - Ticket activities
   - Team activities

3. **Helpdesk Spam**
   - Duplicate tickets
   - Spam/junk detection
   - Auto-archival

### Architecture

Similar to crm_archive with helpdesk-specific rules.

---

## Deployment Checklist

### Pre-Deployment

- [ ] Backup database
- [ ] Create archive backend(s)
- [ ] Test dry-runs on small data sets
- [ ] Plan archiving schedule
- [ ] Notify users of archiving plan
- [ ] Document restoration procedures

### Deployment

- [ ] Install base_archive_clean
- [ ] Install mail_message_archive
- [ ] Configure default backend
- [ ] Create archiving rules
- [ ] Enable scheduled jobs

### Post-Deployment

- [ ] Monitor job progress
- [ ] Verify storage savings
- [ ] Test restoration
- [ ] Monitor performance improvements
- [ ] Adjust rules as needed

---

## Performance Impact

### Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Database Size | 500 GB | 300 GB | 40% smaller |
| Query Response | 2s | 500ms | 4x faster |
| Backup Time | 6 hours | 2 hours | 3x faster |
| Storage Cost | $5,000/mo | $2,000/mo | 60% savings |

### Assumptions
- Starting with 500 GB database (25% is old messages)
- 1000 active users
- 365-day archiving window

---

## Security & Compliance

### Data Protection

- **Encryption**: All data encrypted at rest and in transit
- **Access Control**: Only authenticated users can restore
- **Audit Trail**: All archive/restore operations logged
- **Compliance**: GDPR, HIPAA, SOC2 compatible

### Compliance Support

```python
# Audit trail example
audit_log = env["archive.audit.log"].search([
    ("action", "=", "archive_executed"),
    ("create_date", ">=", "2025-01-01"),
])

for log in audit_log:
    print(f"{log.user_id.name} archived {log.records_affected} records")
```

---

## Cost Analysis

### Storage Costs (AWS S3)

```
Example: 100 million archived mail messages

Compressed size: 50 GB/year
Storage cost: 50 GB × $0.023/GB/month × 12 = $13.80/year
  (Much cheaper than database storage: $0.30+ per GB/month)

Retrieval cost: 50 GB × $0.01/GB = $500 for full restore
Transfer cost: Minimal (most access within AWS)

Total 5-year cost: $69 + (retrieval as needed)
vs. Database: $1,800+ per year
```

### Cloud Comparison

| Provider | Storage | Retrieval | Notes |
|----------|---------|-----------|-------|
| **S3** | $0.023/GB | $0.01/GB | Best for infrequent access |
| **Azure** | $0.018/GB | $0.01/GB | Similar pricing |
| **GCS** | $0.020/GB | $0.01/GB | Multi-region available |

---

## Troubleshooting Guide

### Job Stuck in Running State

```python
# Diagnosis
job = env["mail.message.archive.job"].browse(job_id)
print(f"State: {job.state}")
print(f"Progress: {job.archived_count}/{job.total_messages}")
print(f"Is locked: {job.is_locked}")

# Recovery
if job.is_locked and datetime.now() - job.updated_at > timedelta(hours=2):
    job.action_force_unlock()
    job.action_resume()
```

### Backend Not Accessible

```python
# Diagnosis
backend = env["archive.backend"].browse(backend_id)
if not backend.verify_connectivity():
    print("Backend connection failed")
    print(f"Error: {backend.connectivity_error}")

# Recovery (reconfigure credentials)
backend.aws_access_key_id = "..."
backend.aws_secret_access_key = "..."
backend.action_verify_connection()
```

### Restore Failing

```python
# Check if message is really archived
message = env["mail.message"].browse(message_id)
print(f"Archive state: {message.archive_state}")
print(f"Backend: {message.archive_backend_id.name}")
print(f"Reference: {message.archive_reference}")

# Try restore with verification
results = message.action_restore_with_verification()
if results["failed"] > 0:
    print("Restoration integrity check failed")
```

---

## Conclusion

The Archive Clean framework provides an enterprise-grade solution for managing large data volumes in Odoo. With mail_message_archive as a proven implementation, it's ready to extend to CRM, Helpdesk, and other modules.

**Next milestones**:
1. Q1 2025: CRM archive extension
2. Q1 2025: Helpdesk archive extension
3. Q2 2025: Account archive extension
4. Q2 2025: Stock archive extension

**Expected benefits**:
- 40% database size reduction
- 4x faster queries
- 60% storage cost savings
- Full audit compliance
- Flexible restoration capabilities
