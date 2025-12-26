# Copyright 2025 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Base Archive Clean",
    "version": "16.0.1.0.0",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "website": "https://github.com/OCA/server-tools",
    "category": "Tools",
    "summary": (
        "Base framework for intelligent data archiving "
        "with cloud backup and deduplication"
    ),
    "depends": [
        "base",
        "mail",
        "autovacuum_message_attachment",  # Extends this module
        "storage_backend",  # For S3/SFTP integration
    ],
    "external_dependencies": {
        "python": [
            "google-cloud-bigquery",  # Optional, for BigQuery backend
            "google-auth",  # Optional, for BigQuery backend
        ],
    },
    "data": [
        "data/archive_config.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
