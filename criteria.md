# Acceptance criteria — FitFindr

Five criteria that say what "working" means for this agent, written in unit 3
**before** any results existed.

An acceptance criterion names a target: a number, a count, a rate, or something
a person could plainly observe. *"The agent handles errors"* is an opinion.
*"When search returns nothing, the agent stops before calling the second tool,
in 5 of 5 tries"* is a criterion.

Under each one, write a sentence or two on **why that target** and not a
stricter one. A reason that says something about your tools, your loop, or the
data earns credit; *"80% seemed reasonable"* does not.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

**Two are written for you. You write three.**

---

## 1. A matching query completes all three tools

Given a query that matches at least one listing, the agent completes all three
tool calls and returns a fit card — in at least 4 of 5 tries.

**Why this target:** My search's keyword overlap only matches query's words that is exact match to words in the listing data, so words that could semantically mean the same is not registered the same by the agent. For example, tshirt is not the same as t shirt so the agent will not evaluate a match. Therefore, there's a chance that a try will fail.
<!-- Why 4 of 5 and not 5 of 5? Something about your search, probably —
     "my search is a plain keyword match and some phrasings will miss" is a
     real answer. -->

---

## 2. An impossible query stops before the second tool

Given a query that matches no listings, the agent stops before calling
`suggest_outfit` and returns a message naming what to change — 5 of 5 tries.

**Why this target:** System is designed deterministic to stop running and return a message whenever there's no listing match, and no LLM runs. Therefore it will hit the criteria for 5 of 5 tries. 
<!-- Why is 5 of 5 reasonable here when criterion 1 isn't? What's different
     about this path? -->

---

## 3. Something about state

<!-- YOU WRITE THIS ONE.

     How would you know that the item your search found is the same item the
     next tool received? Name something countable or observable.

     This is the criterion people find hardest, because state failure doesn't
     look like state failure — it looks like a tool problem. Something that
     compares session["selected_item"] against what actually reached
     suggest_outfit is the shape you're after. -->
Given a successful search, the unique id of the `selected_item` set by `search_listings` matches the id passed as the `new_item` argument in `suggest_outfit` for 5 of 5 runs.


**Why this target:** Reading and passing keys within Python dictionary session state is deterministic code. We explicitly pass the exact dictionary from `selected_item` set by `search_listings` to `new_item` argument in `suggest_outfit`, so this will always occur with the same result for 5 of 5 runs.


---

## 4. Something about the fit card

<!-- YOU WRITE THIS ONE.

     The fit card calls a model, so the same input can produce different words
     each time. That's not a bug — it's the nature of the tool. So what would
     make it acceptable?

     Think about what you'd actually be unhappy to see. A caption that never
     mentions the price? Two different items producing the same opening
     sentence? A card longer than a caption anyone would post? Any of those can
     be turned into a number. -->
`create_fit_card` returns a string caption between 2 and 4 sentences long that explicitly includes the item's title/name, price, platform, and vibe — in at least 4 of 5 tries.


**Why this target:** I picked 4 of 5 because `create_fit_card` relies on a generative LLM. While prompt engineering instructs the model to include price, platform, and sentence bounds, non-deterministic model variance can cause it to omit a field or write too many sentence.



---

## 5. Your choice

<!-- YOU WRITE THIS ONE TOO.

     Pick something you actually care about getting right. Speed, the empty
     wardrobe path, what happens when the model can't be reached, whether the
     search respects a price ceiling — anything, as long as it names a number
     or an observable outcome. -->
Given a valid search result and an empty wardrobe array, `suggest_outfit` returns general styling advice without throwing an error or hallucinating non-existent closet items, allowing the pipeline to produce a valid fit card in at least 4 of 5 tries.


**Why this target:** Handling an empty list in Python is deterministic, but guiding the model to fall back on general styling principles rather than hallucinating user items relies on LLM prompt adherence. To account for that variable, I opted to succeed in 4 tries.



---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 4 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath it, like this:

         ## 4. Something about the fit card

         The fit card is different every time.

         **Why this target:** ...

         > **Revised in unit 4:** For 5 different items, the 5 fit cards share
         > no opening sentence.
         >
         > **Why revised:** "different" wasn't checkable — two cards that
         > differed by one word still counted. The new version is something I
         > can actually score.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "I said the empty search stops it 5 of 5 times, but I got 3 of 5,
            so 3 of 5 is more realistic."

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->
