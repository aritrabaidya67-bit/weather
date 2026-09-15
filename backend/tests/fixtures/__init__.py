"""Test-only fixtures.

The deterministic environmental model lives here so the whole ingestion ->
risk -> anomaly -> prediction pipeline can be exercised end to end without any
simulation code existing in the production application.
"""
