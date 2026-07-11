---
name: okp-doc-search
description: >-
  How to research Red Hat documentation, KB solutions, CVEs, and errata
  effectively through okp-mcp (search_portal / get_document). Use whenever
  answering a Red Hat / RHEL / OpenShift / CNV question from official
  documentation, resolving an access.redhat.com/solutions URL or a
  docs.redhat.com URL, or when get_document returns "Document not found".
  Covers query construction, Solr doc_id path rules, URL-to-keyword
  extraction, and whole-guide mapping. Triggers: "Red Hatのドキュメントを
  調べて", "このソリューション記事の内容を確認", "KB検索", "エラータを確認".
---

# okp-doc-search — Red Hat knowledge research via okp-mcp

Research Red Hat's official documentation, solutions (KCS/KB), CVEs, and
errata through okp-mcp. This skill encodes what actually works: how to
phrase queries, how to construct `get_document` doc_ids, and how to turn a
URL into findable content.

## Principles

1. **okp-mcp first for anything Red Hat.** For RHEL / Fedora / CentOS /
   OpenShift questions — system administration, security, CVEs, packages,
   kernel, containers — check `search_portal` before answering from memory.
2. **Titles and descriptions outrank body snippets.** Weigh each hit's
   title and Description above the passages. Before concluding anything
   from a passage, return to the document title and confirm your
   interpretation still matches what the document is actually about —
   passages read without the title's context are a common source of wrong
   conclusions.
3. **Retrieved facts beat recall.** Prefer what the tools return over what
   you remember; cite the source with its URL, e.g.
   `[Failed login doesn't replicate across IPA servers](https://access.redhat.com/solutions/3500801)`.
4. **The corpus is an offline snapshot.** Content from the last few months
   (recent CVEs, errata, new features, latest versions) is likely absent.
   Treat "no match" on very recent topics as a corpus gap, not proof of
   absence, and say so explicitly.

## search_portal best practices

- Search with **specific, complete question phrasing**, not bare keywords.
- Use up to **3 query variations** per angle when one phrasing misses.
- Include the **product name and version number in every query**.

Observed hit rates by query pattern:

| Pattern | Success rate |
|---|---|
| version + technical terms + command name | ~95% |
| up to 3 query variations | ~95% |
| version + URL-anchor keywords | ~90% |
| chapter number / section title | ~80% |
| a whole URL pasted as the query | 0% |
| bare solution number (e.g. "7115923") | often misses |

## get_document mechanics

`doc_id` is a **Solr internal path**, not a URL. Passing a URL fails.

| Type | doc_id format | Example |
|---|---|---|
| solutions | `/solutions/{number}/index.html` | `/solutions/7115923/index.html` |
| documentation | `/documentation/en-us/{product}/{version}/html-single/{guide}/index/index.html` | `/documentation/en-us/openshift_container_platform/4.18/html-single/hosted_control_planes/index/index.html` |

Universal rule: the path **must end in `/index.html`** — without it you get
"Document not found".

Converting a docs.redhat.com URL to a doc_id:

```
https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/hosted_control_planes/deploying-hosted-control-planes-in-a-disconnected-environment

  drop the domain
  /en/   → /en-us/
  /html/ → /html-single/
  replace the page-specific slug with index
  append /index.html

→ /documentation/en-us/openshift_container_platform/4.18/html-single/hosted_control_planes/index/index.html
```

Converting a search_portal result URL (to drill into a hit): take the path
part of the returned `access.redhat.com/documentation/...` URL and append
`/index.html`.

Constraints:

- `query` is **required** — without it you only get a "Pass a query to
  get_document" notice.
- Output is capped: max ~10,000 chars, up to 3 relevant passages ×
  1,000 chars. You never get the full document.
- **The query selects which passages return.** Phrase it as the specific
  thing you want to know; re-query with different phrasings to pull
  different sections of the same document.
- Not every solution is indexed — get_document can fail on a valid,
  existing article.

## Working from a URL

**`access.redhat.com/solutions/NNNN`:**

1. Try `get_document` with `/solutions/NNNN/index.html` first — searching
   the bare solution number in search_portal often misses.
2. If not indexed: fetch the URL with WebFetch (if available) to get the
   title and summary, then search_portal with those keywords to recover
   the content. Without WebFetch, extract keywords from the URL slug.

**`docs.redhat.com`:** returns **403 Forbidden** to direct web fetches —
always go through get_document / search_portal.

**URL anchors are the best keyword source.** For
`.../index#connected-to-disconnected-config-registry`:

```
Step 1: expand the anchor into words
  → "connected to disconnected" + "config registry"
Step 2: add version and product
  → "OpenShift 4.20 connected to disconnected config registry"
Step 3: add concrete technical terms
  → + "additionalTrustedCA", "ImageDigestMirrorSet", "oc patch image.config"
Step 4: run up to 3 variations
  1. "OpenShift 4.20 connected to disconnected config registry"
  2. "OpenShift 4.20 configuring cluster mirror registry additionalTrustedCA"
  3. "OpenShift 4.20 oc patch image.config additionalTrustedCA configmap"
```

## Mapping a whole guide

1. **Table of contents**: query the guide title + version
   (e.g. "Disconnected environments OpenShift Container Platform 4.20")
   → chapter list and section numbers.
2. **Per chapter**: query the chapter title
   (e.g. "OpenShift 4.20 Chapter 2 Converting connected cluster disconnected").
3. **Procedure detail**: query concrete commands / YAML field names
   (e.g. "OpenShift 4.20 oc patch image.config.openshift.io cluster")
   → actual command and YAML examples.

## Reporting

- Cite every finding with its CVE / RHSA / KB ID or document title, with URL.
- Be precise about version applicability — a RHEL 8 / OCP 4.16 article does
  not automatically apply to 9 / 4.20.
- Report negative results explicitly: "searched X across N reformulations,
  nothing matched" is a finding, not a failure.
