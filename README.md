# Saint Eyewear reporting workspace

React frontend, Cloudflare Pages gateway, private Cloudflare Python Worker, and Supabase authentication, PostgreSQL and private storage.

**Release: internal review only. This is not an approved client-reporting application.** The source preserves the draft labels and client-issue lock. A successful build does not establish SOP acceptance.

## Source layout

- `frontend/`: React upload, review, history, configuration and draft-download interface.
- `worker/index.js`: same-origin API gateway, secure session cookies, security headers and private Python service binding.
- `backend/`: portable Python XLSX validation, Decimal calculations, rule assessment and draft DOCX generation.
- `edge/index.ts`: Supabase authorization, membership, private storage and run persistence service.
- `supabase/schema.sql`: schema reference for the dedicated Saint Eyewear project. Review before applying; it is not an automatic deployment step.
- `tests/`: synthetic accounting tests and mocked gateway/build tests.
- `tools/build_pages.mjs`: dependency-free Cloudflare Pages build.
- `wrangler.json`: Pages configuration, including the private `ENGINE` service binding.

## Verify and build

Use Node 22 or later and Python 3.13.

```sh
npm ci
npm run check
npm test
npm run build
python -m pip install -r requirements-test.txt
python -m pytest -q
```

`npm run build` writes `dist/_worker.js` and the required Pages routing files. It does not deploy anything. The build uses Node built-ins and needs no npm build dependencies. React and ReactDOM are version-pinned runtime resources served through the gateway.

Local verification on 23 October 2026: 46 Python tests and 15 gateway/build tests passed. These tests use synthetic data and mocked remote services; they are not a live user-login or real-report acceptance test. Test-generated files are excluded from Git.

## Cloudflare connection

The intended hosting project is Cloudflare Pages, built from this repository's `main` branch:

| Setting | Value |
| --- | --- |
| Framework preset | None |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | Repository root |
| Node version | 22 |
| Private service binding | `ENGINE` -> `saint-eyewear-engine` |

The attempted Git connection returned Cloudflare HTTP 401 / error 8000011 concerning the Pages Git installation. No Pages project or live frontend URL was created by that attempt. Reauthorize the Cloudflare connection and its GitHub access to this repository before retrying. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Required security configuration

The Cloudflare server runtime needs `GATEWAY_SECRET`. The Supabase Edge Function needs the SHA-256 digest of the same value as `SAINT_GATEWAY_SHA256`. Configure these in their respective secret stores, never in repository files, browser code or chat. Supabase supplies its service-role credential internally to the Edge Function.

Authentication, email confirmation, active workspace membership and reviewer permissions remain enforced. The Python Worker must stay private. Preview builds intentionally have no production `ENGINE` binding. Missing configuration returns an error rather than allowing unauthenticated financial operations.

The repository is public. No client workbooks, generated client reports, passwords or privileged service keys belong here. `.env.example` contains names only; the publishable Supabase application key is not a service-role key.

## Release limitations

The previously deployed backend/Edge revision is older than this source. Align those revisions and server secrets before testing the frontend with real uploads. No complete live login -> upload -> process -> review -> download test has passed.

Original report templates, reference scripts, and the August/September issued-pack acceptance materials have not been validated. Generated Word files remain internal drafts. Original-template fidelity, the specified chart layouts, financial comparisons to the issued packs and owner approval remain release blockers.

This portable Python implementation uses standard-library XLSX and DOCX processing rather than claiming the SOP's original library/template pipeline is deployed. Source uploads are capped at 5 MB each and 12 MB combined. Real-file load testing remains required.

Cloudflare Pages does not run the Worker's scheduled handler. Retention needs a separately authorized scheduler and owner confirmation; no cleanup schedule is activated by this repository.
