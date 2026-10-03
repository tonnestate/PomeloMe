# Core Ports

PomeloMe uses ports to keep product boundaries explicit.

## AuthorityProvider

Supplies a time-bounded `AuthorityEnvelope` for a run. A MangoMe adapter may implement this port,
but PomeloMe does not know MangoMe concepts such as Contract, Family, Slice, or Evidence.

## ReceiptSink

Accepts projected semantic receipts. Delivery is downstream-facing and idempotency should be enforced
by receipt identity. A MangoMe adapter may consume these receipts and decide whether they become
observations, evidence candidates, or ordinary execution metadata.

## ReferenceResolver

Materializes opaque references only when required. A BlueberryMe adapter can implement protected
handle resolution, while other installations can use object stores or local references.

## ToolRuntime

Provides read-only or observational tool execution. Mutating operations belong to `EffectGateway`.

## ModelRuntime

Provides planning/judgment. The core treats model invocations as semantic decision boundaries, not as
the normal execution loop.

## SandboxBackend

Provides process/workspace isolation. `OpenShellBackend` is the first optional implementation.
Sandbox authorization is physical/resource-level enforcement and does not replace PomeloMe's semantic
policy checks.
