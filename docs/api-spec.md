# API Specification

## Overview

The first backend contract is a single endpoint that accepts structured book metadata and returns a draft MARC record.

## Endpoint

### `POST /drafts`

Generates a draft MARC JSON record from normalized book metadata.

## Request Body

```json
{
  "title": "string",
  "subtitle": "string",
  "author": "string",
  "isbn": "string",
  "publisher": "string",
  "publicationYear": 2025,
  "physicalDescription": "string",
  "summary": "string",
  "tableOfContents": ["string"],
  "subjects": ["string"]
}
```

## Success Response

### `200 OK`

```json
{
  "record": {
    "leader": "string",
    "fields": []
  }
}
```

The `record` object should conform to `shared/marc-schema.json`.

## Error Responses

### `400 Bad Request`

- Missing required metadata such as `title`.
- Invalid field types.

### `422 Unprocessable Entity`

- Input is structurally valid but insufficient to generate a meaningful draft.

### `500 Internal Server Error`

- Unexpected model, parsing, or orchestration failure.

## v0 Rules

- The service returns a draft, not a final authoritative record.
- Librarian review is always required.
- MARC fields may be partial in early versions if the source metadata is incomplete.
