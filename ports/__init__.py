"""Ports — the abstract contracts the application depends on.

Services depend on these Protocols; concrete adapters (Postgres, Redis,
in-memory) depend on them too. Nothing in the core ever imports a driver, so
the dependency arrows all point inward.

Interfaces are deliberately narrow and role-based. A caller that only reads
rounds depends on `RoundReader` and cannot accidentally write one.
"""
