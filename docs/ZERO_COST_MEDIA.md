# Zero-Cost Media — Feature Proposal, Not Production

This proposes a host-injected **zero incremental billing** execution boundary for
AVCOS image/video workflows. PlumMe is unchanged. This is not zero hardware
electricity, existing VPS rent, or disk wear. No paid routes, paid cloud plans,
Google credits, GPU rental, subscription services, or unknown providers are admitted.

## Threat model

A planning agent, model registry, free-tier catalog, owner-submitted plan, or
budget field is *untrusted* with respect to billing. Even an estimated price of
zero is insufficient. A remote service advertised as free might bill if its
quota, tier or account changes. The guard therefore only approves exact,
host-audited local adapter names beginning with local.; it does not trust an
external price API and supports no remote provider in this first stage.

Trustworthy deployment REQUIRES separate host enforcement:
- The host owns the allowlist, injects it at the composition root and withholds
  control over its configuration from AI workers.
- The running process has **no billable cloud credential or payment authority**,
  including service account permissions and inherited environment variables.
- Container/network egress is restricted so adapters cannot contact
  billed endpoints using credentials or instance identity.
- No alternate unguarded provider, plugin, shell, MCP route or fallback is
  available to the media agent. Do not rely on agent instructions or budgets.
- Explicit operator review is needed for any future remote route; free trial
  credit is never accepted as cost-free proof.

The Python guard alone CANNOT prove no bill is possible if the surrounding
host grants paid credentials or egress. No production protection is claimed.

## Guard locations

1. PlanAdmitter checks every nested READ/EFFECT/REQUEST_JUDGMENT node and
   requires BudgetEnvelope(max_cost_usd=0).
2. PomeloRuntime checks fully resolved READ args before ToolRuntime.read.
3. EffectGateway checks fully resolved EFFECT args before persistence,
   dispatch, recovery or probe; direct gateway callers cannot skip this guard.
4. A generic ModelRuntime.judge call is blocked: its provider route and
   billing identities cannot be proven from the current interface.
5. Rejected unknown tools, credential-bearing arguments, URL arguments,
   ambiguous serialized refs, or unverifiable model routes fail closed.
6. Runtime rejects mismatched guard injection between itself, admission
   and effect gateway. Guard is a host-owned object, never a plan field.

## Example (operator-controlled only)

    from pomelome import BudgetEnvelope, EffectGateway, PomeloRuntime, ZeroCostGuard
    guard = ZeroCostGuard(
        local_read_tools=frozenset({"local.media.inspect"}),
        local_effect_tools=frozenset({"local.media.render"}),
    )
    gateway = EffectGateway(store, {"local.media.render": audited_local_render},
                            zero_cost=guard)
    runtime = PomeloRuntime(tools=local_tools, effects=gateway, zero_cost=guard)
    result = runtime.run("run1", plan, authority, BudgetEnvelope(max_cost_usd=0))

The placeholder local.media.render must **not** be mapped to a service that
can incur billing. The host's adapter and its operating environment are part of
the security boundary, not automatically verified by the Python class.

## Validation / acceptance

    pytest tests/test_zero_cost.py -q
    pytest -q

Unit controls reject paid/read providers, nonzero budget, model judgment,
credentials, nested/parallel hidden costs, mismatched guard wiring, and
credential-bearing data resolved from previous reads. Local effects can still
execute when both cost and existing capability policies allow them.

These checks do NOT prove a real free cloud GPU or video provider is available,
that PlumMe is connected, or that AVCOS production is protected. That requires
independent host-side audit and integration by the authorized runtime owner.

## Host authority requirement

The trusted AuthorityProvider must mint an AuthorityEnvelope containing the
constraint zero_cost_required = true for every AVCOS media job. This flag is
not supplied by the agent or plan. PlanAdmitter and EffectGateway reject the
job if it is mandatory but no ZeroCostGuard is installed. Malformed flag values
also fail closed. The production host must still prevent issuing unmarked
media authorities and enforce process-level billing/egress isolation.
