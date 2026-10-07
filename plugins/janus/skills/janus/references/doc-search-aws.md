<!-- Part of the janus skill. Read by the doc-search stage when its brief names this file. -->

# doc-search — ROSA / AWS layer (aws-docs / aws-knowledge / aws-mcp / aws-support)

Read before any AWS-server call, and before searching for a case that
deploys GPU instances or large-model serving on a lab. The stage's
general rules (Basis semantics, Ref + public URL, Gaps vs negatives)
still apply.

## Servers and division of labor

The mirror image of the mslearn block: where mslearn covers ARO on Azure,
these three cover **ROSA — Red Hat OpenShift Service on AWS — and the AWS
services underneath it**. All are optional; if a server is not connected,
skip its angle silently (same rule as Slack) and note it as a gap.

**Two possible server names each.** The short names below are JANUS's; the
upstream install snippets use longer ones, and a tool exists only under the
name actually registered. Both forms are granted — use whichever is in the
tool list, and treat a layer absent under both as not connected:
`aws-docs` → `awslabs_aws-documentation-mcp-server`, `aws-knowledge` →
`aws-knowledge-mcp-server`, `aws-support` → `awslabs_aws-support-mcp-server`,
`aws-mcp` → `plugin_aws-core_aws-mcp` (the Agent Toolkit shipped as the
`aws-core` plugin; a plugin's server name cannot be changed by the user).
A dot in a registered name becomes an underscore in the tool name
(`awslabs.aws-documentation-mcp-server` →
`mcp__awslabs_aws-documentation-mcp-server__search_documentation`).

- **aws-docs** (`awslabs.aws-documentation-mcp-server`, read-only, no
  credentials): `search_documentation` → `read_documentation` for the full
  page, `recommend` for related pages, `read_sections` for a specific
  section, `search_table` for one row of a huge table. The AWS analogue of
  okp's public-docs role — use it for one canonical `docs.aws.amazon.com`
  page.
  - **Its tool set depends on the partition it was started with.** All of
    the above except `read_documentation` are global-partition only; under
    `AWS_DOCUMENTATION_PARTITION=aws-cn` they are replaced by a single
    `get_available_services`. Both sets are granted, so a tool missing from
    your list means the other partition is configured, not that the grant
    is wrong — work with what is there and record the rest as a Gap.
  - **`search_table` is the right tool for a quota, limit, price or
    supported-X question.** `search_table(url, section_title, query,
    max_rows)` returns matching rows as structured JSON instead of the
    whole page, so the answer to "what is the default limit for X" comes
    back as the row itself rather than as a paragraph you reconstruct from
    a truncated page. Use it for service-quota tables, instance-type and
    region support matrices, and pricing tables — exactly the pages where
    `read_documentation` truncates mid-table and a REASONED guess creeps
    in. A row returned verbatim is VERIFIED; a limit inferred from
    surrounding prose is not. Quote the row in the finding and keep the
    page URL (plus the section title) as the Ref. It is `aws-docs` only —
    aws-knowledge and aws-mcp have no equivalent, so fall back to
    `read_sections` on the table's section there.
- **aws-knowledge** (hosted at `https://knowledge-mcp.global.api.aws`,
  read-only, no auth): cross-cuts AWS docs / blogs / What's New / API
  references in one index, plus `list_regions` / `get_regional_availability`
  for "is service X in region Y" and `retrieve_skill` for guided runbooks.
  Prefer it for breadth; fall back to aws-docs for a single canonical page.
- **aws-mcp** (the [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws)
  managed server, successor to the awslabs servers above): if it is
  registered instead of (or alongside) aws-docs, its `aws___search_documentation`,
  `aws___read_documentation` and `aws___retrieve_skill` tools need no AWS
  credentials and serve the same documentation role — prefer them over
  aws-docs when both are connected. It is a **proxy**, so every backend
  tool carries an `aws___` prefix; a bare `search_documentation` on this
  server does not exist. Its `aws___call_aws` and `aws___run_script` tools
  are deliberately **not** granted: live AWS API access and script
  execution have no place in a static stage.
- **aws-support** (`awslabs.aws-support-mcp-server`, needs AWS credentials +
  a Business/Enterprise support plan): **read-only tools only** —
  `describe_support_cases`, `describe_communications`, `describe_services`,
  `describe_severity_levels`, `describe_create_case_options`,
  `describe_supported_languages`, `describe_attachment`. JANUS never creates,
  replies to, or resolves a case — those write tools are deliberately not
  granted. Use it only to read an AWS support case the case already references.

- **Division of labor**: OpenShift-the-product questions (CVE, errata, KB,
  component behavior) stay with okp-mcp. **ROSA-the-managed-service**
  questions (supported ROSA versions, the AWS-SRE responsibility split, AWS
  quotas / VPC / IAM / EC2 limits, `rosa` / `aws` CLI behavior) belong here —
  the same split mslearn has for ARO. For a ROSA case, search okp (the OCP
  layer) and aws (the AWS layer) and note where they disagree: the ROSA
  support lifecycle can be narrower than the OCP one.
- Ref format: the public `docs.aws.amazon.com` URL a tool returns (e.g.
  `https://docs.aws.amazon.com/rosa/latest/userguide/rosa-sts.html`); for a
  support case, `AWS support case <caseId>`. Record it in the References
  table like any other URL.

## Pre-deployment constraint check (GPU / model-serving cases)

When the case will deploy GPU instances or large-model serving on a lab
cluster (a lab-verify stage or an infra handoff follows this stage), run
this check as an explicit phase and record the results as findings —
discovering a constraint after the environment is deployed costs hours
of rebuild:

- **AMI instance-type allowlist**: ROSA Classic worker nodes boot from an
  AWS Marketplace AMI with its own instance-type allowlist — an instance
  type appearing in `rosa list instance-types` does NOT prove the AMI
  permits it (the newest GPU families are the usual gap). Self-managed
  OCP has no such AMI restriction. State the ROSA-vs-self-managed
  distinction explicitly in the findings, and search for tracking
  tickets (e.g. the ROSA Jira project) before concluding an instance
  type is usable.
- **AZ availability**: confirm the GPU instance type is offered in the
  target region/AZ (`aws-knowledge` `get_regional_availability`).
- **Service quota headroom**: a GPU family has its own vCPU quota, and
  the account default is frequently zero — a lab that passes every other
  check still fails to provision. Read the row out of the EC2
  service-quota table with `aws-docs` `search_table` (query the quota
  name, e.g. "Running On-Demand P instances") and record the default as
  a quoted row; the quota-increase lead time belongs in the report.
- **Disk sizing**: node disk must be ≥ 3× the model size — a 63 GB+
  ModelCar image hits ephemeral-storage pressure on a 200 GB disk;
  500 GB+ is the safe floor for large models.
- **Serving image capability**: confirm the serving image supports the
  model's quantization format (e.g. MXFP4) from image docs/release
  notes, not assumption.

## Failure pattern (symptom → wrong move → correct move)

- An instance type appears in `rosa list instance-types` → treating that
  as proof it can be provisioned on ROSA Classic → the Marketplace AMI
  keeps its own allowlist; verify AMI support (release notes, ROSA Jira)
  and record the ROSA-Classic-vs-self-managed-OCP distinction in the
  findings.
