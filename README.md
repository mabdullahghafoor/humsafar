# Humsafar

Bi-directional remote intervention and care coordination system for vulnerable individuals (elderly, chronically ill, physically disabled, dementia patients).

**Final Year Project — BSSE**
**Supervisor:** S.M. Khalid Jamal

| Member | Role |
|---|---|
| Muhammad Abdullah Ghafoor | Team Lead — Backend, Database, API, BLE Integration, Architecture |
| Muhammad Talha Khan | Flutter Frontend, API Integration, State Management, FCM |
| Syed Sarim Jawad Zaidi | UI/UX, Documentation, Diagrams, Testing |

---

## Tech Stack

- **Backend:** FastAPI, PostgreSQL, SQLAlchemy, Alembic, JWT
- **Frontend:** Flutter (Android-only), Riverpod
- **API testing:** Postman
- **Deployment:** Render (backend)
- **Docs:** SRS v1.0, SDS v1.0, Master Development Roadmap (see `/docs/reference`)

---

## Repository Structure

```
humsafar/
├── backend/        # FastAPI application
├── frontend/        # Flutter application
├── docs/            # all documentation, organized in subfolders (see docs/README.md)
│   ├── api/         #   API contracts (Abdullah)
│   ├── backend/     #   progress, SDS clarifications, running guide (Abdullah)
│   ├── reference/   #   SRS, SDS, Reference Guide, Roadmap, handbooks (Sarim)
│   ├── design/      #   screen designs (Sarim)
│   ├── qa/          #   QA checklists and results (Sarim)
│   ├── diagrams/    #   architecture/workflow diagrams (Sarim)
│   └── reports/     #   final documents and presentation (Sarim)
└── .github/         # PR template, CODEOWNERS
```

**Docs rule:** no file goes directly in `docs/`; every file belongs in one of its subfolders.

This is a **monorepo**: backend and frontend live together for shared issue tracking, PRs, and easier integration checkpoints (ICPs).

---

## Branching Strategy

- `main` — always deployable. Protected. Only updated via PR from `dev`.
- `dev` — integration branch. All feature branches merge here first.
- `feature/<short-description>` — one branch per task, e.g. `feature/auth-endpoints`, `feature/live-map-screen`.

**Workflow:**
1. Branch off `dev`: `git checkout -b feature/your-task-name dev`
2. Commit + push your branch.
3. Open a PR into `dev`.
4. At each Integration Checkpoint (ICP), `dev` is merged into `main` once the demo-able slice is confirmed working.

---

## Backend Setup (Abdullah)

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in local DB credentials
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health` → should return `200`.

## Frontend Setup (Talha)

```bash
cd frontend
flutter pub get
flutter run
```

---

## Project Documentation

Full documentation (SRS, SDS, Hardware Selection, Master Roadmap, individual handbooks) is maintained in `/docs/reference` (see `docs/README.md` for the full folder map) and in the team's Claude Project Knowledge base as the single source of truth.

---

## Status

🚧 Active development — Phase 0 (Environment Setup)
