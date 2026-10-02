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

- **aws-docs** (`awslabs.aws-documentation-mcp-server`, read-only, no
  credentials): `search_documentation` → `read_documentation` for the full
  page, `recommend` for related pages, `read_sections` for a specific
  section, `get_available_services`. The AWS analogue of okp's public-docs
  role — use it for one canonical `docs.aws.amazon.com` page.
- **aws-knowledge** (hosted at `https://knowledge-mcp.global.api.aws`,
  read-only, no auth): cross-cuts AWS docs / blogs / What's New / API
  references in one index, plus `list_regions` / `get_regional_availability`
  for "is service X in region Y" and `retrieve_skill` for guided runbooks.
  Prefer it for breadth; fall back to aws-docs for a single canonical page.
- **aws-mcp** (the [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws)
  managed server, successor to the awslabs servers above): if it is
  registered instead of (or alongside) aws-docs, its `search_documentation`
  and `retrieve_skill` tools need no AWS credentials and serve the same
  documentation role — prefer them over aws-docs when both are connected.
  Its `call_aws` and `run_script` tools are deliberately **not** granted:
  live AWS API access and script execution have no place in a static stage.
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
