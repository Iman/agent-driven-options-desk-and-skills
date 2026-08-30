---
description: Mark every open paper position against the newest chain and report the running result
---

1. `optiondesk forward status` to see what is open.
2. `optiondesk chain SYM --expiry ...` for any underlying whose newest
   chain predates the last mark.
3. `optiondesk forward mark`
4. Report each position's mark, and separately list anything that came
   back unmarkable with the reason. A position with a leg missing from the
   later chain is not marked at zero, and reporting it as flat would be
   the most flattering possible error.

State once that these are mid quotes rather than fills, so a real entry
would have crossed the spread on every leg.
