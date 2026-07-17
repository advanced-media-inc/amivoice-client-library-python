# Copilot Review Instructions

> **Scope**: This file covers code-review guidance only. Common project rules (project overview,
> directory layout, Do/Don't, commands) live in `AGENTS.md` at the repository root.

When performing a code review, please adhere to the following points.

## Overview

In a review, prioritize correctness, security, reliability, performance, and maintainability.

When performing a code review, **Think in English, output in Japanese.**

## Rules

- Scope: Review PR changes and necessary context; avoid unrelated refactors.
- Focus order: Correctness & security → reliability/error handling → performance → readability/maintainability → consistency/style.
- Evidence-based: Reference files/lines, explain why, propose concrete alternatives.
- Tone: Professional, specific, and actionable; ask when intent is unclear.
- Generated/Vendored files: Sanity-check only (lockfiles, dist/, .min.js, images).
