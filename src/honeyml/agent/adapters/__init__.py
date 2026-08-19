"""Adapters to external services, kept behind an interface so the provider can be swapped.

The project already had to replace an inference provider once, mid-development. That is the
reason this package exists as a boundary instead of the engine calling a vendor SDK directly.
"""
