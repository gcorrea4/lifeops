
# LifeOps

LifeOps is an auditable decision-support application for organizing personal tasks around fixed commitments such as university, work, travel time, and other events.

The project is being developed as part of an IBM Bob challenge, using Bob as an agentic development partner throughout the software development lifecycle.

## Project Status

🚧 In development

Current progress:

- ST-1 — Project scaffold ✅
- ST-2 — Database models ✅
- ST-3 — Pydantic schemas ✅
- ST-4 — CRUD routers & application rules 🔄
- ST-5 — Deterministic availability engine ⏳
- Week 2 — AI decision layer ⏳
- Cloud deployment ⏳

## Week 1 Goal

Build a fully functional MVP without AI.

Target flow:

React
→ FastAPI
→ MySQL
→ deterministic availability engine
→ slot suggestions
→ user confirmation

## Tech Stack

### Frontend

- React
- TypeScript
- Vite

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy

### Database

- MySQL 8

### Testing

- pytest

### Infrastructure

- Docker
- Docker Compose

### Planned Deployment

- Vercel
- Azure App Service
- Azure Database for MySQL

## Core Idea

LifeOps separates deterministic scheduling constraints from future AI recommendations.

Hard constraints such as work, university, and unavailable time are handled by deterministic business rules.

AI will later be used only for prioritization and recommendation, while the user remains in control of final scheduling decisions.

## Development Approach

The project is being developed incrementally with IBM Bob using:

- planning sessions;
- architecture review;
- implementation;
- testing;
- debugging;
- refactoring;
- technical documentation.

The final README will include:

- architecture diagrams;
- agent flow;
- auditability design;
- metrics;
- screenshots;
- cloud deployment;
- results and lessons learned.
