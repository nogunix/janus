# JANUS — Claude Code plugin

An OpenShift / RHEL / CNV **research & investigation pipeline** for
Claude Code — case types range from kernel crash forensics to
upgrade/compatibility analysis, CVE impact assessment, and
operator/component behavior investigation. JANUS uses Claude Code itself as
the orchestrator: the lead session composes a pipeline of small agent stages
per case type, gates the dynamic ones, and
hands a ranked-hypothesis report to a human. It lays evidence and hypotheses on
the table — the human makes the final call.

## What's in the plugin

```
.claude-plugin/marketplace.json      # marketplace listing → plugins/janus
plugins/janus/
  .claude-plugin/plugin.json         # plugin manifest
  skills/janus/SKILL.md              # /janus — pipeline driver
  skills/deck/                       # report → branded .pptx/PDF
  skills/okp-doc-search/             # okp-mcp research know-how (queries, doc_id rules)
  agents/                            # 8 agents (patterns inlined into each)
    doc-search  source-trace  github-trace  crash-analyze  lab-verify
    synthesize  self-improver  upstream-adviser
```

The pipeline: `{ doc-search, source-trace, crash-analyze, [approve] lab-verify } | synthesize`
— six composable stages connected by a universal `findings/*.md` format
(github-trace joins conditionally when another stage surfaces an upstream
PR/issue), plus two periodic agents. Reusable investigation patterns (drgn triage, CVE tracing,
refuting an a-priori hypothesis, goroutine-leak repro, etc.) are **inlined into
each agent** so they travel with the plugin.

## Install

This repo is itself a Claude Code plugin marketplace
(`.claude-plugin/marketplace.json`). Inside a Claude Code session:

```
/plugin marketplace add nogunix/janus   # register straight from GitHub
/plugin install janus@janus             # install the plugin (plugin@marketplace)
```

Or from a local clone (useful when editing the plugin):

```bash
git clone https://github.com/nogunix/janus.git ~/janus
```

```
/plugin marketplace add ~/janus     # register the local marketplace
/plugin install janus@janus         # install the plugin (plugin@marketplace)
```

Restart Claude Code so the skills and agents load, then verify:

- `/plugin` — `janus` shows as installed and enabled
- `/janus` appears in the skill list; the eight `janus:*` agents appear in
  the Agent tool list

Day-to-day maintenance:

```
/plugin marketplace update janus    # re-read the local clone after edits
/plugin uninstall janus@janus       # remove the plugin
/plugin marketplace remove janus    # remove the marketplace entry
```

## Working method (model-agnostic quality)

Investigation quality is enforced by explicit discipline, not by the
model in the seat:

- **Evidence-basis labels** — every finding carries
  `Basis: VERIFIED | REASONED | ASSUMED` (tool output observed vs.
  inferred from reading vs. carried in) alongside its confidence, and a
  label is only promoted by new evidence.
- **Named acceptance gates** — the lead checks each report against six
  named gates (references, public URLs, no speculation language, basis
  integrity, completeness, verbatim artifact names) and sends failures
  back to synthesize by gate name; a HIGH hypothesis needs at least one
  VERIFIED finding behind it.
- **Causation gate** — crash-analyze may not record a crash cause
  without "X causes Y because Z" where X and Y are observations from
  this vmcore; correlation without a mechanism caps at MEDIUM.
- **Failure-pattern catalogs** — agents carry
  `symptom → wrong move → correct move` entries seeded from real cases
  (e.g. a search timeout means "reduce scope", never "report negative").
- **Lessons loop** — project-specific lessons are banked (with human
  approval) in `.claude/skills/janus-lessons/SKILL.md`, which plugin
  updates never overwrite; the lead injects relevant entries into stage
  briefs, and recurring ones get promoted into the plugin's own
  catalogs via the self-improver review queue.

See [CHANGELOG.md](CHANGELOG.md) for version history.

## MCP dependencies (environment-specific)

The plugin does not bundle MCP config — server paths are machine-specific.
Register each server yourself (`claude mcp add …`) before running an
investigation, then confirm `claude mcp list` shows `✔ Connected` — a tool
being advertised isn't the same as the server being reachable.

### casket — optional, not yet published
Versioned OpenShift/RHEL/CNV source reverse-lookup, backed by a
ripgrep/OpenGrok index over locally mirrored source trees. A personal
project of the author that hasn't been released yet, so there's no
public repo or instance to point at for now. Without it the rest of the
pipeline still runs — only the `source-trace` stage goes idle.

Everything below is public or self-hostable today, so the rest of the
pipeline works for anyone.

### okp-mcp — Red Hat docs / CVE / errata / KB
Bridges to the official **Offline Knowledge Portal** (OKP) Solr index.
Requires a Red Hat account (`registry.redhat.io` access + an OKP access key
from <https://access.redhat.com/offline/access/>). The bridge server itself
is public OSS: <https://github.com/rhel-lightspeed/okp-mcp>.

```bash
podman login registry.redhat.io        # needs a Red Hat account
# build the okp-mcp bridge image per github.com/rhel-lightspeed/okp-mcp
podman play kube okp-pod.yaml          # manifest below
claude mcp add --transport http okp-mcp http://localhost:8000/mcp --scope user
```

`okp-pod.yaml` — Solr + bridge in one pod:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: okp-mcp
spec:
  containers:
    - name: redhat-okp
      image: registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest
      ports:
        - containerPort: 8983
          hostPort: 8983
      env:
        - name: ACCESS_KEY
          value: "<your-okp-access-key>"
        - name: SOLR_JETTY_HOST
          value: "0.0.0.0"
      volumeMounts:
        - name: redhat-okp-data
          mountPath: /opt/solr/server/solr/portal/data
    - name: okp-mcp
      image: localhost/okp-mcp:latest
      ports:
        - containerPort: 8000
          hostPort: 8000
      env:
        - name: MCP_SOLR_URL
          value: "http://localhost:8983"
  volumes:
    - name: redhat-okp-data
      persistentVolumeClaim:
        claimName: redhat-okp-data
  restartPolicy: Always
```

### mslearn — Microsoft Learn docs for the ARO/Azure layer
Public remote server, no auth, used by doc-search:
```bash
claude mcp add --transport http mslearn https://learn.microsoft.com/api/mcp
```

### slack — optional, bring your own workspace
doc-search can supplement official docs with your team's Slack
discussions when a Slack MCP server is registered (it calls tools like
`search_messages` / `get_thread` / `get_channel_history` — e.g.
korotovsky/slack-mcp-server provides these). Point it at a workspace
you are authorized to search. Slack hits are supplementary evidence
only — findings attribute them as `[slack] #channel, YYYY-MM-DD` and
never rest a conclusion on them alone. Without it, doc-search simply
skips the Slack angle.

(Jira/Confluence MCP servers such as mcp-atlassian are **not** JANUS
dependencies — no stage calls them.)

### drgn — vmcore static analysis
Public OSS (walac/drgn-mcp). Run it sandboxed — network-cut, read-only,
unprivileged — since upstream has no built-in sandboxing:
```bash
git clone https://github.com/walac/drgn-mcp.git
cd drgn-mcp && python3 -m venv .venv && .venv/bin/pip install -e .
claude mcp add drgn -s user -- "$(pwd)/.venv/bin/python" -m drgn_mcp.server
```

### github — upstream PR/issue/commit lookup
Official hosted read-only endpoint — no server to run yourself. Used by
github-trace and upstream-adviser:
```bash
claude mcp add --transport http github https://api.githubcopilot.com/mcp/readonly
```

### linux — read-only RHEL node/VM diagnostics
Public OSS (rhel-lightspeed/linux-mcp-server), local or over SSH. Used by
lab-verify. Register with `LINUX_MCP_TOOLSET=fixed` (lowercase) so the
arbitrary-script `run_script` toolset stays disabled — that's the safety
boundary that keeps lab-verify read-only:
```bash
pip install git+https://github.com/rhel-lightspeed/linux-mcp-server.git
claude mcp add linux -s user --env LINUX_MCP_TOOLSET=fixed -- linux-mcp-server
```

## Safety

Read-only. Dead-artifact analysis (vmcore) is autonomous-safe; live-target work
(lab provisioning, dynamic tracing) requires explicit human approval and a
disposable lab, never production. Never spoofs guardrails; the final
root-cause call is the human's.

## License

[MIT](LICENSE)
