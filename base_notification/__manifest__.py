# __manifest__.py
{
    "name": "Base Notification Method",
    "summary": "Generic notifications on create/write/delete or method call",
    "version": "16.0.1.0.0",
    "author": "Kencove, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/server-tools",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "base_automation",
    ],
    "data": [
        "views/base_automation_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "base_notification/static/src/js/base_notification_service.esm.js",
        ],
    },
    "installable": True,
    "application": True,
}
