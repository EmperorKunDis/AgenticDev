---
name: tdd
description: Use for behavior changes that can be specified at a stable public seam.
---
# Test-driven development

Agree on the observable seam. Work in vertical slices: one behavior test, observe red, implement only enough for green, repeat. Expected values must come from the specification rather than duplicating implementation logic. Prefer integration boundaries over private-method mocks. Refactor only after behavior is green and keep unrelated cleanup out of the diff.
