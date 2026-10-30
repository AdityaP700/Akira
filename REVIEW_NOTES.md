# REVIEW_NOTES.md

A handoff log for teammates and reviewers, like a pull-request description for every commit. Append-only, newest first. Write it so Person B can review the change without asking Person A anything.

## Entry format

```markdown
## <commit hash> — <phase id> — <title>
**Author:** <person or agent> · **Sub-agents used:** none | <name: scope → deliverable>
**Summary:** what the change does, in 2–3 sentences.
**Files changed:** list with one line each on why.
**Behaviour before → after:** what an API caller now sees differently.
**How to verify:**
1. command(s) to run
2. request(s) to send (curl or Postman item) and the expected response
**Risks / things to look at closely:** e.g. locking order, rounding, error codes.
**Expected follow-up:** next phase or open question.
**Reviewer checklist:**
- [ ] Tests cover the new paths, including failure paths
- [ ] No float in money paths; no secrets in diff
- [ ] Guardrails respected (list any exceptions approved)
- [ ] README / docs updated where behaviour changed
```

---
