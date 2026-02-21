from typing import Dict, List, Optional


class BoardRenderer:
    @staticmethod
    def render_task_board(
        backlog_items: List[str],
        done_items: List[str],
        bridge: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        def task_lines(items: List[str], checked: bool = False) -> List[str]:
            if not items:
                return ["- [ ]"] if not checked else ["- [x]"]
            mark = "x" if checked else " "
            return [f"- [{mark}] {item}" for item in items]

        lines = ["---", "kanban-plugin: list", "---", ""]

        if bridge:
            lines.extend(
                [
                    "## Now",
                    *task_lines(bridge.get("now", []), checked=False),
                    "",
                    "## Paused",
                    *task_lines(bridge.get("paused", []), checked=False),
                    "",
                    "## Captured from Reality",
                    *task_lines(bridge.get("captured", []), checked=False),
                    "",
                    "## Next 3",
                    *task_lines(bridge.get("next", []), checked=False),
                    "",
                ]
            )

        lines.extend(
            [
                "## Focus",
                "",
                "",
                "## Creative",
                "",
                "",
                "## Light",
                "",
                "",
                "## Recovery",
                "",
                "",
                "## Reflect",
                "",
                "",
                "## Backlog",
            ]
        )

        lines.extend(task_lines(backlog_items, checked=False))
        lines.extend(["", "## Reconsider", "- [ ]", "", "## Done Today"])
        lines.extend(task_lines(done_items, checked=True))
        lines.extend(
            [
                "",
                "## Admin",
                "- [ ]",
                "",
                "",
                "%% kanban:settings",
                "```",
                '{"kanban-plugin":"list","list-collapse":[false,null,false,false,false,false]}',
                "```",
                "%%",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def goals_board_template() -> str:
        return """---
kanban-plugin: board
---

## Short term

- [ ] Learn Music theory
- [ ] Build my Personal Brand [[Personal Youtube]]
- [ ] Build Some projects for each discipline Computer science
- [ ] Learning Russian
- [ ] Learn to drive
- [ ] Learn testing
- [ ] CCNA
- [ ] Learn japense
- [ ] Theory Vs practice bot


## Medium Term

- [ ] Find a Junior development Job
- [ ] Save for buying a house
- [ ] Saving for staying in an apartment in a good area


## Long Term

- [ ] Move to mid-level position
- [ ] Earn 10k month
- [ ] Build A security fund


## Come back to

- [ ] Fix up website to put learning
- [ ] Finish the Market analysis bot to find hosuing




%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false]}
```
%%
"""
