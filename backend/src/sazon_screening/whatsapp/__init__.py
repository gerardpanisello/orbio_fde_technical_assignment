"""The real WhatsApp channel (spec 016): Meta WhatsApp Cloud API.

An adapter around the screening service (ADR 0005): inbound webhook messages become
candidate turns, agent replies become Graph API payloads. The engine and the pipeline
do not know which channel a conversation uses.
"""
