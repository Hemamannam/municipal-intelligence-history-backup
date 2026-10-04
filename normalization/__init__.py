"""Normalization layer: raw JSON payloads → typed, standardized clean.* tables.

Sits between raw ingestion and dbt. Lives in Python (not SQL) because the
address/name normalizers depend on usaddress + rule dictionaries that have
no SQL equivalent — and because pytest can exercise them directly.
"""
