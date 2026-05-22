# Sprint 0 Plan

## Goal

Define the initial project contracts for KOMA so that frontend, backend, and AI implementation can begin from a shared understanding of inputs and outputs.

## Scope

1. Finalize the minimal book metadata input shape.
2. Finalize the minimal MARC draft output shape.
3. Document the first draft-generation API.
4. Prepare example fixtures for development and testing.

## Deliverables

- `docs/api-spec.md`
- `docs/marc-json-schema.md`
- `shared/sample-book.json`
- `shared/marc-schema.json`
- `shared/sample-marc-result.json`

## Acceptance Criteria

- The sample input is sufficient to generate a basic MARC draft.
- The sample output includes a title field (`245`) and at least one access point field.
- The output shape is documented in both human-readable and machine-readable forms.
- Future implementation work can use the sample files as baseline fixtures.

## Notes

This sprint is contract-first. Framework-specific implementation choices are intentionally deferred.
