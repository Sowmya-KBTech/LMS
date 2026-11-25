from django.apps import AppConfig


class PlacementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.placement'

    def ready(self):
        # 10th/12th marks, drive attendance, offers, round results
        # (shared Import & Export engine in core/dataio)
        from core.dataio.registry import register
        from .importers import (DriveAttendanceImporter, OfferImporter,
                                PriorAcademicsImporter, RoundResultImporter)
        register(PriorAcademicsImporter())
        register(DriveAttendanceImporter())
        register(OfferImporter())
        register(RoundResultImporter())

        # keep the saved eligibility table in step (meeting point 10)
        from .signals import connect
        connect()
