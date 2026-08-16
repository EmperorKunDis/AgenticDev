---
name: code-review
description: Use to review a fixed diff against its specification and repository standards.
---
# Code review

Pin the base and head commits. Review two independent axes: repository standards and requested behavior. Cite every finding with file and line, explain concrete impact, and distinguish hard violations from judgment calls. Check auth, data isolation, failure paths, tests, secret exposure, scope creep, and whether deterministic tooling already covers the issue. If no actionable finding exists, say so plainly.
