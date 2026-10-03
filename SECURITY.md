# Security Status

PomeloMe v0.1 is an experimental reference implementation, not a production security product.

Security-relevant guarantees in v0.1 are limited to the tested core invariants: bounded plan
admission, deny-by-default capability checks, intent-before-effect persistence, non-blind recovery of
uncertain effects, and product-boundary separation.

Do not treat the local SQLite store as a hardened distributed durability layer. Use a production
workflow backend and an appropriate sandbox/security backend for real deployments.
