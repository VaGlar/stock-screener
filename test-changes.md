---
description: Run the tester agent on the changes since the default branch (analyze mode)
---

Use the tester agent in analyze mode on the changes between the default branch (origin/main, or origin/master if that is what exists) and the current HEAD.

Do not pass the tester any summary of what the developer intended. It starts from the diff, TESTING.md if present, and its own instructions.

Extra instructions from me, if any: $ARGUMENTS

When it finishes, tell me the path of the report and show only its Verdict section.
