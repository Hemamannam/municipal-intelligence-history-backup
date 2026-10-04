"""Ingestion layer: fetch raw records from public APIs into the local warehouse.

Design principles:
- Raw records are preserved verbatim (append-only, versioned by Socrata's
  ``:updated_at``). Cleaning happens downstream in staging, never at ingest.
- Every run is recorded in ``meta.ingest_runs``; invalid records land in
  ``meta.rejected_records`` instead of being silently dropped.
- Reruns are idempotent: the same record version is never inserted twice.
"""
