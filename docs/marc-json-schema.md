# MARC JSON Shape

## Purpose

This document defines the project-owned JSON representation for a draft MARC bibliographic record used by KOMA.

## Top-Level Structure

```json
{
  "leader": "string",
  "fields": []
}
```

## Field Representation

Each entry in `fields` is represented as one of the following:

### Control Field

```json
{
  "tag": "001",
  "value": "000000001"
}
```

### Data Field

```json
{
  "tag": "245",
  "ind1": "1",
  "ind2": "0",
  "subfields": [
    { "code": "a", "value": "Main title :" },
    { "code": "b", "value": "subtitle /" },
    { "code": "c", "value": "author." }
  ]
}
```

## Starter Tags for v0

- `020` - ISBN
- `100` - Main entry personal name
- `245` - Title statement
- `260` - Publication information
- `650` - Topical subject access

Optional tags may be added later as the drafting pipeline matures.

## Design Notes

- This is a simplified project contract, not a full MARC21 exchange format.
- The AI output should be easy to validate and easy for the frontend to render.
- Repeated fields such as `650` are represented as separate entries in the `fields` array.
