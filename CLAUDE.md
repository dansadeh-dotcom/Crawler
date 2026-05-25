# Crawler — Project Guidelines

## Non-negotiable coding rules

1. Ask, don't assume.
If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements.

2. Simplest solution first.
Always implement the simplest thing that could work. Do not add abstractions or flexibility that weren't explicitly requested.

3. Don't touch unrelated code.
If a file or function is not directly part of the current task, do not modify it, even if you think it could be improved.

4. Flag uncertainty explicitly.
If you are not confident about an approach or technical detail, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.

## Development workflow

Before coding:
- Read CURRENT_APP_STATE.md before every implementation.
- Determine smallest useful improvement
- Consider token/API impact

During coding:
- Build smallest reliable solution
- Reuse existing code paths
- Avoid unnecessary abstractions
- Touch only related systems

After coding:
- Update CURRENT_APP_STATE.md after every implementation.
- Update ERRORS.md if the same approach fails twice.
- Do not summarize broadly in chat; only list files changed, what changed, what was not touched, and next recommended task.

## Crawler rules

Purpose:
Efficiently collect, process and organize information.

Primary goals:
- Reliability
- Speed
- Low token usage
- Low API cost
- Maintainability

Always consider:
- rate limits
- retries
- logging
- duplicate detection
- failure handling
- caching
- memory usage

Prefer:
- modular functions
- incremental processing
- existing libraries
- structured outputs

Do NOT:
- crawl unnecessary pages
- duplicate information
- over-engineer pipelines
- create speculative systems

Optimize for practical usefulness over architecture purity.

## How to update this file

Review existing CLAUDE.md, CURRENT_APP_STATE.md and ERRORS.md.

Do not recreate files. Do not overwrite existing project-specific content.

Update CLAUDE.md by adding new sections near the top, keeping existing project-specific rules underneath.

Also ensure CLAUDE.md says:
- Read CURRENT_APP_STATE.md before every implementation.
- Update CURRENT_APP_STATE.md after every implementation.
- Update ERRORS.md if the same approach fails twice.
- Do not summarize broadly in chat; only list files changed, what changed, what was not touched, and next recommended task.

Merge only. Do not delete existing content.
Stop after updating the markdown files.
