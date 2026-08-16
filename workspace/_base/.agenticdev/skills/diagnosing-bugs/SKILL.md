---
name: diagnosing-bugs
description: Use for defects, regressions, crashes, wrong output, or unexplained slowness.
---
# Diagnosing bugs

1. Define one fast, deterministic command that reproduces the exact symptom. Redact secrets.
2. Minimize the reproducer until every remaining input is necessary.
3. Rank falsifiable hypotheses; test one variable at a time with tagged temporary instrumentation.
4. Add a regression test at the public seam, make it fail, apply the smallest fix, then rerun the original reproducer.
5. Remove instrumentation and unrelated edits. Report the confirmed cause and verification.
