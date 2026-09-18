---
id: blockchain.solidity.evm
status: verified
version: 0.1.0
contexts:
  languages: [Solidity]
  runtimes: [EVM]
  frameworks: [none]
prerequisites:
  - programming.functions
  - programming.conditions
  - programming.collections
  - programming.debugging
outcomes:
  - Explain contract state, transaction callers, reverts, and access checks.
  - Identify the effect of external calls on a state-changing function.
safetyClass: high
---

# Solidity and the EVM

Separate Solidity syntax from EVM behaviour. This Skill is never a beginner's entry screen: if a learner cannot yet identify a value, condition, function, and collection, open the linked foundation bridge before showing contract source. For every state-changing function, ask who may call it, what state is read/written, whether an external call occurs, what reverts, and what the gas/resource implications are. Use local simulations or testnets only; never prompt for secrets or request transaction signing.
