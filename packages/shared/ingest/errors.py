class IngestConflict(Exception):
    """A bounded machine conflict; never exposes SQL or collector data."""
