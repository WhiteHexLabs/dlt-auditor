# Design Profile: fuel-ts-attackathon

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: fuel-ts-attackathon
- Ecosystem: fuel, typescript
- Languages: typescript
- Protocol type: Fuel TypeScript SDKs and wallets
- Execution model: client libraries over Fuel node APIs
- Consensus model: n/a (client side)
- VM: FuelVM (via SDK encoding)

## Focus Surfaces

- Pending resource reservation and client lifecycle management.
- Default pending resource reuse and cleanup.
- Transaction submission flows, wallet and signer handling, and key material exposure.
- Amount and gas math precision across number/BN boundaries, min-gas and gas estimation.
- Provider and GraphQL query pagination, cursor handling, and error propagation.
- Address, asset, and message encoding/decoding edge cases.
