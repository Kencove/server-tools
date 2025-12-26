# Archive Clean - Integration Guide

## Overview

This guide explains how to extend Archive Clean to other modules (CRM, Helpdesk, etc.) using the proven mail_message_archive pattern.

## Architecture Pattern

Archive extensions follow a consistent pattern:

```
┌─────────────────────────────────────────┐
│     Your Archive Extension Module       │
├─────────────────────────────────────────┤
│ models/                                 │
│  ├── your_rule.py (extends rule mixin)  │
│  ├── your_job.py (extends job mixin)    │
│  └── your_model.py (extended model)     │
│ views/                                  │
│  ├── your_rule_views.xml                │
│  ├── your_job_views.xml                 │
│  └── wizards/                           │
│ data/                                   │
│  ├── ir_cron.xml (scheduling)           │
│  ├── ir_model_access.xml (security)     │
│  └── demo/                              │
│ __manifest__.py                         │
│ README.md                               │
└─────────────────────────────────────────┘
```

## Step-by-Step Extension Guide

### Step 1: Create Module Structure

```bash
mkdir -p crm_archive
cd crm_archive

# Create subdirectories
mkdir -p models views wizards data/demo security
touch __init__.py
touch models/__init__.py
touch __manifest__.py
```

### Step 2: Create __manifest__.py

```python
# crm_archive/__manifest__.py

{
    "name": "CRM Archive",
    "version": "16.0.1.0.0",
    "category": "CRM",
    "license": "AGPL-3",
    "author": "Your Company",
    "summary": "Archive old CRM records (leads, opportunities, calls)",
    "depends": [
        "base_archive_clean",
        "crm",
        "mail",  # For CRM mail integration
    ],
    "data": [
        "security/ir_model_access.xml",
        "views/crm_lead_archive_rule_views.xml",
        "views/crm_phonecall_archive_rule_views.xml",
        "views/crm_archive_job_views.xml",
        "views/crm_archive_menus.xml",
        "data/crm_archive_cron.xml",
        "data/demo/crm_archive_demo.xml",
    ],
    "demo": [
        "data/demo/crm_archive_demo.xml",
    ],
    "external_dependencies": {
        "python": [],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
```

### Step 3: Create Archive Rule Models

```python
# crm_archive/models/crm_lead_archive_rule.py

from odoo import api, fields, models

class CrmLeadArchiveRule(models.Model):
    _name = "crm.lead.archive.rule"
    _inherit = ["archive.rule.mixin"]
    _description = "CRM Lead Archiving Rule"

    # CRM-specific fields
    archive_closed_leads = fields.Boolean(
        default=True,
        help="Archive leads in closed stages"
    )
    archive_lost_opportunities = fields.Boolean(
        default=True,
        help="Archive opportunities marked as lost"
    )
    archive_won_opportunities = fields.Boolean(
        default=False,
        help="Archive won opportunities"
    )

    # Stage filtering
    exclude_stage_ids = fields.Many2many(
        "crm.stage",
        string="Exclude Stages",
        help="Don't archive leads in these stages"
    )

    # User filtering
    exclude_user_ids = fields.Many2many(
        "res.users",
        string="Exclude Users",
        help="Don't archive leads owned by these users"
    )

    # Keep metadata
    keep_activity_records = fields.Boolean(
        default=True,
        help="Keep activity/mail records, archive lead only"
    )

    @api.depends("older_than_days", "archive_closed_leads", "archive_lost_opportunities")
    def _compute_name(self):
        """Auto-generate rule name"""
        for record in self:
            parts = []
            if record.archive_closed_leads:
                parts.append("closed")
            if record.archive_lost_opportunities:
                parts.append("lost opps")
            if record.older_than_days:
                parts.append(f">{record.older_than_days}d")

            record.name = " + ".join(parts) or "CRM Archive Rule"

    def _get_domain(self):
        """Build domain for records to archive"""
        domain = super()._get_domain()

        # Base domain: CRM leads
        domain += [("type", "in", ["lead", "opportunity"])]

        # Closed leads
        if self.archive_closed_leads:
            domain += [("active", "=", False)]  # Closed leads are inactive

        # Lost opportunities
        if self.archive_lost_opportunities:
            domain += [("probability", "=", 0)]

        # Exclude specific stages
        if self.exclude_stage_ids:
            domain += [("stage_id", "not in", self.exclude_stage_ids.ids)]

        # Exclude specific users
        if self.exclude_user_ids:
            domain += [("user_id", "not in", self.exclude_user_ids.ids)]

        return domain

    def action_simulate_archive(self):
        """Preview what would be archived"""
        self.ensure_one()
        domain = self._get_domain()
        records = self.env["crm.lead"].search(domain)

        # Show stats
        closed_leads = len(records.filtered(lambda r: r.type == "lead"))
        lost_opps = len(records.filtered(lambda r: r.type == "opportunity"))

        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "kanban,form",
            "domain": domain,
            "context": {
                "default_archive_preview": True,
            },
            "name": f"Preview: {closed_leads} leads + {lost_opps} opps",
        }
```

### Step 4: Create Archive Job Model

```python
# crm_archive/models/crm_archive_job.py

from odoo import api, fields, models
from datetime import datetime

class CrmArchiveJob(models.Model):
    _name = "crm.archive.job"
    _inherit = ["archive.job.mixin"]
    _description = "CRM Archiving Job"

    # Link to rule
    rule_id = fields.Many2one(
        "crm.lead.archive.rule",
        string="Archiving Rule",
        required=True,
    )

    # Statistics
    leads_archived = fields.Integer(default=0)
    opportunities_archived = fields.Integer(default=0)
    activities_kept = fields.Integer(default=0)

    # Performance
    avg_compress_ratio = fields.Float(
        default=0.0,
        help="Average compression ratio for CRM records"
    )

    @api.model
    def _create_recurring_jobs(self):
        """Create jobs for active auto-archive rules"""
        rules = self.env["crm.lead.archive.rule"].search([
            ("is_active", "=", True),
            ("auto_archive", "=", True),
        ])

        for rule in rules:
            # Check if job already running
            running_job = self.search([
                ("rule_id", "=", rule.id),
                ("state", "in", ["draft", "running"]),
            ])

            if not running_job:
                # Create new job
                job = self.create({
                    "rule_id": rule.id,
                    "backend_id": rule.backend_id.id,
                    "name": f"CRM Archive: {rule.name}",
                })
                job.action_execute()

    def action_execute(self):
        """Execute the archiving job"""
        self.ensure_one()

        try:
            # Get records to archive
            domain = self.rule_id._get_domain()
            records = self.env["crm.lead"].search(domain)

            self.total_messages = len(records)
            self.state = "running"
            self.started_at = datetime.now()

            # Process in batches
            batch_size = 100
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                self._archive_batch(batch)

            self.state = "done"
            self.completed_at = datetime.now()

        except Exception as e:
            self.state = "error"
            self.error_message = str(e)

    def _archive_batch(self, records):
        """Archive a batch of CRM records"""
        for record in records:
            try:
                # Store CRM-specific data
                archive_data = {
                    "id": record.id,
                    "name": record.name,
                    "type": record.type,
                    "stage_id": record.stage_id.name,
                    "probability": record.probability,
                    "expected_revenue": record.expected_revenue,
                    "contact_name": record.contact_name,
                    "email_from": record.email_from,
                    "phone": record.phone,
                    "mobile": record.mobile,
                    "partner_id": record.partner_id.id if record.partner_id else None,
                    "user_id": record.user_id.id,
                    "create_date": record.create_date.isoformat(),
                    "write_date": record.write_date.isoformat(),
                }

                # Archive to backend
                reference = self.rule_id.backend_id.archive_record(
                    archive_data,
                    model="crm.lead",
                    record_id=record.id,
                    rule_id=self.rule_id.id,
                )

                # Mark as archived
                record.write({
                    "archive_state": "archived",
                    "archive_backend_id": self.rule_id.backend_id.id,
                    "archive_reference": reference,
                    "archive_timestamp": datetime.now(),
                })

                if record.type == "lead":
                    self.leads_archived += 1
                else:
                    self.opportunities_archived += 1
                self.archived_count += 1

            except Exception as e:
                self.failed_count += 1
                self.env["archive.error.log"].create({
                    "job_id": self.id,
                    "record_id": record.id,
                    "model": "crm.lead",
                    "error_message": str(e),
                })
```

### Step 5: Extend Original Model

```python
# crm_archive/models/crm_lead.py

from odoo import fields, models

class CrmLead(models.Model):
    _inherit = "crm.lead"

    # Archive fields
    archive_state = fields.Selection(
        [("active", "Active"), ("archived", "Archived"), ("restored", "Restored")],
        default="active",
    )
    archive_backend_id = fields.Many2one(
        "archive.backend",
        string="Archived To",
    )
    archive_reference = fields.Char(
        string="Archive Reference",
        help="Backend reference for restore",
    )
    archive_timestamp = fields.Datetime(
        string="Archived At",
    )

    def action_restore(self):
        """Restore from archive"""
        self.ensure_one()

        if self.archive_state != "archived":
            raise Warning("Record not archived")

        # Restore from backend
        archive_data = self.archive_backend_id.restore_record(
            self.archive_reference,
            model="crm.lead",
        )

        # Update record
        self.write({
            "archive_state": "restored",
            "archive_timestamp": None,  # Clear archive timestamp
        })
```

### Step 6: Create Views

```xml
<!-- crm_archive/views/crm_lead_archive_rule_views.xml -->

<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Form View -->
    <record id="crm_lead_archive_rule_form" model="ir.ui.view">
        <field name="name">crm.lead.archive.rule.form</field>
        <field name="model">crm.lead.archive.rule</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_simulate_archive" type="object"
                            string="Simulate" class="oe_highlight"/>
                    <button name="action_dry_run" type="object"
                            string="Dry-Run" class="oe_highlight"/>
                </header>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="is_active"/>
                        <field name="older_than_days"/>
                        <field name="backend_id" required="1"/>
                    </group>
                    <group>
                        <field name="archive_closed_leads"/>
                        <field name="archive_lost_opportunities"/>
                        <field name="archive_won_opportunities"/>
                        <field name="keep_activity_records"/>
                    </group>
                    <group>
                        <field name="exclude_stage_ids" widget="many2many_tags"/>
                        <field name="exclude_user_ids" widget="many2many_tags"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <!-- Tree View -->
    <record id="crm_lead_archive_rule_tree" model="ir.ui.view">
        <field name="name">crm.lead.archive.rule.tree</field>
        <field name="model">crm.lead.archive.rule</field>
        <field name="arch" type="xml">
            <tree>
                <field name="name"/>
                <field name="is_active" widget="boolean"/>
                <field name="older_than_days"/>
                <field name="backend_id"/>
            </tree>
        </field>
    </record>

    <!-- Action -->
    <record id="crm_lead_archive_rule_action" model="ir.actions.act_window">
        <field name="name">Lead Archiving Rules</field>
        <field name="res_model">crm.lead.archive.rule</field>
        <field name="view_mode">tree,form</field>
    </record>

</odoo>
```

### Step 7: Create Security Rules

```xml
<!-- crm_archive/security/ir_model_access.xml -->

<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Archive Manager Group -->
    <record id="group_crm_archive_manager" model="res.groups">
        <field name="name">CRM Archive Manager</field>
        <field name="category_id" ref="base.module_category_hidden"/>
        <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
    </record>

    <!-- Model Access -->
    <record id="crm_lead_archive_rule_access" model="ir.model.access">
        <field name="name">CRM Lead Archive Rule</field>
        <field name="model_id" ref="model_crm_lead_archive_rule"/>
        <field name="group_id" ref="group_crm_archive_manager"/>
        <field name="perm_read">1</field>
        <field name="perm_write">1</field>
        <field name="perm_create">1</field>
        <field name="perm_unlink">1</field>
    </record>

</odoo>
```

### Step 8: Create Cron Jobs

```xml
<!-- crm_archive/data/crm_archive_cron.xml -->

<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="crm_archive_cron_job" model="ir.cron">
        <field name="name">CRM Archive - Create Recurring Jobs</field>
        <field name="model_id" ref="model_crm_archive_job"/>
        <field name="state">code</field>
        <field name="code">model._create_recurring_jobs()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="nextcall">2025-01-01 02:00:00</field>
        <field name="numbercall">-1</field>
        <field name="active">True</field>
    </record>

</odoo>
```

## Testing Extension

### Create Demo Data

```xml
<!-- crm_archive/data/demo/crm_archive_demo.xml -->

<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Demo Rule -->
    <record id="demo_rule_old_leads" model="crm.lead.archive.rule">
        <field name="name">Archive Old Closed Leads</field>
        <field name="is_active">True</field>
        <field name="older_than_days">730</field>  <!-- 2 years -->
        <field name="archive_closed_leads">True</field>
        <field name="backend_id" ref="base_archive_clean.demo_backend_s3"/>
    </record>

</odoo>
```

### Test Cases

```python
# tests/test_crm_archive.py

from odoo.tests.common import TransactionCase

class TestCrmArchive(TransactionCase):

    def setUp(self):
        super().setUp()
        self.rule_model = self.env["crm.lead.archive.rule"]
        self.job_model = self.env["crm.archive.job"]
        self.lead_model = self.env["crm.lead"]

    def test_archive_closed_leads(self):
        """Test archiving closed leads"""
        # Create old closed lead
        lead = self.lead_model.create({
            "name": "Old Closed Lead",
            "type": "lead",
            "active": False,
        })

        # Create archive rule
        rule = self.rule_model.create({
            "name": "Test Rule",
            "older_than_days": 0,
            "archive_closed_leads": True,
        })

        # Execute
        job = self.job_model.create({
            "rule_id": rule.id,
            "backend_id": rule.backend_id.id,
        })
        job.action_execute()

        # Assert
        self.assertEqual(lead.archive_state, "archived")
        self.assertIsNotNone(lead.archive_reference)
```

## Next Steps

1. **Install and Test**: Install crm_archive in your Odoo instance
2. **Configure Rules**: Create archiving rules matching your CRM policies
3. **Run Dry-Runs**: Simulate archiving before execution
4. **Monitor Jobs**: Watch archive job progress in real-time
5. **Extend Further**: Apply same pattern to helpdesk, accounting, etc.

## Common Patterns

### Pattern 1: Time-Based Archiving
Archive records older than X days

```python
def _get_domain(self):
    domain = super()._get_domain()
    domain += [("create_date", "<", self.cutoff_date)]
    return domain
```

### Pattern 2: Status-Based Archiving
Archive records in specific statuses

```python
def _get_domain(self):
    domain = super()._get_domain()
    domain += [("state", "in", ["done", "cancelled"])]
    return domain
```

### Pattern 3: Custom Filtering
Archive based on custom logic

```python
def _get_domain(self):
    domain = super()._get_domain()
    if self.exclude_important:
        domain += [("priority", "!=", "high")]
    return domain
```

## Resources

- **Base Framework**: base_archive_clean/__doc__.md
- **Mail Implementation**: mail_message_archive/README.md
- **API Reference**: archive_backend.py docstrings
- **Architecture**: ARCHITECTURE.md

---

**Ready to extend Archive Clean to your module? Follow the steps above!**
