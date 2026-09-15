# Design Profile: blast-cantina

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: blast-cantina
- Ecosystem: blast, evm, l2
- Languages: solidity, typescript
- Protocol type: Blast EVM L2 (OP-stack style)
- Execution model: EVM L2 with native yield and gas tokens
- Consensus model: OP-stack rollup derivation and sequencing
- VM: EVM

## Focus Surfaces

- Execution gas, precompiles, refunds, discounts, and fee attribution.
- Cross-domain bridge messaging, gas forwarding, replay, deposits, and withdrawals.
- Deployment, genesis, proxy, implementation, initialization, and durable config.
- Native/VM state mirrors, system contracts, and special accounts.
- External yield providers, staking/vault flows, oracles, shutdown, and recovery.
- Fork gates, migrations, and compatibility paths.
