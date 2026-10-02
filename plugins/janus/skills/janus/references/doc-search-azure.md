<!-- Part of the janus skill. Read by the doc-search stage when its brief names this file. -->

# doc-search — ARO / Azure layer (mslearn)

Read before any `mcp__mslearn__*` call. The stage's general rules (Basis
semantics, Ref + public URL, Gaps vs negatives) still apply.

- Three tools: `microsoft_docs_search` (chunked semantic search, ~10 chunks
  with `contentUrl`), `microsoft_docs_fetch` (full article as markdown — use
  when a search chunk is truncated mid-topic), `microsoft_code_sample_search`
  (az CLI / ARM / Bicep examples).
- **Division of labor**: OCP-the-product questions (CVE, errata, KB,
  component behavior) belong to okp-mcp. ARO-the-managed-service questions
  (supported ARO versions, SRE policy, Azure quotas/networking, cluster
  create/upgrade via `az aro`) belong to mslearn. For ARO cases search both
  and note where they disagree — the ARO support lifecycle is narrower than
  the OCP one.
- It is a live service (no corpus-staleness caveat, unlike okp-mcp), covers
  public docs only, needs no auth.
- Ref format: the `contentUrl` (e.g.
  `https://learn.microsoft.com/azure/openshift/support-lifecycle`) — record
  it in the References table like any other URL.

## Mapping a whole guide
1. Query the guide title + version → table of contents / chapter list.
2. Query chapter titles → per-chapter detail.
3. Query concrete commands / YAML field names → procedure-level passages.
