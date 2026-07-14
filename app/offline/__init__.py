"""Offline asset-building layer.

Offline:   Raw Word/Excel/YAML → generated assets → schema indexes → ChromaDB
Online:    User question → Pipeline (retrieval → SchemaGraph → CoT → SQL → gate)

The online Pipeline never directly parses raw Word/Excel documents.
"""
