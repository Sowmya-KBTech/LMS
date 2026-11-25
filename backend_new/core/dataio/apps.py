from django.apps import AppConfig


class DataioConfig(AppConfig):
    """
    Import & Export (core, always on).

    Holds the ONE shared import/export engine. Each part of the app plugs in
    its own "importer" (which columns, how to check a row, how to save it):

        core.dataio.importers.users   -> students, staff      (registered here)
        modules.<name>/...            -> registered from that module's own
                                         AppConfig.ready(), so a module that is
                                         switched off has no import/export
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "core.dataio"
    label = "dataio"
    verbose_name = "Import & Export"

    def ready(self):
        # core importers (users is core, so these always exist)
        from core.dataio.importers import users  # noqa: F401  (registers on import)
        from core.dataio.importers import academics  # noqa: F401  (courses, subjects)
