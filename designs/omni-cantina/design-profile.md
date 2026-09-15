# Design Profile: omni-cantina

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: omni-cantina
- Ecosystem: omni, evm, cosmos
- Languages: go, solidity
- Protocol type: omni cross-chain messaging network
- Execution model: halo consensus over anvil EVM chains with portal contracts
- Consensus model: halo (Cosmos-SDK based)
- VM: EVM

## Focus Surfaces

- Consensus finalization and external error handling.
- Vote extension commit logic and signature edges.
- Signature canonicalization and duplicate persistence.
- Cross-runtime event ordering and delayed accounting.
- Temporal bridge mirrors and reserve snapshots.
- Proposal cardinality and retained state growth.
- Fork payload sidecar equivalence.
- Delayed identity reservation and public key handling.
- Cross-domain message submission, validation fees, and portal contract interactions.
