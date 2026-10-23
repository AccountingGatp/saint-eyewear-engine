# GitHub to Cloudflare deployment

## Current status

Application source and a locally tested Cloudflare Pages build are prepared in this repository. No live frontend URL has been verified.

The attempted Pages/Git connection was rejected with HTTP 401 and error 8000011: an issue with the Cloudflare Pages Git installation. The connected credential had Pages Write scope, but Cloudflare still rejected it. Do not bypass this denial with alternative credentials or a public processing endpoint. An authorized account holder must reconnect the Cloudflare integration and authorize Cloudflare's GitHub application for `AccountingGatp/saint-eyewear-engine`.

## Create the Git-connected project after authorization

In Cloudflare, choose Workers & Pages, create a Pages application, and connect GitHub. Select this repository and production branch `main`.

Use framework preset **None**, build command **`npm run build`**, output directory **`dist`**, repository root, and Node **22**. The checked-in `wrangler.json` declares the private `ENGINE` service binding. Keep preview access to production services disabled, and configure Pages to fail closed rather than serving a fallback when its function configuration fails.

A Pages build compiles the frontend gateway only. It does not publish the Python Worker or Supabase Edge Function, configure secrets, apply SQL, authorize users, or prove that the reporting application works end to end.

## Align the server components

Before enabling real financial uploads:

1. Review and deploy the matching `backend/` revision to the private `saint-eyewear-engine` Worker, retaining its private service-binding-only access. The payload builder can prepare a reviewable source bundle: `python tools/build_deployment_payloads.py`.
2. Deploy the matching `edge/index.ts` as Supabase's `saint-workspace` function. The function implements gateway-secret verification, `auth.getUser`, confirmed-email checks and active membership authorization. Do not remove these checks.
3. Use a securely generated server-only `GATEWAY_SECRET` in Cloudflare and its SHA-256 hexadecimal digest as `SAINT_GATEWAY_SHA256` in Supabase. They must match. Do not commit either value. No secret value is supplied in this repository.
4. Confirm the private bucket and existing schema. Do not rerun schema scripts blindly against another project.
5. Set Supabase authentication site/redirect URLs to the actual frontend URL only after Cloudflare has created it. Keep email confirmation and workspace membership checks enabled.

## Deployment checks

- Verify the actual Pages deployment status and URL; do not infer a live URL from a proposed project name.
- `GET /api/health` should confirm both Python and database connectivity while preserving `client_ready: false`.
- An unsigned-in session must not return financial data. Cross-origin writes must fail.
- Use authorized test accounts to check staff/reviewer separation, private uploads, reopened history, reviewer explanations, sign-off and short-lived draft downloads.
- Run the complete upload -> validate -> review -> generate -> download flow with approved acceptance inputs.
- Client issuance remains disabled until original-template and financial acceptance tests pass and the owner signs off.

## Retention

Pages does not execute scheduled Worker events. Arrange retention separately only after the owner approves the proposed periods. This build does not silently activate deletion jobs.
