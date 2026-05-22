# KOMA

KOMA is an AI-assisted bibliographic drafting project for the "상상기업" program.
Its goal is to reduce repetitive cataloging work by generating a draft MARC bibliographic record from book metadata such as title, author, publisher, summary, and table of contents, then letting librarians review and correct the result.

## Project Goal

- Accept structured book information as input.
- Generate a draft MARC record with key fields such as `020`, `100`, `245`, `260`, and `650`.
- Provide a web interface for librarian review and correction.
- Leave room for prompt iteration, retrieval support, and evaluation workflows.

## Repository Structure

```text
koma/
├── docs/        # Project planning and interface contracts
├── frontend/    # Librarian-facing web UI
├── backend/     # API and orchestration layer
├── ai/          # Prompt, RAG, and evaluation assets
└── shared/      # Shared sample data and schema contracts
```

## Planned Workflow

1. A user submits book metadata.
2. The backend prepares a prompt or pipeline input.
3. The AI layer generates a draft MARC JSON record.
4. The frontend presents the draft to a librarian.
5. The librarian reviews, edits, and confirms the final bibliographic record.

## Current Status

This repository is currently scaffolded around project contracts and sample data.
Implementation details for the frontend, backend, and AI pipeline will be added after the contract files in `docs/` and `shared/` are finalized.
