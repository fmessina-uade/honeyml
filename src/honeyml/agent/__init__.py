"""Agentic triage engine.

Consumes normalized events from the bus, builds context, asks an inference service to classify
them, validates the answer against a closed schema and persists the decision.

The structure follows the development view: one module per responsibility, so that the pieces
that carry risk — the schema validation and the provider adapter — are isolated and replaceable.
"""
