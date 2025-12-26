# Base Archive Clean - Architecture Review & Robustness Improvements

## Executive Summary

The current base_archive_clean design provides a solid foundation, but needs several enhancements to be production-ready, especially for multi-model extensibility. This document identifies critical gaps and provides concrete recommendations.

---

## 1. CRITICAL ISSUES

### 1.1 Transaction Management & Rollback

**Issue**: Current `archive_job.execute()` has multiple `commit()` calls that prevent rollback if a later step fails.

**Impact**: If verification fails at step 7, steps 1-6 are already committed. Can't rollback without manual intervention.

**Recommendation**:
```python
# Use Odoo's transactional savepoints
def execute(self):
    try:
        # Don't commit until entire job succeeds
        with self.env.cr.savepoint('archive_job'):
            records = self._search_records()
            classified = self._classify_records(records)
            batches = self._create_batches(classified)
            self._upload_batches(batches)

            if self.rule_id.verify_before_delete:
                self._verify_uploads()

            if self.rule_id.action == 'archive_delete':
                self._delete_local_records()

        # Only commit if entire workflow succeeds
        self.env.cr.commit()
        self.write({'state': 'done'})

    except Exception as e:
        self.env.cr.rollback()  # Automatic via savepoint
        self.write({'state': 'failed', 'error_message': str(e)})
        raise
```

**Priority**: CRITICAL

---

### 1.2 Concurrency & Race Conditions

**Issue**: Multiple jobs can run simultaneously on same rule, causing duplicate archiving.

**Recommendation**:
- Add `locks` mechanism in `archive.rule`:
  - Field: `job_running` (Boolean, non-storable, computed)
  - Prevents new jobs while one is executing

- Alternative: Use database advisory locks:
```python
def _acquire_rule_lock(self):
    """Acquire exclusive lock for this rule"""
    self.env.cr.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (abs(hash(self._name + str(self.id))) % 2**31,)
    )
```

**Priority**: HIGH

---

### 1.3 Incomplete Error Handling

**Issue**: `failed_record_ids` stored as Text, but no way to handle partially completed batches.

**Recommendation**:
- Distinguish between recoverable and fatal errors
- Add error classification:
  ```python
  ERROR_TYPES = {
      'ACCESS_DENIED': 'recoverable',  # User can retry with better permissions
      'STORAGE_FULL': 'recoverable',    # Admin can free space
      'DATA_CORRUPTION': 'fatal',       # Can't archive this record safely
      'NETWORK_ERROR': 'recoverable',   # Retry later
      'SCHEMA_MISMATCH': 'fatal',       # Record structure changed
  }
  ```

**Priority**: HIGH

---

## 2. DATA INTEGRITY ISSUES

### 2.1 Checksum Strategy Insufficient

**Issue**:
- Only validates record count and checksums
- Doesn't validate data completeness or schema

**Recommendation**:
```python
def _verify_uploads(self):
    """Enhanced verification"""
    checks = {
        'record_count': self._verify_record_count(),
        'checksum': self._verify_checksums(),
        'schema': self._verify_schema_match(),  # Check field counts, types
        'references': self._verify_foreign_keys(),  # Sample check FK integrity
        'metadata': self._verify_metadata_integrity(),  # Timestamps, owners
    }

    if not all(checks.values()):
        raise ArchiveVerificationFailed(checks)
```

**Priority**: HIGH

---

### 2.2 Missing Audit Trail

**Issue**: No detailed logging of what was archived, by whom, when, and why.

**Recommendation**:
- Create `archive.log` model for detailed audit trail:
  ```python
  class ArchiveLog(models.Model):
      _name = "archive.log"

      job_id = fields.Many2one("archive.job")
      record_model = fields.Char()
      record_id = fields.Integer()
      original_values = fields.Text(help="JSON snapshot before archive")
      action = fields.Selection([('archive', 'Archive'), ('delete', 'Delete')])
      timestamp = fields.Datetime(default=now)
      user_id = fields.Many2one("res.users")
      reason = fields.Char()
  ```

**Priority**: MEDIUM (Legal/Compliance)

---

## 3. ARCHITECTURAL IMPROVEMENTS

### 3.1 Mixin Pattern Clarification

**Issue**: Unclear how mixin pattern interacts with archive_mixin and model-specific implementations.

**Recommendation**:
```python
# archive_mixin.py provides base capabilities
class ArchiveMixin(models.AbstractModel):
    _name = "archive.mixin"

    is_archived = fields.Boolean(
        help="Record archived to cloud storage"
    )
    archive_date = fields.Datetime()
    archive_location = fields.Char()
    archive_job_id = fields.Many2one("archive.job")

    def archive(self, backend_id, verify=True):
        """Archive this record"""
        pass

# Then mail.message extends it:
class MailMessage(models.Model):
    _inherit = ["mail.message", "archive.mixin"]

    # Mail-specific archiving logic
    def _get_archive_attachments(self):
        """Get attachments to archive with message"""
        return self.attachment_ids

# Other models inherit similarly:
class SaleOrder(models.Model):
    _inherit = ["sale.order", "archive.mixin"]
    # sale-specific logic
```

**Priority**: MEDIUM

---

### 3.2 Policy Application Order Matters

**Issue**: Current flow applies policy AFTER searching, but policy domain is not used in search.

**Recommendation**:
- Incorporate policy domain into search:
```python
def _search_records(self):
    # Build domain from BOTH rule and policy
    domain = self.rule_id._build_archive_domain()

    if self.rule_id.policy_id:
        # Policy domain further restricts records
        policy_domain = self.rule_id.policy_id._build_domain()
        domain = expression.AND([domain, policy_domain])

    return self.env[model_name].search(domain)
```

**Priority**: MEDIUM

---

## 4. MISSING FEATURES

### 4.1 Incremental Processing with Checkpoints

**Issue**: No way to resume a failed job; must restart from beginning.

**Recommendation**:
- Add checkpoint mechanism in archive_batch:
```python
class ArchiveBatch(models.Model):
    checkpoint_number = fields.Integer(default=0)
    checkpoint_data = fields.Text(help="Serialized job state")

    def save_checkpoint(self, data):
        """Save progress checkpoint"""
        self.write({
            'checkpoint_data': json.dumps(data),
            'checkpoint_number': self.checkpoint_number + 1,
        })

    def resume_from_checkpoint(self):
        """Resume from last checkpoint"""
        if self.checkpoint_data:
            return json.loads(self.checkpoint_data)
        return None
```

**Priority**: MEDIUM

---

### 4.2 Predictive Archiving (What-If Analysis)

**Issue**: Users can preview, but no way to estimate impact (space saved, runtime).

**Recommendation**:
```python
class ArchiveRule(models.Model):
    def action_estimate_impact(self):
        """Estimate archive impact without executing"""
        # Search records
        records = self._search_records_to_archive()

        # Estimate stats
        estimate = {
            'record_count': len(records),
            'estimated_size_mb': self._estimate_size(records),
            'estimated_duration_minutes': self._estimate_duration(records),
            'estimated_space_saved': self._estimate_space_saved(records),
        }

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'archive.estimate',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_estimate_data': json.dumps(estimate)},
        }
```

**Priority**: LOW (Nice-to-have)

---

### 4.3 Scheduled Downtime Protection

**Issue**: No protection against archiving during peak hours.

**Recommendation**:
```python
class ArchiveRule(models.Model):
    skip_hours_start = fields.Float(help="Don't archive 9-17 (9.0-17.0)")
    skip_hours_end = fields.Float()
    skip_weekdays = fields.Char(help="1=Monday, 0=Sunday (e.g. '0,6' = weekends)")

    def _can_run_now(self):
        """Check if it's safe to run"""
        now = datetime.now()
        hour = now.hour + now.minute / 60.0

        # Check hour restriction
        if self.skip_hours_start and self.skip_hours_end:
            if self.skip_hours_start < hour < self.skip_hours_end:
                return False

        # Check day restriction
        if self.skip_weekdays:
            skip_days = [int(d) for d in self.skip_weekdays.split(',')]
            if now.weekday() in skip_days:
                return False

        return True
```

**Priority**: LOW

---

## 5. MAIL.MESSAGE SPECIFIC RECOMMENDATIONS

When implementing mail_message_archive, address these:

### 5.1 Thread Management
**Problem**: Messages form threads/conversations. Archiving one message may break thread continuity.

**Solution**:
- Add rule field: `archive_entire_thread` (Boolean)
- If enabled, archive all messages in thread together

### 5.2 Attachment Handling
**Problem**: Messages may have 1-N attachments. Attachment archiving strategy matters.

**Solution**:
```python
class MailArchivePolicy(models.Model):
    attachment_strategy = fields.Selection([
        ('archive_with_message', 'Archive with message'),
        ('archive_separately', 'Archive to separate storage'),
        ('delete_large', 'Delete attachments > X MB'),
        ('keep_recent', 'Keep last N versions'),
    ])

    large_attachment_threshold_mb = fields.Float(default=10)
    keep_attachment_versions = fields.Integer(default=1)
```

### 5.3 Quoted Message Deduplication
**Problem**: Same message quoted in 5 email replies = 5 copies of same content.

**Solution**:
```python
# In dedup_mixin, add mail-specific dedup:
def _find_mail_duplicates(self):
    """Find quoted/forwarded duplicates"""
    # Compare body (ignoring quoted parts)
    clean_body = self._strip_quoted_text(self.body)

    similar = self.search([
        ('id', '!=', self.id),
        ('author_id', '=', self.author_id.id),
    ])

    for msg in similar:
        clean_similar = self._strip_quoted_text(msg.body)
        if similarity(clean_body, clean_similar) > 0.9:
            yield (self, msg)  # Duplicates
```

### 5.4 Privacy & Legal Hold
**Problem**: Some messages must be kept due to legal/compliance requirements.

**Solution**:
```python
class MailMessage(models.Model):
    legal_hold = fields.Boolean(help="Protected from archiving/deletion")
    hold_reason = fields.Char()
    hold_expires = fields.Date()

    def action_place_hold(self, reason, expires=None):
        """Place legal hold"""
        self.write({
            'legal_hold': True,
            'hold_reason': reason,
            'hold_expires': expires,
        })
```

---

## 6. SUMMARY OF PRIORITY CHANGES

| Change | Priority | Effort | Impact |
|--------|----------|--------|--------|
| Transaction/Rollback | CRITICAL | Medium | Prevents data loss |
| Concurrency Control | HIGH | Medium | Prevents duplicates |
| Enhanced Verification | HIGH | Medium | Data integrity |
| Error Classification | HIGH | Low | Recoverability |
| Audit Trail | MEDIUM | Low | Compliance |
| Mixin Clarification | MEDIUM | Low | Extensibility |
| Policy Domain Integration | MEDIUM | Low | Efficiency |
| Mail-specific features | MEDIUM | Medium | Mail archiving |

---

## 7. IMPLEMENTATION ROADMAP

### Phase 1 (Foundation - Critical)
1. Fix transaction management with savepoints
2. Add concurrency control (rule locks)
3. Enhance error handling & classification

### Phase 2 (Data Safety)
1. Implement mail_message_archive with best practices
2. Add audit trail logging
3. Enhanced verification checks

### Phase 3 (Polish)
1. What-if analysis
2. Scheduled downtime protection
3. Incremental processing

---

## 8. RECOMMENDATIONS FOR mail_message_archive MODULE

The mail-specific module should demonstrate:

1. **Concrete mixin usage** - show archive_mixin in action
2. **Policy patterns** - demonstrate intelligent classification
3. **Attachment handling** - show how to handle related records
4. **Thread awareness** - show proper thread handling
5. **Error recovery** - show best practices for mail-specific failures

This will set the pattern for later CRM and helpdesk extensions.

