<!-- Part of the janus skill. SKILL.md says when the lead reads this file. -->

# MCP dependencies

Read at intake when a server is missing, or when a human asks how to
register one.

`casket` (versioned source — optional; source-trace activates only when
this server is registered, and its absence is normal), `okp-mcp` (Red Hat docs/CVE/errata/KB),
`rh-api-mcp` (live Red Hat Customer Portal API — authoritative errata
lookup by advisory ID via `rh_get_errata`, complementing okp-mcp's offline
corpus. The two are complementary, not competing: okp-mcp is the
exploration/discovery engine (CVE search, solution articles, natural-language
queries); rh-api-mcp is the precise lookup engine (exact errata ID →
structured JSON with CVE list, affected products, Bugzilla links). okp-mcp
cannot reliably find an errata by bare advisory ID; rh-api-mcp has no search
capability. The optimal pipeline is: okp-mcp discovers → errata ID extracted
→ `rh_get_errata` retrieves authoritative details → finding promoted from
REASONED to VERIFIED. Also provides subscription/system inventory via
`rh_list_subscriptions`, `rh_list_systems`, `rh_get_system` for cases that
need entitlement or registration context. Read-only — JANUS never modifies
subscriptions or system registrations. Optional: doc-search runs without it
but records the absence as a gap when live errata lookup would have helped),
`mslearn`
(Microsoft Learn docs — ARO/Azure layer for doc-search; public remote server,
no auth: `claude mcp add --transport http mslearn
https://learn.microsoft.com/api/mcp`), `aws-docs` / `aws-knowledge` /
`aws-support` (AWS docs — ROSA/AWS layer for doc-search, the AWS mirror of
mslearn; all optional, from
[awslabs/mcp](https://github.com/awslabs/mcp). `aws-knowledge` is the hosted
read-only endpoint `https://knowledge-mcp.global.api.aws` (no auth);
`aws-docs` is read-only via `uvx awslabs.aws-documentation-mcp-server`;
`aws-support` needs AWS credentials + a Business/Enterprise support plan and
only its read-only `describe_*` tools are granted — JANUS never opens, replies
to, or resolves a case. AWS has designated the
[Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws) as the
awslabs servers' successor: if its managed `aws-mcp` server is registered,
doc-search prefers its no-auth `search_documentation` / `retrieve_skill`
over aws-docs — its `call_aws` / `run_script` tools are never granted),
`drgn` (vmcore), `github` (upstream
PR/issue/commit — github-trace and upstream-adviser), `atlassian`
(Atlassian Rovo MCP at `mcp.atlassian.com/v2/mcp` — Jira tickets for
jira-trace; uses OAuth 2.1 authentication, no API token needed.
`executeWrite` / `executeDestructive` are never granted — that is the
safety boundary), `linux` (read-only
RHEL node/VM diagnostics, local or over SSH — lab-verify; register with
`LINUX_MCP_TOOLSET=fixed` so `run_script` stays disabled), `terraform`
(the HashiCorp [terraform-mcp-server](https://github.com/hashicorp/terraform-mcp-server)
— registry lookup of providers, modules and Sentinel policies for
iac-author. Its default tool set is read-only; only the enumerated
registry tools are granted, because enabling its enterprise tools with a
Terraform token adds `create_run` / `apply_run`, which apply real
infrastructure), `ansible`
([ansible-dev-tools](https://github.com/ansible/ansible-dev-tools) MCP —
scaffolding, `ansible-lint`, best-practice and execution-environment
guidance for iac-author. **Only the authoring subset is granted**:
`ansible_navigator` executes playbooks and `ade_setup_environment` runs
the host package manager, so neither is in any agent's tool list). Not bundled with
the plugin — paths are environment-specific, so register them yourself
(`claude mcp add …`); confirm `claude mcp list` shows them `✔ Connected`
before relying on them (a tool being advertised ≠ the server being
connected).
