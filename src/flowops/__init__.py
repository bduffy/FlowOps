"""FlowOps — the governed actuation layer.

Scaffold. Core domain (models, actuators, gates, jobs, audit, services) is pure
stdlib so the governed-actuation loop runs with no third-party deps, no database,
and no cloud — the dev (local) execution profile. Persistence (Postgres) and the
FastAPI/React adapters are layered on top (issues #3, #5, #6).
"""

__version__ = "0.0.0"
