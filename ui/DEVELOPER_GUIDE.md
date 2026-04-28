# Temporal Research UI - Developer Integration Guide

## Authentication

All `/api/*` endpoints (except `/api/health`) require a Firebase ID token in the `Authorization: Bearer <token>` header. The frontend's `api-client.js` injects this automatically (token sourced from `auth.js`) once the user has signed in via Google. Tokens whose email is not verified or doesn't end in `@temporal.io` are rejected with `401`/`403`.

For local dev, set `AUTH_DISABLED=true` in `.env` to bypass verification entirely. The backend logs the active auth mode at startup (look for `[auth]` lines).

## API Contract

The frontend expects these exact response shapes:

### POST /api/start-research

**Request:**

```json
{
  "query": "User's research question"
}
```

**Response:**

```json
{
  "workflow_id": "interactive-research-abc123",
  "status": "started"
}
```

### GET /api/status/{workflow_id}

**Response (awaiting clarifications):**

```json
{
  "workflow_id": "interactive-research-abc123",
  "status": "awaiting_clarifications",
  "current_question": "What aspects interest you most?",
  "current_question_index": 0,
  "total_questions": 3
}
```

**Response (researching):**

```json
{
  "workflow_id": "interactive-research-abc123",
  "status": "researching"
}
```

**Response (complete):**

```json
{
  "workflow_id": "interactive-research-abc123",
  "status": "complete"
}
```

### POST /api/answer/{workflow_id}

**Request:**

```json
{
  "answer": "User's answer to clarification"
}
```

**Response:**

```json
{
  "status": "accepted",
  "workflow_status": "awaiting_clarifications",
  "questions_remaining": 2
}
```

### GET /api/result/{workflow_id}

**Response:**

```json
{
  "workflow_id": "interactive-research-abc123",
  "markdown_report": "# Research Report\n\n## Summary\n...",
  "short_summary": "Brief summary of findings",
  "follow_up_questions": [
    "Would you like more detail on X?",
    "Should we explore Y?"
  ]
}
```

## Workflow Status Values

The frontend handles these status values:

| Status                    | Frontend Behavior                         |
| ------------------------- | ----------------------------------------- |
| `awaiting_clarifications` | Shows `current_question` as bot message   |
| `researching`             | Shows spinner with "Researching..."       |
| `complete`                | Fetches result, redirects to success.html |

## Frontend Files

| File            | Purpose                                           |
| --------------- | ------------------------------------------------- |
| `index.html`    | Chat interface (entry point)                      |
| `success.html`  | Results display with accordion                    |
| `api-client.js` | JavaScript API wrapper (attaches Bearer token)    |
| `auth.js`       | Firebase auth gate, sign-in card, `getIdToken()`  |

## Frontend Configuration

To change the API URL, edit the `API_BASE_URL` constant in `index.html` (currently `http://localhost:8234`).

To plug into a Firebase project, replace the `REPLACE_ME` values in the `window.FIREBASE_CONFIG` block at the top of `index.html` and `success.html` with the project's web-config values from the Firebase console (apiKey, authDomain, projectId).

## Integration Checklist

- [ ] Implement POST /api/start-research
- [ ] Implement GET /api/status/{workflow_id}
- [ ] Implement POST /api/answer/{workflow_id}
- [ ] Implement GET /api/result/{workflow_id}
- [ ] Configure Environment Configuration Profile / .env file with Temporal connection details
- [ ] Configure auth: either set `AUTH_DISABLED=true` for local dev, or populate `FIREBASE_PROJECT_ID` + `window.FIREBASE_CONFIG` for a real deploy
- [ ] Start Temporal server or connect to Cloud
- [ ] Start worker (uv run openai_agents/run_worker.py)
- [ ] Test full flow

## Testing Without Temporal

For UI testing without Temporal, you can:

1. Add mock responses directly in the endpoints
2. Use the mock version of index.html (available on request)

## File Structure

```
ui/
├── backend/
│   ├── main.py              # FastAPI server (configure here)
│   └── auth.py              # Firebase ID token verification dependency
├── public/                  # Static assets
│   ├── fonts/
│   │   └── *.otf           # Aeonik fonts
│   ├── icons/
│   │   └── *.svg           # SVG icons
│   └── images/
│       └── *.png           # Images
├── src/                     # Source code
│   ├── js/
│   │   ├── api-client.js   # JS API client (attaches Bearer token)
│   │   └── auth.js         # Firebase sign-in gate
│   └── css/
│       └── styles.css      # Shared styles
├── index.html               # Chat UI (entry point)
├── success.html             # Results page
└── DEVELOPER_GUIDE.md       # This file
```

## Troubleshooting

### CORS Errors

CORS defaults to allowing all origins. For production, set the `FRONTEND_ORIGINS` env var (comma-separated list) on the API server — no code change needed:

```bash
FRONTEND_ORIGINS=https://research-demo.temporal.io
```

### 401 / 403 from /api/* endpoints

- `401 Missing or malformed Authorization header` → frontend isn't attaching a Bearer token. Confirm sign-in completed (sign-out button visible) and `auth.js` loaded without errors.
- `401 Invalid Firebase ID token` → backend can't verify the token. Check the boot log for the `[auth] Firebase initialized ...` line; if it says `project ID only` but the project ID doesn't match the frontend `FIREBASE_CONFIG.projectId`, you have a mismatch.
- `403 Access restricted to @temporal.io accounts` → user signed in with a non-Temporal Google account.

### Connection Refused

- Check Temporal server is running
- Verify address in temporal.toml for your profile
- Check port 7233 is accessible

### Workflow Not Found

- Verify workflow_id is being passed correctly
- Check worker is running and registered

## Support

For issues with:

- **UI/Frontend**: Check browser console for errors
- **API/Backend**: Check FastAPI logs
- **Temporal**: Check worker logs and Temporal UI (localhost:8233)
