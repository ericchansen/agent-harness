"""Deterministic mock provider used by ``--mock`` and tests."""

from .dispatcher import mock_response

__all__ = ["mock_response"]
