# Understanding gate

Understanding is responsibility-building, not proof of authorship.

1. **Orientation** explains the selected basis, approved contribution contract, final Diff, verification evidence, policy result, and the highest-risk path.
2. **Assessment** asks new questions about those materials. The questions must not merely ask the contributor to repeat the Orientation.
3. Both records bind to the material snapshot they evaluated. Any material change to the entry, basis, contract, Diff, verification evidence, or policy result invalidates the old record.

`standard` depth uses concise explanation and short questions. `heightened` depth requires a fuller explanation of control/data flow, design trade-offs, failure modes, and test coverage. A project policy can require heightened treatment regardless of automatic signals.

The deterministic CLI records the evidence without generating the explanation or answers. The JSON Schema validates the portable shape; `reviewworthy understanding validate` is the canonical check for equal question/answer counts, exact material snapshots, and phase ordering:

```bash
reviewworthy understanding record .reviewworthy/contribution.json \
  --phase orientation --status passed \
  --summary "The contributor explained the selected boundary and its risks." \
  --topic contract --topic diff --topic verification --topic policy
reviewworthy understanding record .reviewworthy/contribution.json \
  --phase assessment --status passed \
  --question "Which invariant does the changed path protect?" \
  --answer "The input boundary preserves the existing caller contract."
reviewworthy understanding validate .reviewworthy/contribution.json
```

Assessment recording requires a passed Orientation bound to the current snapshot. The Skill remains responsible for teaching and for choosing non-repeating questions.
