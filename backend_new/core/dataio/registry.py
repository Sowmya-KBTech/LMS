"""
Registry of importers.

An importer registers itself once, when its app loads:

    from core.dataio.registry import register
    register(MyImporter())

Modules register from their own AppConfig.ready(). A module that is switched
off for a college never loads, so its import/export simply doesn't exist.
"""

_IMPORTERS = {}


def register(importer):
    if importer.key in _IMPORTERS:
        raise ValueError(f"Importer '{importer.key}' is registered twice.")
    _IMPORTERS[importer.key] = importer
    return importer


def get(key):
    return _IMPORTERS.get(key)


def available_for(user):
    """Importers this user is allowed to use, in registration order."""
    return [imp for imp in _IMPORTERS.values() if imp.can_use(user)]
