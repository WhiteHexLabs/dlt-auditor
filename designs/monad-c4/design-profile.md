# Design Profile: monad-c4

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: monad-c4
- Ecosystem: monad, evm
- Languages: rust, cpp
- Protocol type: parallel EVM L1 blockchain
- Execution model: optimistic parallel execution with deferred effects
- Consensus model: MonadBFT
- VM: EVM

## Focus Surfaces

- MonadBFT consensus, block and payload validation, fork and timeout handling.
- Parallel execution scheduling, state-cache ownership, commit/rollback ordering, and deferred effect application.
- Txpool admission and ordering versus block policy versus execution predicate equivalence (nonce, balance, reserve, chain-id, system-sender).
- Transaction policy regressions across transaction types, including legacy versus EIP-1559 fee accounting and EIP-7702 delegated-status timing.
- Storage I/O and offset consistency, state accesses, and account/version binding.
- Async channel backpressure, panic propagation, and service shutdown ordering.
- Timer and callback coordinate regressions where a callback may use a different round/view/coordinate than the queued vote, proposal, or request.

## Hypothesis Preservation Notes

- A fee/accounting hypothesis is distinct when it compares legacy gas price, EIP-1559 effective bid, base fee, priority fee, reserve/emptying rules, or proposal-time affordability.
- An EIP-7702 hypothesis is distinct when it involves wrong-chain child plus system sender fatality/order, txpool ordered delegation versus block-policy global pre-marking, or Rust/C++ execution child-skip predicates.
- A timer/callback hypothesis is distinct when a callback coordinate can differ from the queued vote/proposal/request coordinate.
