from collective.matomoaitracker import _
from collective.matomoaitracker.browser.tracking import load_settings
from collective.matomoaitracker.browser.tracking import registry_record
from collective.matomoaitracker.browser.tracking import token_auth_setting
from collective.matomoaitracker.connection import check_connection
from collective.matomoaitracker.interfaces import IMatomoAITrackingControlPanel
from collective.matomoaitracker.status import STATUS
from plone import api
from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm
from plone.z3cform import layout
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from z3c.form import button
from z3c.form.browser.checkbox import CheckBoxFieldWidget


class MatomoAITrackingControlPanelForm(RegistryEditForm):
    """Edit Matomo AI Tracking settings."""

    schema = IMatomoAITrackingControlPanel  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
    schema_prefix = "matomoaitracker"
    label = _("Matomo Settings")

    buttons = RegistryEditForm.buttons.copy()
    handlers = RegistryEditForm.handlers.copy()  # pyright: ignore[reportAttributeAccessIssue]

    def updateFields(self):
        super().updateFields()
        self.fields["matomo_bot_site_categories"].widgetFactory = CheckBoxFieldWidget

    def updateWidgets(self, prefix=None):
        super().updateWidgets(prefix)
        # Never send the stored token to the browser, say what there is.
        token, from_environment = token_auth_setting()
        widget = self.widgets["matomo_token_auth"]  # pyright: ignore[reportOptionalSubscript]
        widget.value = ""
        if from_environment:
            widget.placeholder = _(
                "Set by the MATOMO_AI_TOKEN_AUTH environment variable"
            )
        elif token:
            widget.placeholder = _("A token is stored")
        else:
            widget.placeholder = _("No token stored")

    def applyChanges(self, data):
        if not data.get("matomo_token_auth"):
            # Saving the form with an empty token field keeps the stored one.
            data["matomo_token_auth"] = registry_record("matomo_token_auth") or ""
        return super().applyChanges(data)

    @button.buttonAndHandler(_("Test connection"), name="test_connection")
    def handle_test_connection(self, action):
        """Check the saved settings against Matomo."""
        settings, problem = load_settings()
        if settings is None:
            api.portal.show_message(problem, self.request, type="error")
            return
        for ok, message in check_connection(settings):
            api.portal.show_message(
                message, self.request, type="info" if ok else "error"
            )

    @button.buttonAndHandler(
        _("Remove token"),
        name="remove_token",
        condition=lambda form: bool(registry_record("matomo_token_auth")),
    )
    def handle_remove_token(self, action):
        api.portal.set_registry_record("matomoaitracker.matomo_token_auth", "")
        api.portal.show_message(_("The Matomo token is removed."), self.request)
        self.request.response.redirect(self.request["ACTUAL_URL"])


class MatomoAITrackingControlPanelFormWrapper(ControlPanelFormWrapper):
    """The control panel, with the tracking status above the form."""

    status_template = ViewPageTemplateFile("templates/tracking_status.pt")

    def update(self):
        super().update()
        self.contents = self.status_template() + self.contents

    def status(self):
        """The tracking status, with times as ISO 8601 for pat-display-time."""
        return {
            "started": iso(STATUS.started),
            "last_batch": iso(STATUS.last_batch),
            "batches": STATUS.batches,
            "tracked": STATUS.tracked,
            "rejected": STATUS.rejected,
            "skipped": STATUS.skipped,
            "last_error": STATUS.last_error,
            "last_error_time": iso(STATUS.last_error_time),
        }


def iso(moment):
    return moment.isoformat() if moment else None


MatomoAITrackingControlPanelView = layout.wrap_form(
    MatomoAITrackingControlPanelForm,
    MatomoAITrackingControlPanelFormWrapper,
)
