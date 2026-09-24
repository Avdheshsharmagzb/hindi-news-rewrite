# PRD — Hindi Editorial Newsroom Admin CMS & AI Rewriter

## Original Problem Statement
Add an 'Approve for Rewrite' action button on 'Pending_Review' news items in the Admin Dashboard. On click, trigger an AI function to rewrite headline + content into flawless high-standard journalistic Hindi (उच्च पत्रकारिता श्रेणी) — zero errors in matras/spelling/sentence construction, 100% facts preserved, fully reworded to avoid copyright, using a cost-effective LLM. Then change status to 'Rewritten_Pending_Publish'.

## Architecture
- **Frontend**: React (CRA/craco) + Tailwind + shadcn/ui + framer-motion + sonner. Single dashboard page `src/components/NewsDashboard.jsx`.
- **Backend**: FastAPI + Motor (MongoDB). Routes under `/api`.
- **AI**: Gemini 3 Flash (`gemini-3-flash-preview`) via emergentintegrations `LlmChat` + Emergent Universal Key (cost-effective choice).
- **DB**: collection `news`.

## User Personas
- News editor/admin reviewing raw wire/agency copy and publishing polished Hindi articles.

## Core Requirements (static)
- Statuses: Pending_Review → Rewritten_Pending_Publish → Published.
- 'Approve for Rewrite' only on Pending_Review items; AI rewrite preserves facts, rewrites wording, outputs Devanagari.
- Side-by-side original vs rewritten comparison; publish action.

## Implemented (2026-06)
- Backend endpoints: GET /api/stats, GET/POST /api/news (status/category filters), POST /api/news/{id}/rewrite (Gemini Hindi rewrite + status change), POST /api/news/{id}/publish (guarded to rewritten items), DELETE /api/news/{id}.
- Startup seeding: 5 Pending_Review, 1 Rewritten_Pending_Publish, 1 Published (mixed Hindi/English sources).
- Frontend: editorial dark/light dashboard, stats bar, status filter tabs, search, add-news modal, per-card actions, AI rewrite with loading + comparison modal, publish flow.
- No auth (per user choice).
- Verified: backend 100% + frontend 100% (test_reports/iteration_1.json).

## Backlog / Remaining
- P1: Auth (JWT or Emergent Google) for admin dashboard.
- P2: Edit original before rewrite; re-trigger rewrite; archive published; diff highlighting.
- P2: Public published-news view; categories management.

## Next Tasks
- Awaiting user feedback / next feature request.
