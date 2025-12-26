# Base Archive Clean Module - Architecture & Design Document

## Executive Summary
Create a foundational archiving system that extends `autovacuum_message_attachment` concepts with:
- Cloud backup integration (S3/BigQuery)
- Intelligent deduplication
- Model-agnostic retention policies
- Safe archive-then-delete workflow
- Extensible architecture for model-specific implementations

## Key Findings from autovacuum_message_attachment Review

### What Works Well (Keep & Extend):
1. **Vacuum Rule Model** - Excellent retention policy framework
   - Retention time configuration
   - Model filtering with domain support
   - Pattern matching (filename_pattern)
   - Company-specific rules
   - Active/inactive rules

2. **Autovacuum Mixin** - Smart batch processing
   - Batch unlink (1000 records at a time)
   - Separate cursor for safety
   - Commit after each batch
   - Error handling

3. **Domain Building** - Flexible record selection
   - Time-based retention
   - Model-specific filters
   - Subtype filtering (for messages)
   - Pattern matching (for attachments)

### What to Improve:
1. **No Cloud Backup** - Direct deletion without archiving
2. **No Deduplication** - Doesn't merge duplicate attachments
3. **No Restore** - One-way deletion only
4. **No Verification** - No confirmation before deletion
5. **Limited to mail.message/ir.attachment** - Not extensible to other models

## Architecture Overview

### Component Structure

```
base_archive_clean/
├── Core Models
│   ├── archive.rule (extends vacuum.rule concepts)
│   ├── archive.policy (new - classification rules)
│   ├── archive.job (tracks archival operations)
│   └── archive.backend (integrates with storage_backend)
│
├── Mixins
│   ├── archive.mixin (base archiving logic)
│   ├── dedup.mixin (attachment deduplication)
│   └── restore.mixin (restoration logic)
│
├── Model Extensions
│   ├── ir.attachment (add dedup + archive)
│   ├── mail.message (add archive support)
│   └── base (make any model archivable)
│
└── Backends
    ├── backend.s3 (uses storage_backend)
    ├── backend.bigquery (new)
    └── backend.local (for testing)
```

### Data Flow

```
┌─────────────────┐
│  Source Models  │
│ (any Odoo model)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐
│  Archive Rules  │─────▶│  Archive Policy  │
│  (what/when)    │      │  (classification)│
└────────┬────────┘      └──────────────────┘
         │
         ▼
┌─────────────────┐
│  Archive Job    │
│  (orchestrator) │
└────────┬────────┘
         │
         ├─▶ Deduplication (if enabled)
         │
         ├─▶ Cloud Backup (S3/BigQuery)
         │
         ├─▶ Verification (checksum/count)
         │
         └─▶ Local Deletion (if verified)
```

## Detailed Component Design

### 1. Archive Rule Model

```python
# TODO: Extend vacuum.rule concepts
class ArchiveRule(models.Model):
    _name = 'archive.rule'
    _description = 'Archive & Retention Rule'

    # From vacuum.rule (keep these)
    name = fields.Char(required=True)
    retention_time = fields.Integer(default=365)
    model_ids = fields.Many2many('ir.model')
    model_filter_domain = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company')

    # NEW: Archive-specific fields
    action = fields.Selection([
        ('archive', 'Archive to Cloud'),
        ('delete', 'Direct Delete'),
        ('deduplicate', 'Deduplicate Only')
    ], default='archive')

    backend_id = fields.Many2one('archive.backend')
    verify_before_delete = fields.Boolean(default=True)
    enable_deduplication = fields.Boolean(default=False)

    # Classification policy
    policy_id = fields.Many2one('archive.policy')

    # Statistics
    archived_count = fields.Integer(compute='_compute_stats')
    space_saved_mb = fields.Float(compute='_compute_stats')
```

### 2. Archive Policy (NEW - Classification)

```python
# TODO: Define retention policies based on record characteristics
class ArchivePolicy(models.Model):
    _name = 'archive.policy'
    _description = 'Archive Classification Policy'

    name = fields.Char(required=True)

    # Classification criteria
    priority = fields.Integer(default=10)

    # Attachment-specific rules
    max_file_versions = fields.Integer(
        help="Keep only N most recent versions of same file on a record"
    )
    preferred_mime_types = fields.Char(
        help="application/pdf,image/png (keep these, archive others)"
    )
    min_age_days = fields.Integer(default=365)

    # Size thresholds
    large_file_threshold_mb = fields.Float(
        default=10.0,
        help="Files larger than this always archived"
    )

    # Record state filters
    record_state_domain = fields.Text(
        help="e.g., [('state', 'in', ['done', 'cancel'])]"
    )
```

### 3. Archive Backend (Integration Layer)

```python
# TODO: Integrate with storage_backend for S3/SFTP
# TODO: Add BigQuery as new backend type
class ArchiveBackend(models.Model):
    _name = 'archive.backend'
    _description = 'Archive Storage Backend'

    name = fields.Char(required=True)
    backend_type = fields.Selection([
        ('s3', 'Amazon S3'),
        ('gcs', 'Google Cloud Storage'),
        ('bigquery', 'Google BigQuery (structured data)'),
        ('sftp', 'SFTP'),
        ('local', 'Local Filesystem (testing only)')
    ], required=True)

    # Link to storage_backend if applicable
    storage_backend_id = fields.Many2one('storage.backend')

    # BigQuery specific
    bq_project_id = fields.Char()
    bq_dataset = fields.Char()
    bq_table_prefix = fields.Char()

    # Connection config
    config_json = fields.Text(help="Backend-specific JSON config")

    # Methods
    def upload_batch(self, records, metadata):
        """Upload records to backend"""
        pass

    def verify_upload(self, batch_id, checksums):
        """Verify data integrity"""
        pass

    def search_archived(self, domain):
        """Search archived records"""
        pass

    def restore_records(self, record_ids):
        """Restore records from archive"""
        pass
```

### 4. Archive Mixin (Core Logic)

```python
# TODO: Create extensible mixin for any model
class ArchiveMixin(models.AbstractModel):
    _name = 'archive.mixin'
    _inherit = 'autovacuum.mixin'  # Extend existing vacuum mixin

    is_archived = fields.Boolean(
        default=False,
        index=True,
        help="True if this record has been archived to cloud"
    )
    archive_date = fields.Datetime()
    archive_backend_id = fields.Many2one('archive.backend')
    archive_reference = fields.Char(
        help="Backend-specific ID for retrieval"
    )

    # OVERRIDE: batch_unlink to archive first
    def batch_unlink(self):
        """Archive before unlinking"""
        # TODO: Group by rule/backend
        # TODO: Call archive_batch_with_verification
        # TODO: Only unlink if verification passes
        pass

    def archive_batch_with_verification(self, rule_id):
        """
        PSEUDOCODE:
        1. Prepare metadata (model, ids, checksums)
        2. Upload to backend
        3. Wait for confirmation
        4. Verify checksums
        5. If verified: mark as archived, return True
        6. If failed: rollback, return False
        """
        pass

    def search_including_archived(self, domain):
        """Unified search across local + archived"""
        pass

    def restore_from_archive(self):
        """Pull record back from cloud"""
        pass
```

### 5. Deduplication Mixin (Attachment-Specific)

```python
# TODO: Implement intelligent attachment deduplication
class DedupMixin(models.AbstractModel):
    _name = 'dedup.mixin'
    _description = 'Attachment Deduplication Logic'

    checksum = fields.Char(index=True)  # Already exists in ir.attachment
    file_size = fields.Integer()  # Already exists

    duplicate_of_id = fields.Many2one(
        'ir.attachment',
        help="If this is a duplicate, points to the master"
    )
    duplicate_count = fields.Integer(
        compute='_compute_duplicates',
        help="How many dupes of this file exist"
    )

    def find_duplicates(self):
        """
        PSEUDOCODE:
        1. Group by checksum
        2. For each group:
           - Keep the newest or most-referenced version
           - Mark others as duplicates
        3. Return list of duplicate IDs
        """
        pass

    def merge_duplicates(self, master_id, duplicate_ids):
        """
        PSEUDOCODE:
        1. Update all references to point to master
        2. Archive duplicate files
        3. Update statistics
        """
        pass
```

## Retention Policy Examples

### Example 1: Old Sales Orders
```python
Policy: "Old Sale Orders - Minimal Retention"
- Model: sale.order
- State: done, cancel
- Age: > 3 years
- Keep: Latest invoice PDF only
- Archive: All other attachments
- Archive: All mail.message except invoicing events
```

### Example 2: Attachments on Completed Projects
```python
Policy: "Project Archival"
- Model: project.project
- State: done
- Age: > 2 years
- Keep: Final deliverable (newest PDF)
- Deduplicate: All images/documents
- Archive: Task messages
```

### Example 3: Large Files Regardless of Age
```python
Policy: "Large File Archival"
- Model: *
- File Size: > 10MB
- Age: > 90 days
- Action: Always archive to S3
- Keep: Metadata + thumbnail in Odoo
```

## Database Schema Changes

### New Tables
- `archive_rule` - Rules engine
- `archive_policy` - Classification logic
- `archive_job` - Job tracking
- `archive_batch` - Batch metadata
- `archive_backend` - Storage config

### Field Additions
- `ir.attachment`: `is_archived`, `archive_date`, `archive_backend_id`, `duplicate_of_id`
- `mail.message`: `is_archived`, `archive_date`, `archive_backend_id`
- Any model with archive.mixin: Same fields

## Safety & Verification Protocol

```python
# CRITICAL: Never delete without verification
def safe_archive_workflow(records, rule):
    """
    1. SELECT records to archive
    2. CREATE archive_batch record (status='pending')
    3. UPLOAD to backend
    4. VERIFY:
       - Record count matches
       - Checksums match
       - Backend confirms storage
    5. IF verified:
       - UPDATE records (is_archived=True)
       - DELETE from local (optional, based on rule)
       - UPDATE archive_batch (status='completed')
    6. IF verification fails:
       - LOG error
       - UPDATE archive_batch (status='failed')
       - RETRY or ALERT admin
       - DO NOT DELETE
    """
```

## Phase 1 Implementation Plan

### Step 1: Base Module Scaffolding ✓ (In Progress)
- Create module structure
- Define models (pseudo-code first)
- Write README sections
- Create security groups

### Step 2: Core Models (Next)
- Implement archive.rule
- Implement archive.policy
- Implement archive.backend (abstract)
- Add tests

### Step 3: Archive Mixin
- Create archive.mixin
- Extend ir.attachment
- Extend mail.message
- Batch operations

### Step 4: Deduplication
- Implement dedup.mixin
- Checksum-based matching
- Reference updating
- Statistics

### Step 5: Backend Integrations
- S3 backend (via storage_backend)
- BigQuery backend (new)
- Verification logic
- Restore functionality

### Step 6: UI & Wizards
- Archive wizard
- Search wizard (local + archived)
- Restore wizard
- Job monitoring views

## Integration with Existing Modules

### autovacuum_message_attachment
- EXTEND: vacuum.rule → archive.rule
- EXTEND: autovacuum.mixin → archive.mixin
- KEEP: Batch processing logic
- ADD: Archive-before-delete workflow

### storage_backend
- USE: Existing S3/SFTP backends
- EXTEND: Add archive-specific methods
- ADD: BigQuery as new backend type

### mail
- EXTEND: mail.message with archive.mixin
- KEEP: All existing functionality
- ADD: Archived message search

## Success Metrics

### Phase 1 (Foundation)
- [ ] Module installed without errors
- [ ] Archive rules configurable
- [ ] Policies definable
- [ ] Test backend working

### Phase 2 (Core Features)
- [ ] Messages can be archived
- [ ] Attachments can be archived
- [ ] Deduplication reduces storage 20%+
- [ ] Verification prevents data loss

### Phase 3 (Production Ready)
- [ ] 50%+ database size reduction
- [ ] Backup/restore times reduced 60%+
- [ ] Search includes archived data
- [ ] Zero data loss incidents
- [ ] Performance improved (queries faster)

## Next Actions

1. Review this document with team
2. Finalize model structure
3. Create detailed pseudo-code for archive.mixin
4. Build MVP with local backend (testing)
5. Add S3 backend
6. Add BigQuery backend
7. Production rollout with monitoring
