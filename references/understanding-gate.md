# Understanding gate

Understanding is responsibility-building, not proof of authorship.

1. **Orientation** explains the selected basis, approved contribution contract, final Diff, verification evidence, policy result, and the highest-risk path.
2. **Assessment** asks new questions about those materials. The questions must not merely ask the contributor to repeat the Orientation.
3. Both records bind to the material snapshot they evaluated. Any material change to the entry, basis, contract, Diff, verification evidence, or policy result invalidates the old record.

`standard` depth uses concise explanation and short questions and must cover the rubric categories `behavior`, `invariant`, and `test`. `heightened` depth additionally requires `flow`, `tradeoffs`, `failures`, and `regressions`. A project policy can require heightened treatment regardless of automatic signals.

The deterministic CLI records the evidence without generating the explanation or answers. The JSON Schema validates the portable shape; `reviewworthy understanding validate` is the canonical check for rubric categories/evidence shape, equal question/answer counts, exact material snapshots, and phase ordering. It cannot prove that the contributor's explanation is correct:

```bash
reviewworthy understanding record .reviewworthy/contribution.json \
  --phase orientation --status passed \
  --summary "The contributor explained the selected boundary and its risks." \
  --rubric behavior="The boundary rejects invalid input." \
  --rubric invariant="Existing callers retain their behavior." \
  --rubric test="The focused test covers the regression." \
  --topic contract --topic diff --topic verification --topic policy
reviewworthy understanding record .reviewworthy/contribution.json \
  --phase assessment --status passed \
  --question "Which invariant does the changed path protect?" \
  --answer "The input boundary preserves the existing caller contract." \
  --rubric behavior="The invalid input follows the guarded path." \
  --rubric invariant="The caller contract remains unchanged." \
  --rubric test="The regression command covers the changed path."
reviewworthy understanding validate .reviewworthy/contribution.json
```

Assessment recording requires a passed Orientation bound to the current snapshot. The Skill remains responsible for teaching and for choosing non-repeating questions.
