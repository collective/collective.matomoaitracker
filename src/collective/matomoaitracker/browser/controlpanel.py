from collective.matomoaitracker import _
from collective.matomoaitracker.interfaces import IMatomoAITrackingControlPanel
from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm
from plone.z3cform import layout


class MatomoAITrackingControlPanelForm(RegistryEditForm):
    """Edit Matomo AI Tracking settings."""

    schema = IMatomoAITrackingControlPanel
    schema_prefix = "matomoaitracker"
    label = _("Matomo Settings")


MatomoAITrackingControlPanelView = layout.wrap_form(
    MatomoAITrackingControlPanelForm,
    ControlPanelFormWrapper,
)
