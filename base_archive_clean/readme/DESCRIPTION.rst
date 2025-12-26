This module provides a comprehensive framework for intelligent data archiving, extending the `autovacuum_message_attachment` module with cloud backup, deduplication, and model-agnostic retention policies.

**Key Features:**

* **Cloud Backup Integration**: Archive to S3, Google Cloud Storage, BigQuery, or SFTP before deletion
* **Intelligent Deduplication**: Automatically detect and merge duplicate attachments
* **Verify-Then-Delete Protocol**: Never delete local data until cloud backup is verified
* **Model-Agnostic**: Apply retention policies to any Odoo model, not just mail/attachments
* **Classification Policies**: Define sophisticated rules based on record state, age, file type, size
* **Unified Search**: Search both local and archived data from a single interface
* **Easy Restoration**: One-click restore of archived records when needed
* **Extensible Architecture**: Build model-specific archiving strategies

**Why This Module?**

Long-running Odoo instances accumulate massive amounts of data:
- `mail_message` table can reach 50-70% of total database size
- `ir_attachment` duplicates waste storage
- Large databases slow down backups and migrations
- Compliance requires data retention but not immediate access

This module solves these problems by:
1. Identifying old/redundant data using intelligent policies
2. Safely backing up to cloud storage
3. Verifying backup integrity
4. Removing local copies to free space
5. Maintaining searchability and restoration capabilities

**Benefits:**

* Reduce database size by 50-70% in typical installations
* Improve backup times by 60%+
* Maintain full audit trail and compliance
* Keep data accessible when needed
* Lower infrastructure costs
