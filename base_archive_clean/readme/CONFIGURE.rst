**Prerequisites:**

For S3/SFTP backends:
- `storage_backend` module installed
- Backend configured (see storage_backend documentation)

For BigQuery backend (optional):
- Google Cloud Platform account
- BigQuery API enabled
- Service Account with BigQuery Data Editor role
- Service Account JSON key

**Module Installation:**

1. Install dependencies:
   ```bash
   pip install google-cloud-bigquery google-auth
   ```

2. Install the module from Apps menu

**Initial Configuration:**

**1. Configure Archive Backends**

Go to Settings → Technical → Archive → Backends

- For S3/SFTP: Link to existing `storage.backend` record
- For BigQuery:
  - Set Project ID and Dataset name
  - Upload Service Account JSON key (stored encrypted)
- For Local (testing): Set local directory path

**2. Create Archive Policies**

Go to Settings → Technical → Archive → Policies

Example policy for old sale orders:
- Name: "Old Sales - Minimal Retention"
- Min Age: 1095 days (3 years)
- Record State Domain: `[('state', 'in', ['done', 'cancel'])]`
- Max File Versions: 1 (keep only latest PDF)
- Preferred MIME Types: `application/pdf`

**3. Define Archive Rules**

Go to Settings → Technical → Archive → Rules

Example rule using above policy:
- Name: "Archive Old Sale Order Attachments"
- Models: `sale.order`
- Policy: "Old Sales - Minimal Retention"
- Action: "Archive to Cloud"
- Backend: Your S3 backend
- Retention Time: 1095 days
- Verify Before Delete: Yes
- Enable Deduplication: Yes

**4. Schedule Automated Archiving**

The module includes cron jobs:
- "Archive Old Records" (weekly by default)
- "Deduplicate Attachments" (daily by default)

Configure frequency in Settings → Technical → Automation → Scheduled Actions
