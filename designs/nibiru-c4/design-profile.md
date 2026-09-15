# Design Profile: nibiru-c4

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: nibiru-c4
- Ecosystem: nibiru, cosmos, evm, wasm
- Languages: go, solidity
- Protocol type: EVM + Cosmos SDK hybrid chain
- Execution model: dual EVM and CosmWasm runtimes over CometBFT state
- Consensus model: CometBFT
- VM: EVM + CosmWasm

## Focus Surfaces

- VM/native account creation, account type conversion, code-hash writes, nonce writes, and deterministic address collision handling.
- Future deterministic VM deployment addresses versus user-created native account classes such as vesting, locked, named, derived, or compatibility accounts.
- Native balance mutators, staking/delegation flows, module sends, mint/burn, escrow, and any VM-facing balance mirror.
- Precompile, host-function, Wasm, internal contract-call helper, and VM-to-native adapter success and failure exits.
- Nested VM/native execution, state-cache ownership, dirty-object restoration, commit/rollback, read-only/query isolation, and shared keeper pointer restoration.
- ERC20 or token helper behavior for empty successful returns, false returns, fee-on-transfer deltas, rebasing, callbacks, recursive helper calls, and metadata failures.
- Gas, fee, refund, and denomination units across builders, ante checks, execution, internal calls, tracing, display, and finalization.
- Batched or multi-message wrappers, including SDK sequence, VM nonce, StateDB nonce, contract creation, normal calls, failed calls, and later messages.
