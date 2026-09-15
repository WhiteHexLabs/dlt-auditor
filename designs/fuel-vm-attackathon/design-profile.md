# Design Profile: fuel-vm-attackathon

Hypothesis context for audit prioritization only. Focus surfaces are audit
priority, never evidence: every finding still requires target evidence,
reachability, attacker control, and impact.

- Name: fuel-vm-attackathon
- Ecosystem: fuel
- Languages: rust
- Protocol type: FuelVM virtual machine crate
- Execution model: register-based VM executing Fuel bytecode
- Consensus model: n/a (VM layer)
- VM: FuelVM

## Focus Surfaces

- Instruction decode and dispatch semantics, including wide integer compare/arithmetic opcodes and status/error register behavior.
- Contract/code load and copy opcodes, memory model, and requested-length paths.
- Checked arithmetic, overflow behavior, and parameter bounds.
- Memory, contract, and buffer ownership across call frames.
- Storage I/O and offset consistency from VM instructions.
- Changelog, patch archaeology, and regression analysis of past fixes.
- Predicate, fee, and panic rules enforced inside the VM.
