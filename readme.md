
# LifeOps

LifeOps is a personal decision-support application designed to help organize tasks around fixed commitments such as university, work, travel time, and other events.

The project is being developed with **IBM Bob**, IBM's agentic AI development tool, used throughout the software development lifecycle for planning, architecture, implementation, testing, debugging, and documentation.

## Problem

Managing work, university, study sessions, deadlines, and personal tasks often requires repeated manual planning.

The main challenge is finding realistic free time without creating conflicts with fixed commitments — especially when some schedules can cross midnight.

## Proposed Solution

LifeOps combines:

- fixed schedule management;
- task management with duration, priority, and deadlines;
- a deterministic availability engine;
- valid time-slot suggestions;
- user confirmation before scheduling.

The project is intentionally being built in two stages:

1. **Deterministic scheduling engine** — handles hard constraints and available time.
2. **AI decision layer** — will later help prioritize and explain recommendations without overriding scheduling rules.

## Stack

- React + TypeScript
- Python + FastAPI
- MySQL
- SQLAlchemy
- Pydantic
- Docker
- pytest
- IBM Bob

## Status

🚧 In development

Current focus: building the deterministic scheduling engine before adding the AI recommendation layer.
