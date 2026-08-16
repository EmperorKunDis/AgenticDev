---
name: codebase-design
description: Use when choosing module interfaces, adapters, seams, or architecture changes.
---
# Codebase design

Design deep modules: a small interface hiding substantial behavior. Put tests and callers at the same stable seam. Accept dependencies, return explicit results, document invariants and error modes, and introduce an adapter only when behavior genuinely varies. Prefer locality: one conceptual change should concentrate in one module instead of causing shotgun edits.
