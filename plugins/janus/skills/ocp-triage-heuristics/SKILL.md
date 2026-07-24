---
name: ocp-triage-heuristics
description: Experiential OpenShift live-cluster triage heuristics — layered triage, failure-mode classification, operator status-triple, node lifecycle, and upgrade gates. Distilled for JANUS from the openshift-ops plugin. Read-only diagnostics are autonomous-safe; every mutating remediation is flagged and stays behind JANUS human-approval gates.
---

# OpenShift Triage Heuristics (JANUS-adapted)

Experiential SRE decision knowledge for OpenShift/OCP investigations —
the "what to check first, and why" that a seasoned operator carries.
Distilled from the community `openshift-ops` plugin (marketplace
`ecosystem-claude-plugins`, author Eran Cohen, Apache-2.0) and re-scoped
to JANUS's read-only, sandboxed, human-approval discipline.

## How this differs from the source, and JANUS safety boundary

`openshift-ops` targets a live operator who both diagnoses AND remediates.
JANUS does not remediate autonomously. Every line below is tagged:

- 🔍 **DIAGNOSTIC (autonomous-safe)** — read-only observation. A JANUS
  stage (lab-verify, live-tracer, doc-search, investigation-planner) may
  run/reason about it inside an approved disposable lab. Never against
  production.
- ⚠️ **REMEDIATION (approval-gated)** — mutates cluster/node/operator
  state. JANUS NEVER executes these autonomously. They appear here only
  as *reference* so a report can recommend a fix for a human to apply,
  or so a hypothesis can be phrased ("stuck because a PDB blocks drain").
  Treat as write-boundary: propose, never perform.

## Which JANUS stages consume this

- **investigation-planner** — layered triage + failure-mode classes to
  decompose a symptom into tracks.
- **lab-verify / live-tracer** — 🔍 diagnostic chains as read-only
  verification steps on the approved lab.
- **doc-search / synthesize** — failure-mode vocabulary to correlate
  symptoms with CVE/errata/KB and to rank hypotheses.
- **Upgrade-compatibility case type** — the pre-upgrade gates and
  stuck-upgrade chain map directly onto that case's investment/verify
  gates.

---

## 1. Layered triage — find the layer first

Every cluster issue lives in one layer; the layer picks the diagnostic path.

- **Application** (pods/deployments/statefulsets): pod-level symptoms —
  CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled.
  🔍 Start: `oc describe pod`, `oc logs`.
- **Platform** (operators/controllers/API server): cluster-wide symptoms —
  degraded ClusterOperators, API timeouts, webhook failures.
  🔍 Start: `oc get co`, inspect the operator namespace.
- **Infrastructure** (nodes/networking/storage): node-level symptoms —
  NotReady nodes, PVC stuck Pending, cross-node connectivity failure.
  🔍 Start: `oc get nodes`, `oc describe node`.

🔍 Layer unknown? `oc get co && oc get nodes && oc get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded` — whichever returns problems first names the layer.

---

## 2. Application failure modes (diagnosis priority)

### CrashLoopBackOff 🔍
1. `oc logs <pod> --previous` FIRST — current logs may be from a restart that hasn't crashed yet.
2. Empty logs → container dies before the app starts → inspect image entrypoint/command, not app code.
3. Logs show OOMKilled → compare container memory limit vs actual usage; limit may be too low.
4. Check liveness probe — aggressive probe kills healthy-but-slow-start containers (`failureThreshold`, `initialDelaySeconds`).
5. Check ConfigMap/Secret mounts — a missing mount crashes immediately with no useful log.

### Pending pods 🔍
1. `oc describe pod` → Events. NO events at all → scheduler never attempted placement → almost always insufficient resources or a nodeSelector/affinity matching zero nodes.
2. "FailedScheduling / Insufficient cpu|memory" → `oc adm top nodes` for actual vs allocatable.
3. Taint messages → check pod tolerations, not just node taints.
4. Pod has a PVC → is the PVC itself Pending (`oc get pvc`)? A Pending PVC blocks the pod indefinitely with no obvious error on the pod.

### ImagePullBackOff 🔍 — separate three causes
- **Auth failure (403/401)**: image exists, pull secret wrong/missing. Is the secret linked to the pod's SA with `--for=pull`?
- **Not found (404/manifest unknown)**: wrong tag/registry, or image deleted. Verify exact `image:tag` exists.
- **Unreachable (timeout/refused)**: node can't reach the registry → infrastructure layer → node DNS/proxy.

### Networking failures 🔍
1. **Service has no endpoints** — selector ≠ pod labels. #1 cause of "connection refused" between services.
2. **NetworkPolicy default-deny** — if ANY NetworkPolicy selects a pod, only explicitly allowed traffic passes.
3. **DNS fails** — are CoreDNS pods running in `openshift-dns`? If they crashloop, nothing resolves service names.
4. **Route 503** — backend pods exist but aren't Ready → check readiness probes, not the Route/Ingress.

### Gotchas 🔍
- `oc get events -A --sort-by='.lastTimestamp'` is the best first move when the fault is unknown — events expire after ~1h, so capture early.
- "Completed" pod is NOT a failure (Jobs/init containers produce it normally) — flag only if it should be long-running.
- `oc adm top` needs metrics-server; "metrics not available" is itself a platform-layer problem, not your original bug.

---

## 3. Operator troubleshooting

### Which operator system?
- **Cluster Operators (CVO-managed)** — core platform (networking, ingress, auth, monitoring). `oc get co`. Cannot be installed/uninstalled/reinstalled; diagnose WHY degraded, fix in place.
- **OLM Operators** — OperatorHub add-ons. `oc get csv -A`. Full lifecycle; diagnose the OLM resource chain.

### The Status Triple 🔍 (ClusterOperator severity map)

| AVAILABLE | PROGRESSING | DEGRADED | Meaning |
|---|---|---|---|
| True | False | False | Healthy. |
| True | True | False | Reconciling — normal during upgrades. Wait. |
| True | False | True | Partial failure — serving but wrong. Investigate, not urgent. |
| True | True | True | Actively broken, self-healing. Monitor closely. |
| False | True | False | Not serving but working on it. Give 10–15 min before escalating. |
| False | any | True | Full failure. Immediate action. |

- **PROGRESSING=True for >30 min** outside an upgrade = stuck.

### Cluster Operator diagnosis 🔍
1. Read status conditions — they almost always carry the real error: `oc get co <name> -o jsonpath='{.status.conditions}'`.
2. Find its namespace from `relatedObjects` in CO status (usually `openshift-<name>`).
3. Read the *operator* pod logs (not the operand) — root cause lives there.
4. Follow dependency chains — e.g. console depends on authentication; fix the root operator first.

### OLM / CSV lifecycle 🔍 (phase tells you where it's stuck)
- **Pending**: waiting on deps → `status.requirementStatus` for what's missing.
- **InstallReady**: about to install; stuck here → check the install plan.
- **Installing**: stuck >5 min → check deployment/pod (usually image pull or resource constraint).
- **Succeeded**: healthy.
- **Failed**: `status.conditions` for reason — missing CRDs, insufficient RBAC, resource conflict.
- ⚠️ Deleting a failed CSV makes OLM recreate it from the subscription — a valid recovery *once the transient cause is resolved*. Approval-gated.

### Install-plan & CRD gotchas 🔍
- **Manual approval mode**: unapproved install plans pile up silently; one unapproved plan (`spec.approved: true` needed) blocks ALL future upgrades for that operator.
- **Automatic approval**: upgrades apply on detection; a breaking upgrade may go unnoticed until the operand fails — check CSV phase after auto-upgrades.
- **CRD ownership conflict**: two operators claiming one CRD → check `metadata.ownerReferences` on the CRD for the owning CSV. ⚠️ Fix (delete wrong subscription+CSV) is approval-gated.

### OLM infrastructure 🔍 (cascade — failures flow downward)
1. **OLM Operator** (`openshift-operator-lifecycle-manager`) — manages CSV lifecycle; down → no installs/upgrades.
2. **Catalog Operator** (same ns) — resolves deps, creates install plans; down → subscriptions stop resolving.
3. **Package Server** — serves `packagemanifest`; down → `oc get packagemanifest` empty, new installs show no available operators.
- ⚠️ Stale catalog: `oc delete pod -n openshift-marketplace -l olm.catalogSource=<name>` forces refresh (non-destructive, pod recreated). Approval-gated as it is still a mutation.

### Operator gotchas 🔍
- Restarting an operator pod rarely fixes root cause — a misconfigured CR just crashes it again. Read logs first.
- OperatorGroup must exist BEFORE the subscription — otherwise silence: no error, no install plan.
- Cluster operators cannot be reinstalled — CVO fights deletion; fix in place.
- OLM-level issues (install plan stuck, CSV not created) → logs live in `openshift-operator-lifecycle-manager`, not the failing operator's namespace.

---

## 4. Node operations

### Key fork: automated vs manual infrastructure 🔍 (decide first — affects everything)
- **Automated** (AWS/Azure/GCP/OpenStack): nodes are managed by MachineSets. Scale MachineSets, not nodes. ⚠️ To remove: delete the **Machine** object, never the node object (deleting the node orphans a still-billing VM).
- **Manual** (bare metal / pre-provisioned VMs): you own the full lifecycle (RHCOS ignition, CSR approval, labeling, hardware decommission). The cluster knows nodes, not machines.

### Safe drain 🔍-to-understand / ⚠️-to-execute
1. Cordon first, THEN drain — draining without cordon lets new pods land mid-drain (moving target).
2. Check PDBs first (`oc get pdb -A`): `maxUnavailable: 0` (or `minAvailable` == current replicas) blocks drain silently — it just hangs.
3. Stateful workloads need explicit `--grace-period` to flush/close.
4. `--force` loses data (deletes emptyDir pods without graceful shutdown) — decommission only, never for maintenance.
5. `--delete-emptydir-data` is usually required (system pods use emptyDir) and is safe; it's `--force` that skips graceful handling of user data.
- The drain command itself is ⚠️ (mutation). The PDB/probe *reasoning* is 🔍 and is exactly what explains a "stuck drain / stuck upgrade" hypothesis.

### Node failure diagnosis priority 🔍 (NotReady — most common first)
1. **Network**: can the node reach the API server? Kubelet that can't phone home → NotReady though otherwise healthy. Check SDN/OVN pods on the node.
2. **Disk pressure**: `/var/lib/containers/` fills from accumulated images. (⚠️ remediation: `crictl rmi --prune`, `journalctl --vacuum-time=3d`.)
3. **Memory pressure**: top consumers via `oc adm top pods -A` — often system workloads (monitoring/logging), not user pods.
4. **Kubelet down**: `oc debug node/<name>` → `chroot /host && systemctl status kubelet`; `journalctl -u kubelet` for the real error.
5. **Certificates**: expired kubelet certs → NotReady with no obvious pod-log symptom. Pending CSRs (`oc get csr`) for the node indicate cert-renewal trouble.

### Node gotchas 🔍
- MachineSet edits only affect NEW machines — changing instance type/labels does not touch existing machines.
- Manually-applied node labels are lost on replacement — set persistent labels in the MachineSet `spec.template.spec.metadata.labels`.
- `oc debug node/` needs to schedule a privileged pod — if the node can't schedule (disk full / kubelet down), debug won't work either; SSH is the fallback.
- Deleting a node object does NOT deprovision the VM — cloud keeps billing. For automated infra always delete the Machine.
- Bare-metal add: watch for TWO CSR rounds (client cert, then serving cert); ⚠️ don't bulk-approve blindly — a rogue CSR can admit an unauthorized node.

---

## 5. Cluster upgrade

### Irreversibility (frames the whole case)
OCP upgrades cannot be rolled back. The only recovery from a catastrophic
upgrade is restoring an etcd backup — full downtime, loses everything
after the snapshot. Prevention is the entire game.

### Pre-upgrade gates 🔍 (ALL must pass — maps to the upgrade case's investment gate)
1. Every ClusterOperator AVAILABLE=True, PROGRESSING=False, DEGRADED=False.
2. Every node Ready (a NotReady node stalls MCP rollout).
3. No critical alerts firing.
4. Resource headroom — pods evict/reschedule one node at a time; a full cluster has nowhere to place them.
5. Certificates not expiring soon (expiry mid-upgrade cascades).
6. etcd backup taken (only safety net, given irreversibility).

### Path decision 🔍
- **Standard**: set channel `stable-4.x`, `oc adm upgrade`, pick target. Happy path.
- **EUS-to-EUS**: skips intermediate minors but is a TWO-HOP process (e.g. 4.14 EUS → 4.15 intermediate → 4.16 EUS); finish hop 1 fully before hop 2.
- **Large clusters**: ⚠️ pause the worker MCP (`oc patch mcp worker ... paused:true`) so the control plane updates first, then unpause workers in batches — prevents all workers draining at once.
- **Air-gapped**: mirror release images internally, create an ImageContentSourcePolicy, upgrade with `--to-image` at the mirror.

### Three phases 🔍
1. CVO updates cluster operators (`oc get co`).
2. Control-plane nodes update one at a time (brief API unavailability normal).
3. Worker nodes update — MCO renders configs, nodes drain+reboot one at a time (slowest phase). Done when `oc get mcp` shows UPDATED=True, UPDATING=False, DEGRADED=False.

### Stuck-upgrade diagnosis priority 🔍
1. `oc describe clusterversion` — status conditions usually carry the actual blocker message.
2. `oc get co` for DEGRADED=True / AVAILABLE=False — the blocker ~60% of the time.
3. `oc get mcp` — worker/master pool DEGRADED=True means a node failed to apply the new machine config.
4. Node won't drain — SchedulingDisabled with pods still running → a PDB (`oc get pdb -A`) with `maxUnavailable: 0` blocks eviction forever.
5. machine-config-daemon log on the stuck node (`oc logs -n openshift-machine-config-operator <node daemon pod>`) usually has the error.
6. ⚠️ Force drain — last resort, decommission only; loses emptyDir data and ignores PDBs.

### Upgrade gotchas 🔍
- `--force` on `oc adm upgrade` bypasses version-graph safety checks; it does NOT push a stuck upgrade forward. Almost never correct.
- `--allow-explicit-upgrade` is only for targets outside the recommended graph — not for normal upgrades.
- Worker updates are intentionally slow (one node at a time); a 20-node cluster can take 2h+ for workers alone — slow ≠ stuck.
- `oc adm upgrade --clear` cancels a *pending* upgrade but does not revert applied changes; useless once the upgrade has started.
- Once started-then-stalled, you cannot cancel — fix the blocker and let it continue.

---

## Attribution
Distilled from `openshift-ops` (skills: openshift-debugging,
openshift-operator-troubleshooting, openshift-node-operations,
openshift-cluster-upgrade), marketplace `ecosystem-claude-plugins`,
redhat-community-ai-tools/claude-plugins, Apache-2.0, author Eran Cohen.
Re-scoped to JANUS read-only/approval-gated discipline (🔍 vs ⚠️ tags,
stage-consumer mapping) — no verbatim reuse of remediation flow as
autonomous action.
