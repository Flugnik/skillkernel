# SkillKernel project rules

1. Preserve layer boundaries:
   - core
   - runtime
   - router
   - skills
   - memory
   - contracts
   - events

2. Prefer the smallest viable change.
3. Do not introduce a new abstraction unless repetition or coupling clearly demands it.
4. Keep implementation explicit and inspectable.
5. Every behavior change should be accompanied by tests or a clear reason why tests were not added.
6. Do not silently change public contracts, manifest semantics, event formats, or routing behavior.
7. Follow existing naming and directory conventions before inventing new ones.
8. Optimize for maintainability by a small dev team, not for theoretical elegance.
9. When uncertain, preserve compatibility.
10. Summaries must name concrete files changed and concrete risks.
