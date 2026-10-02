<!-- Part of the janus skill. SKILL.md says when the lead reads this file. -->

# Findings format

Read when writing a findings file yourself (a step-5a supplement) or when
judging C1/basis or a Ref's format at step 7. Stage agents carry their own
copy of the output template.

Every stage writes to `cases/<id>/findings/<stage>.md` in the same format.

## YAML frontmatter (required)

```yaml
---
stage: <stage-name>
case: <case-id>
date: <ISO 8601>
status: complete | partial | failed
model: <the model that actually ran this stage>
tool_calls: <N>
duration_s: <seconds>
---
```

`model` records **what ran, not what was assigned**. The Model strategy
table is the declared assignment; the cost de-escalation and refusal
ladders both substitute a different model legitimately and silently, so
the assignment cannot be read backwards off the table. Write the model
you are actually running as. A stage that cannot determine it writes
`model: unrecorded` — never omits the key, and never guesses the table's
value. This is what makes "quality survives a model swap" auditable
after the fact instead of merely asserted: without it, a report produced
by a degraded model is indistinguishable from one produced by the
assigned model.

## Finding structure

```markdown
### F<N>: <one-line title>
- **Confidence**: HIGH | MEDIUM | LOW
- **Basis**: VERIFIED | REASONED | ASSUMED
- **Type**: known-issue | implementation | version-change | crash-cause | behavior | constraint | negative
- **Detail**: <2-5 sentences>
- **Ref**: <verifiable reference>
```

**Basis** states what backs the claim — it is orthogonal to Confidence:

- **VERIFIED** — tool output observed in this session backs the claim
  (the Ref points at that output: a document actually opened, code
  actually read/diffed, a drgn/oc command actually run).
- **REASONED** — inferred from something read (a search snippet, a code
  structure, a cross-reference) without direct verification.
- **ASSUMED** — neither; carried in from the question or from prior
  knowledge.

A claim's Basis may only be promoted by new evidence, never by
restatement. A HIGH-confidence finding on an ASSUMED basis is a
contradiction — synthesize and the lead's gates reject it.

## Reference format

| Source | Format | Example |
|---|---|---|
| docs | CVE / RHSA / KB ID | `CVE-2024-1086` |
| rh-api | errata advisory ID (live) | `RHSA-2024:0001 (via rh-api-mcp)` |
| source | `component@NVR file:line` | `hyperkube@4.20.0 pkg/…/eviction.go:414` |
| drgn | script + output path | `audit/drgn-1.py → audit/drgn-1.log` |
| lab | command + cluster ver | `oc get pods (OCP 4.20.0) → audit/lab-1.log` |
| terraform | `namespace/provider@version resource` or `module@version` | `hashicorp/azurerm@4.14.0 azurerm_redhat_openshift_cluster` |
| iac | file + static-check output | `iac/terraform/main.tf → audit/iac-1.log` |
| slack | `#channel, YYYY-MM-DD` | `#forum-kubevirt, 2026-06-15` |
| github | `owner/repo#N` or commit SHA + URL | `kubevirt/kubevirt#14309` |
| mslearn | Learn URL | `https://learn.microsoft.com/azure/openshift/support-lifecycle` |
| aws-docs | `docs.aws.amazon.com` URL | `https://docs.aws.amazon.com/rosa/latest/userguide/rosa-sts.html` |
| aws-support | `AWS support case <id>` | `AWS support case 1234567890` |

## Lead-written supplement files (step 5a)

**Supplement file conventions:**

- **Naming**: `<stage>-<source>-supplement.md` — e.g.
  `doc-search-mslearn-supplement.md`, `doc-search-slack-supplement.md`
- **Frontmatter**: include `supplement_of: <parent-file>.md` and
  `source: <mcp-name>` alongside the standard stage/case/date/status
  fields
- **Finding numbers**: globally unique within the case. The parent
  stage owns F1–F19 (or whatever range it used). Each supplement
  starts at the next available block of 10: F20–F29, F30–F39, etc.
  Check existing files before assigning numbers.
- **Delta field**: each finding in a supplement should include a
  `Delta from <prior_case>:` line when `case.yaml` has a
  `prior_case` reference, documenting what is new vs. the prior
  investigation
- **Stage contract**: supplement files follow the same finding format
  (Confidence, Basis, Type, Detail, Ref) as the parent stage. They
  are first-class findings — synthesize reads them alongside the
  parent.

**Example supplement frontmatter:**
```yaml
---
stage: doc-search
case: JANUS-006
date: 2026-08-19T07:00:00Z
status: complete
supplement_of: doc-search.md
source: slack
tool_calls: 4
---
```
