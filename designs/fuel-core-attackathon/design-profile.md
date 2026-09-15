# Design Profile: fuel-core-attackathon

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: fuel-core-attackathon
- Ecosystem: fuel
- Languages: rust
- Protocol type: Fuel L1 blockchain node
- Execution model: UTXO-based block execution with FuelVM
- Consensus model: fuel-core consensus/da layer integration
- VM: FuelVM

## Focus Surfaces

- Block execution, transaction validation, and input/output coin accounting.
- External effect status and bridge accounting, including value-bearing message data, coin selection, and transaction-builder input variants.
- Terminal range and cursor boundaries in paginated or bounded APIs.
- RPC transport resource control: idle no-header, partial-header, slow-body, large Content-Length, junk body, keep-alive, response-write, and subscription lifetime variants.
- Timer, retry, and service liveness, including shutdown and drop ordering.
- Signed arithmetic and control-loop panics reachable from public inputs.
- Txpool admission, ordering, dependency, and replacement rules.
- Consensus, p2p message handling, and peer sync progress binding.
