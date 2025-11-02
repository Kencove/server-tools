import logging

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class ServerActions(models.Model):

    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[
            ("notify", "Notification"),
        ],
        ondelete={
            "notify": "cascade",
        },
    )
    notify_method = fields.Selection(
        selection=[
            ("notify", "Notification"),
            ("notify_email", "Notification & Email"),
            ("notify_comment", "Notification & Post as Message"),
            ("notify_note", "Notification & Post as Note"),
        ],
        string="Send as",
        compute="_compute_notify_method",
        readonly=False,
        store=True,
        help="""
        Choose method for notification sending:\n
        Notification: show a popup notification\n
        Notification & Email: notify and send directly emails\n
        Notification & Post as Message: notify and post on document and notify followers\n
        Notification & Post as Note: notify and log a note on document""",
    )
    notify_partner_ids = fields.Many2many(
        "res.partner",
        "ir_actions_server_notify_partner_rel",
        "server_action_id",
        "partner_id",
        string="Add Followers",
        compute="_compute_notify_partner_ids",
        readonly=False,
        store=True,
        help="If you select a mail template, only template receipants will be notified.",
    )

    @api.depends("state")
    def _compute_notify_method(self):
        to_reset = self.filtered(lambda act: act.state != "notify")
        if to_reset:
            to_reset.notify_method = False
        other = self - to_reset
        if other:
            other.notify_method = "notify"

    @api.depends("state")
    def _compute_notify_partner_ids(self):
        to_reset = self.filtered(lambda act: act.state != "followers")
        if to_reset:
            to_reset.notify_partner_ids = False

    def _run_action_followers_multi(self, eval_context=None):
        Model = self.env[self.model_name]
        if self.partner_ids and hasattr(Model, "message_subscribe"):
            records = Model.browse(
                self._context.get("active_ids", self._context.get("active_id"))
            )
            records.message_subscribe(partner_ids=self.partner_ids.ids)
        return False

    @api.model
    def _get_eval_context(self, action=None):
        if not self:
            return {}
        action = action or self
        eval_context = super()._get_eval_context(action=action)
        eval_context["message"] = False
        eval_context["partners"] = False
        return eval_context

    def _get_notification_message(self, records):
        self.ensure_one()
        record_ids_str = ", ".join(map(str, records.ids))
        message = _("Event: for model: %(model)s (IDs: %(ids)s) was triggered") % {
            "model": records._description,
            "ids": record_ids_str,
        }
        return message

    def _get_dynamic_message_and_partners(self, records):
        """Safely execute user-defined Python code to compute message and recipients."""
        self.ensure_one()
        message = self._get_notification_message(records)
        partners = self.notify_partner_ids
        localdict = self._get_eval_context()
        if self.code:
            try:
                safe_eval(self.code, localdict, mode="exec", nocopy=True)
                message = localdict.get("message") or message
                partners = localdict.get("partners") or partners
            except Exception as e:
                _logger.warning(
                    f"Error evaluating Python code in rule '{self.name}': {e}"
                )
        return message, partners

    @api.model
    def notify_changes(self, partner_ids, message):
        """Send notification to partner_ids."""
        channel = "base_notification_updates"
        for partner_id in partner_ids:
            self.env["bus.bus"]._sendone(
                partner_id,
                channel,
                {
                    "message": message,
                },
            )

    def _execute_notification(self, records):
        """Send the configured notification."""
        message, partner_ids = self._get_dynamic_message_and_partners(records)
        if self.notify_method == "notify":
            self.notify_changes(partner_ids, message)

    def _run_action_notify_multi(self, eval_context=None):
        Model = self.env[self.model_name]
        records = Model.browse(
            self._context.get("active_ids", self._context.get("active_id"))
        )
        if self.notify_method and records:
            self._execute_notification(records)
        return False


class BaseAutomation(models.Model):
    _inherit = "base.automation"
