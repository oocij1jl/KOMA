# KOMA

KOMA는 AI기반 서지데이서 생성보조 서비스 입니다.

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

