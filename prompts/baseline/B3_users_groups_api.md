# B3 — Users, groups, members API

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md` (E2, E3), `docs/design/PROJECT_PLAN.md` §6, latest `CHANGELOG.md`. Run `git status`.

**Goal:** clean REST resources with consistent errors, pagination and an auth seam for later.

**Endpoints**

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/users` | `{"name"}` | 201 `{"id":"usr_…","name","created_at"}` | 422 |
| GET | `/users?limit=&cursor=` | — | 200 `{"items":[…],"next_cursor"}` | 422 bad cursor |
| POST | `/groups` | `{"name"}` | 201 `{"id":"grp_…","name","created_at"}` | 422 |
| POST | `/groups/{group_id}/members` | `{"user_id":"usr_…"}` | 201 member | 404 group/user, 409 `ALREADY_MEMBER` |
| GET | `/groups/{group_id}/members` | — | 200 list with `joined_at` | 404 |

Rules:
- Request models: `extra="forbid"`, names stripped, 1–100 chars. Separate `UserIn`/`UserOut` etc.
- Pagination: keyset (`created_at, id`) with an opaque base64 cursor; `limit` 1–100, default 20.
- Errors through `AppError` codes: `NOT_FOUND`, `ALREADY_MEMBER`, `VALIDATION_ERROR`.
- `api/deps.py::get_actor()` exists and returns `None` in baseline. Every group route already takes `actor = Depends(get_actor)` so phase A1 only changes the dependency.
- Routers contain no business logic; they call services.

**Tests** (`tests/api/`): happy paths, 404s with unknown public ids, 409 duplicate member, unknown field → 422, name of spaces → 422, pagination returns all items exactly once across pages.

**Acceptance gate:** tests pass; `/docs` shows every endpoint with examples; `docs/API.md` started (table + one curl per endpoint).

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(api): users, groups and membership endpoints`. Do not push.

**References**
- OWASP REST Security cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- Pydantic `extra="forbid"`: https://pydantic.dev/docs/validation/latest/api/pydantic/config/
- FastAPI dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
