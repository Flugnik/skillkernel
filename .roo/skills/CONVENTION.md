# Roo Skills Convention for SkillKernel

## Термины

- **Mode** — кто выполняет работу.
- **Roo Skill** — как выполняется повторяемая инженерная процедура.
- **Kernel Skill** — runtime-модуль внутри SkillKernel.

## Основные правила

1. Один skill = один workflow.
2. Названия skills — только в `snake_case`.
3. Skills должны быть узкими и прикладными.
4. Skills не заменяют modes.
5. Skills не заменяют проектные манифесты.
6. Проектные Roo Skills хранятся внутри репозитория.
7. Каждый skill должен иметь:
   - `SKILL.md`
   - `README.md`
8. Skills не должны дублировать архитектурные правила без необходимости.
9. Если workflow разовый, отдельный skill под него создавать не нужно.
10. Если skill становится слишком широким, его нужно разделить.

## Стартовый набор skills

- `manifest_writer`
- `minimal_diff_builder`
- `test_sync`
- `new_skill_scaffold`
- `repo_guard`