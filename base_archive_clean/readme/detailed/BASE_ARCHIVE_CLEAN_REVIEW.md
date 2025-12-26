# Base Archive Clean - Architectural Review & Recommendations

## Executive Summary

Based on the concrete implementation of `mail_message_archive`, the base `archive_clean` module has a solid foundation but requires several enhancements to be more robust, extensible, and production-ready. This review identifies 12 key areas for improvement and provides specific recommendations.

---

## 1. Error Handling & Transaction Management

### Current State
- Basic try/catch blocks in job execution
- Limited rollback strategy
- No transaction isolation levels

### Recommendations
**Priority: HIGH**

```python
# Add to archive.job.mixin
class ArchiveJobMixin(models.Model):
    # New field for tracking partial failures
    is_partial_failure = fields.Boolean(
        string="Partial Failure",
        default=False,
        help="Job completed with some failures"
    )

    def _execute_with_transaction_safety(self):
        """Execute with proper transaction handling."""
        try:
            # Use SAVEPOINT for granular rollback
            with self.env.cr.savepoint():
                return self._execute()
        except Exception as e:
            # Log and mark as partial failure
            self.is_partial_failure = True
            raise
```

### Benefits
- Atomic operations per message (fail one, don't fail all)
- Better audit trail of what succeeded/failed
- Ability to retry failed batches

---

## 2. Attachment Handling Intelligence

### Current State
- mail_message_archive references attachments but doesn't manage them
- No deduplication of attachments
- No size optimization strategy

### Recommendations
**Priority: HIGH**

```python
# New model: archive.attachment.policy
class ArchiveAttachmentPolicy(models.Model):
    _name = "archive.attachment.policy"

    # Strategy options
    STRATEGIES = [
        ("archive_with_message", "Archive with Message"),
        ("archive_separately", "Archive Separately with Refs"),
        ("keep_only_refs", "Keep Only References"),
        ("delete_after_archive", "Delete After Archiving"),
    ]

    strategy = fields.Selection(STRATEGIES, default="archive_separately")
    deduplicate = fields.Boolean(
        default=True,
        help="Deduplicate identical attachments"
    )
    compression_algorithm = fields.Selection(
        [("gzip", "GZIP"), ("bzip2", "BZIP2"), ("lzma", "LZMA")],
        default="gzip"
    )
    keep_metadata = fields.Boolean(
        default=True,
        help="Preserve file metadata"
    )

    def deduplicate_attachments(self, attachments):
        """Remove duplicate attachments by hash."""
        seen_hashes = set()
        deduplicated = []

        for attachment in attachments:
            file_hash = self._compute_file_hash(attachment)
            if file_hash not in seen_hashes:
                deduplicated.append(attachment)
                seen_hashes.add(file_hash)

        return deduplicated
```

### Benefits
- Reduce storage costs by 20-50% through deduplication
- Flexible policies for different data types
- Maintain attachment reference integrity

---

## 3. Incremental Processing with Checkpoints

### Current State
- Batch processing exists but no checkpointing
- If job fails midway, all progress lost
- No resumption capability

### Recommendations
**Priority: HIGH**

```python
# Add to archive.job.mixin
class ArchiveJobMixin(models.Model):
    # Checkpoint tracking
    last_checkpoint_id = fields.Integer(
        string="Last Checkpoint Record ID",
        help="Last successfully archived record ID"
    )
    checkpoint_timestamp = fields.Datetime(
        string="Last Checkpoint Time",
        readonly=True
    )
    checkpoint_count = fields.Integer(
        default=100,
        help="Records to process before checkpoint"
    )

    def _process_with_checkpoints(self, records):
        """Process records with periodic checkpoints."""
        checkpoint_size = self.checkpoint_count
        processed = 0

        for i in range(0, len(records), checkpoint_size):
            batch = records[i : i + checkpoint_size]

            try:
                self._archive_batch(batch)
                processed += len(batch)

                # Save checkpoint
                self.last_checkpoint_id = batch[-1].id
                self.checkpoint_timestamp = fields.Datetime.now()
                self.archived_count = processed
                self.env.cr.commit()

            except Exception as e:
                _logger.error(f"Batch failed: {e}. Stopping at checkpoint.")
                raise

    def action_resume(self):
        """Resume from last checkpoint."""
        if not self.last_checkpoint_id:
            raise UserError("No checkpoint to resume from")

        # Find where we left off
        domain = self.rule_id._get_domain()
        domain += [("id", ">", self.last_checkpoint_id)]
        remaining = self.env["mail.message"].search(domain)

        self._process_with_checkpoints(remaining)
```

### Benefits
- Resume capability after failures
- No wasted effort redoing completed work
- Better observability into job progress

---

## 4. Notification & Alerting System

### Current State
- Logging only (to files)
- No user notifications
- No alerting on failures

### Recommendations
**Priority: MEDIUM**

```python
# New model: archive.notification
class ArchiveNotification(models.Model):
    _name = "archive.notification"
    _description = "Archive Job Notifications"

    SEVERITY = [("info", "Info"), ("warning", "Warning"), ("error", "Error")]

    job_id = fields.Many2one("archive.job.mixin", ondelete="cascade")
    severity = fields.Selection(SEVERITY)
    message = fields.Text()
    created_at = fields.Datetime(auto_now_add=True)

    def _send_notifications(self, job, severity, message):
        """Send notifications based on user preferences."""
        # Create record
        notification = self.create({
            "job_id": job.id,
            "severity": severity,
            "message": message,
        })

        # Send to job creator if error
        if severity == "error":
            job.create_uid.notify_danger(f"Archive job failed: {message}")

        # Send to configured administrators
        admin_users = self.env["res.users"].search([
            ("groups_id", "in", self.env.ref("archive_clean.group_archive_manager").id)
        ])

        for user in admin_users:
            user.notify_info(message)
```

### Benefits
- Real-time awareness of job status
- Proper escalation of errors
- Audit trail of all notifications

---

## 5. Domain Validation & Safety

### Current State
- Basic domain construction
- No validation of domains
- Risk of over-archiving

### Recommendations
**Priority: HIGH**

```python
# Add to archive.rule.mixin
class ArchiveRuleMixin(models.Model):

    def validate_domain(self, domain):
        """Validate archiving domain before execution."""
        validation_results = {
            "is_valid": True,
            "warnings": [],
            "estimated_count": 0,
            "sample_ids": [],
        }

        try:
            # Test domain validity
            test_records = self.env[self._name].search(domain, limit=1000)
            validation_results["estimated_count"] = len(test_records)
            validation_results["sample_ids"] = test_records[:5].ids

        except Exception as e:
            validation_results["is_valid"] = False
            validation_results["warnings"].append(f"Invalid domain: {e}")
            return validation_results

        # Check for safety issues
        if validation_results["estimated_count"] == 0:
            validation_results["warnings"].append("Domain matches no records")

        if validation_results["estimated_count"] > 100000:
            validation_results["warnings"].append(
                f"Large number of records ({validation_results['estimated_count']}). "
                "Consider splitting into smaller jobs."
            )

        return validation_results

    def action_validate_domain(self):
        """Validate domain from UI."""
        domain = self._get_domain()
        results = self.validate_domain(domain)

        if not results["is_valid"]:
            raise UserError(f"Domain validation failed: {results['warnings']}")

        # Show confirmation with sample records
        return {
            "type": "ir.actions.act_window",
            "name": "Domain Validation Results",
            "res_model": "archive.rule.validation",
            "view_mode": "form",
            "target": "new",
            "context": results,
        }
```

### Benefits
- Prevent accidental over-archiving
- Validate domains before execution
- User confirmation with data preview

---

## 6. Audit Trail & Compliance

### Current State
- Basic logging
- No compliance audit trail
- Limited traceability

### Recommendations
**Priority: MEDIUM**

```python
# New model: archive.audit.log
class ArchiveAuditLog(models.Model):
    _name = "archive.audit.log"
    _description = "Archive Audit Trail"
    _order = "created_at DESC"

    ACTION_TYPES = [
        ("rule_created", "Rule Created"),
        ("rule_modified", "Rule Modified"),
        ("job_created", "Job Created"),
        ("job_started", "Job Started"),
        ("job_completed", "Job Completed"),
        ("archive_executed", "Archive Executed"),
        ("restore_executed", "Restore Executed"),
        ("deletion_executed", "Deletion Executed"),
    ]

    action = fields.Selection(ACTION_TYPES, required=True)
    user_id = fields.Many2one("res.users", readonly=True)
    rule_id = fields.Many2one("archive.rule.mixin", ondelete="set null")
    job_id = fields.Many2one("archive.job.mixin", ondelete="set null")

    records_affected = fields.Integer(help="Number of records affected")
    data_size = fields.Integer(help="Size in bytes")
    details = fields.Text(help="JSON details of the action")

    created_at = fields.Datetime(default=fields.Datetime.now)

    @api.model
    def log_action(self, action, user_id, rule_id=None, job_id=None,
                   records_affected=0, data_size=0, details=None):
        """Log an archive action."""
        self.create({
            "action": action,
            "user_id": user_id,
            "rule_id": rule_id,
            "job_id": job_id,
            "records_affected": records_affected,
            "data_size": data_size,
            "details": details,
        })
```

### Benefits
- Full compliance audit trail
- Track who did what and when
- Support for compliance audits (GDPR, HIPAA, etc.)

---

## 7. Restore & Recovery Strategy

### Current State
- Basic restore functionality
- No verification after restore
- No recovery integrity checks

### Recommendations
**Priority: MEDIUM**

```python
# New mixin: restore.mixin
class RestoreMixin(models.Model):
    """Provides robust restore and recovery functionality."""

    def action_restore_with_verification(self):
        """Restore with integrity verification."""
        results = {"restored": 0, "verified": 0, "failed": 0}

        for record in self.filtered(lambda r: r.archive_state == "archived"):
            try:
                # Restore
                record.action_restore()
                results["restored"] += 1

                # Verify restoration
                if self._verify_restoration(record):
                    results["verified"] += 1
                else:
                    results["failed"] += 1
                    _logger.warning(
                        f"Restoration of {record._name} {record.id} "
                        "failed verification"
                    )

            except Exception as e:
                results["failed"] += 1
                _logger.error(f"Restore failed: {e}")

        return results

    def _verify_restoration(self, record):
        """Verify restored record integrity."""
        # Check that key fields are present
        # Verify attachment count matches
        # Validate relationships are intact
        # This is model-specific
        return True
```

### Benefits
- Ensure restoration success
- Detect corruption or partial restoration
- Recovery confidence

---

## 8. Concurrent Job Safety

### Current State
- No locking mechanism
- Risk of concurrent modifications
- No job queue management

### Recommendations
**Priority: MEDIUM**

```python
# Add to archive.job.mixin
class ArchiveJobMixin(models.Model):
    # Job concurrency control
    is_locked = fields.Boolean(
        default=False,
        help="Job is locked from modification"
    )
    lock_timeout = fields.Integer(
        default=3600,
        help="Seconds before lock expires"
    )

    def acquire_lock(self):
        """Acquire execution lock."""
        if self.is_locked:
            if self._lock_expired():
                _logger.warning(f"Lock expired, acquiring new lock")
                self.is_locked = False
            else:
                raise UserError("Job is already locked")

        self.write({"is_locked": True})

    def release_lock(self):
        """Release execution lock."""
        self.write({"is_locked": False})

    def _lock_expired(self):
        """Check if lock has expired."""
        if not self.locked_at:
            return False

        elapsed = (fields.Datetime.now() - self.locked_at).total_seconds()
        return elapsed > self.lock_timeout

    def action_force_unlock(self):
        """Force unlock (admin only)."""
        if not self.env.user._is_admin():
            raise UserError("Only administrators can force unlock")

        self.release_lock()
```

### Benefits
- Prevent concurrent job execution
- Detect and handle stuck jobs
- Proper job queuing

---

## 9. Metrics & Monitoring

### Current State
- Basic counters
- No performance metrics
- Limited visibility into effectiveness

### Recommendations
**Priority: MEDIUM**

```python
# New model: archive.metrics
class ArchiveMetrics(models.Model):
    _name = "archive.metrics"
    _description = "Archive Performance Metrics"

    job_id = fields.Many2one("archive.job.mixin")

    # Timing metrics
    total_duration = fields.Float(help="Total job duration in seconds")
    archive_duration = fields.Float(help="Time spent archiving")
    backend_duration = fields.Float(help="Time spent in backend")

    # Throughput metrics
    records_per_second = fields.Float()
    bytes_per_second = fields.Float()

    # Quality metrics
    success_rate = fields.Float(help="Percentage of successful archives")
    compression_ratio = fields.Float()

    # Cost metrics (if applicable)
    estimated_storage_cost = fields.Float()
    cost_per_record = fields.Float()

    def _calculate_metrics(self, job):
        """Calculate all metrics for a job."""
        duration = (job.completed_at - job.started_at).total_seconds()

        success_count = job.archived_count
        total_count = job.total_messages

        metrics = {
            "total_duration": duration,
            "records_per_second": success_count / duration if duration > 0 else 0,
            "success_rate": (success_count / total_count * 100) if total_count > 0 else 0,
        }

        return self.create(metrics)
```

### Benefits
- Performance visibility
- Optimize archiving strategy
- Cost tracking

---

## 10. Deduplication & Optimization

### Current State
- mail_message_archive handles message-specific dedup
- No generic deduplication strategy
- No compression optimizations

### Recommendations
**Priority: MEDIUM**

```python
# New mixin: dedup.mixin
class DedupMixin(models.Model):
    """Provides deduplication capabilities."""

    def deduplicate_before_archive(self, records):
        """Remove duplicates before archiving."""
        deduplicated = []
        seen_hashes = set()

        for record in records:
            record_hash = self._compute_record_hash(record)

            if record_hash not in seen_hashes:
                deduplicated.append(record)
                seen_hashes.add(record_hash)

        return deduplicated

    def _compute_record_hash(self, record):
        """Compute hash of record for dedup."""
        import hashlib
        import json

        # Get key fields for hashing
        key_data = self._get_dedup_fields(record)
        key_json = json.dumps(key_data, sort_keys=True, default=str)

        return hashlib.sha256(key_json.encode()).hexdigest()

    def _get_dedup_fields(self, record):
        """Get fields to use for dedup (override per model)."""
        # Default: use all non-relational fields
        return {f: record[f] for f in record._fields if record[f]}
```

### Benefits
- Reduce storage by eliminating duplicates
- Model-specific deduplication strategies
- Configurable dedup policies

---

## 11. Backend Extensibility

### Current State
- Basic backend interface
- Limited extensibility
- No plugin mechanism

### Recommendations
**Priority: LOW**

```python
# Enhance archive.backend with more methods
class ArchiveBackend(models.Model):
    _inherit = "archive.backend"

    def verify_connectivity(self):
        """Test backend connectivity."""
        try:
            # Backend-specific connectivity test
            self._test_connection()
            return True
        except Exception as e:
            return False

    def get_storage_stats(self):
        """Get backend storage statistics."""
        return {
            "total_size": self._get_total_size(),
            "record_count": self._get_record_count(),
            "oldest_record": self._get_oldest_record(),
            "newest_record": self._get_newest_record(),
        }

    def list_archived(self, limit=100):
        """List archived records in backend."""
        pass

    def verify_integrity(self):
        """Verify integrity of archived data."""
        pass
```

### Benefits
- Better backend abstraction
- Easier to add new backends
- Enhanced backend monitoring

---

## 12. Configuration Management

### Current State
- Settings scattered across multiple models
- No centralized configuration
- Hard to export/import settings

### Recommendations
**Priority: LOW**

```python
# New model: archive.config
class ArchiveConfig(models.Model):
    _name = "archive.config"
    _description = "Archive Configuration"
    _singleton = True

    # Global settings
    default_backend_id = fields.Many2one("archive.backend")
    auto_delete_days = fields.Integer(
        default=90,
        help="Days after archiving before auto-deletion"
    )
    max_job_workers = fields.Integer(
        default=4,
        help="Max concurrent archive jobs"
    )
    checkpoint_interval = fields.Integer(
        default=100,
        help="Records per checkpoint"
    )
    enable_compression = fields.Boolean(default=True)
    enable_deduplication = fields.Boolean(default=True)

    # Notification settings
    notify_on_completion = fields.Boolean(default=True)
    notify_on_failure = fields.Boolean(default=True)
    notification_email = fields.Char()

    def export_config(self):
        """Export configuration as JSON."""
        return {
            "version": "1.0",
            "default_backend": self.default_backend_id.name,
            "settings": {
                "auto_delete_days": self.auto_delete_days,
                "max_job_workers": self.max_job_workers,
                # ... other settings
            }
        }

    def import_config(self, config_data):
        """Import configuration from JSON."""
        # Validate and apply configuration
        pass
```

### Benefits
- Centralized configuration
- Easy to export/import
- Better deployment experience

---

## Implementation Roadmap

### Phase 1 (Priority: HIGH) - Weeks 1-2
1. Error handling & transaction management (3 days)
2. Attachment handling intelligence (4 days)
3. Domain validation & safety (3 days)

### Phase 2 (Priority: MEDIUM) - Weeks 3-4
4. Incremental processing with checkpoints (4 days)
5. Notification & alerting system (3 days)
6. Audit trail & compliance (3 days)

### Phase 3 (Priority: MEDIUM) - Weeks 5-6
7. Restore & recovery strategy (3 days)
8. Concurrent job safety (3 days)
9. Metrics & monitoring (3 days)

### Phase 4 (Priority: LOW) - Weeks 7-8
10. Deduplication & optimization (3 days)
11. Backend extensibility (2 days)
12. Configuration management (2 days)

---

## Success Metrics

After implementation, the base_archive_clean module should achieve:

- **Reliability**: 99.9% success rate on archive jobs
- **Recoverability**: Resume from checkpoint after failure
- **Performance**: Archive 1000+ messages/minute
- **Compliance**: Full audit trail for all actions
- **Usability**: 5-minute setup for new backends
- **Maintainability**: <5% of code for edge cases

---

## Conclusion

The mail_message_archive module demonstrates that the base_archive_clean architecture is sound. These 12 recommendations will make it more robust, compliant, and production-ready while maintaining flexibility for model-specific extensions (CRM, Helpdesk, etc.).

The modular approach allows incremental implementation without breaking existing functionality.
