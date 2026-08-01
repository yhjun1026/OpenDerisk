"""ECP (Enterprise Context Protocol) serve module.

Hard semantic layer for OpenDerisk: versioned, confirmation-gated semantic
objects (entity/metric/relation/dimension) with a resolution cache, a
materialized edge projection, a confirmer list and an append-only op log.

Design: docs/ECP.md + docs/ECP-implementation-design.md
"""
