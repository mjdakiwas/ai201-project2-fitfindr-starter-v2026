"""
The FitFindr planning loop.

This is the file that makes FitFindr an agent rather than a script. It decides
which tool to run next based on what the last one returned.

If your loop calls all three tools no matter what comes back, you have a list
of function calls. A loop looks at the last result before it picks the next
step. **That branch is the graded part of this unit.**

Build and test your three tools in `tools.py` first. Then come here.

    python agent.py          runs both example paths below
"""

import re

import config
import trace
from tools import search_listings, suggest_outfit, create_fit_card
from generate import ModelUnavailable


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """
    A fresh session for one user interaction.

    The session is the single source of truth for a run. Every tool result goes
    in here, and the next tool reads it back out.

    You could pass values straight from one call to the next. It would work,
    and you would not be able to test it — you can't print a variable you have
    already overwritten. Going through the session is what makes the state
    visible, and unit 4 has you write a criterion about exactly that.

    Add fields if you need them.
    """
    return {
        "query": query,              # what the user typed
        "parsed": {},                # description / size / max_price you pulled out of it
        "search_results": [],        # everything search_listings returned
        "selected_item": None,       # the one you chose — goes into suggest_outfit
        "wardrobe": wardrobe,        # the user's wardrobe
        "outfit_suggestion": None,   # what suggest_outfit returned
        "fit_card": None,            # what create_fit_card returned
        "error": None,               # set when the run ended early
    }


# ── reading the query ─────────────────────────────────────────────────────────
#
# Regex and string splitting, not a model call. Three reasons: it costs no
# quota against a 15-requests-per-minute budget that two tools already spend
# twice a run; it gives the same answer every time, which unit 4's five tries
# depend on; and search_listings drops stopwords and scores on overlap anyway,
# so it has no use for a cleaner phrase than this produces.

_PRICE_PATTERNS = (
    re.compile(
        r"\b(?:under|below|less than|cheaper than|no more than|max(?:imum)?|up to)"
        r"\s*\$?\s*(\d+(?:\.\d{1,2})?)\b",
        re.I,
    ),
    re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)", re.I),
)

# Longest alternatives first, so "size us 8" doesn't come out as "8" and
# "size xxs" doesn't come out as "s".
_SIZE_PATTERNS = (
    re.compile(
        r"\bsize\s+(us\s*\d+(?:\.\d)?|w\d{2}|x{0,2}s|x{0,2}l|m"
        r"|extra small|extra large|small|medium|large|\d+(?:\.\d)?)\b",
        re.I,
    ),
    re.compile(r"\bin\s+(?:an?\s+)?(x{0,2}s|x{0,2}l|m)\b", re.I),
    re.compile(r"\b(w\d{2})\b", re.I),
    re.compile(r"\bus\s*(\d+(?:\.\d)?)\b", re.I),
)

_SIZE_WORDS = {
    "small": "S",
    "medium": "M",
    "large": "L",
    "extra small": "XS",
    "extra large": "XL",
}


def _normalise_size(raw: str) -> str:
    """"size  Medium" → "M", "size us 8" → "US 8"."""
    cleaned = " ".join(raw.split())
    return _SIZE_WORDS.get(cleaned.lower(), cleaned.upper())


def parse_query(query: str) -> dict:
    """
    Pull a description, a size and a price ceiling out of what the user typed.

    Each pattern that matches is **cut out of the string**, so the leftovers
    become the description. That matters: "under" is not a stopword, and a
    listing that says "great for layering under a graphic tee" would otherwise
    score a point for the word "under" in "under $30".

    Returns a dict with exactly the three keys session["parsed"] holds:
    description (str), size (str or None), max_price (float or None).
    """
    text = query or ""
    max_price = None
    size = None

    for pattern in _PRICE_PATTERNS:
        found = pattern.search(text)
        if found:
            max_price = float(found.group(1))
            text = f"{text[:found.start()]} {text[found.end():]}"
            break

    for pattern in _SIZE_PATTERNS:
        found = pattern.search(text)
        if found:
            size = _normalise_size(found.group(1))
            text = f"{text[:found.start()]} {text[found.end():]}"
            break

    # Cutting "size large" out of "cardigan, size large, max $40" leaves a
    # dangling ", ,". Harmless to the search, which only reads words, but it
    # shows up in the trace and reads like a bug.
    description = " ".join(text.split())
    description = re.sub(r"\s*,(?:\s*,)+", ",", description).strip(" ,")

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _nothing_found_message(parsed: dict) -> str:
    """
    The message the empty-search branch puts in the session.

    "No results" would not earn its place here — the user can't act on it. This
    names the filters that were actually applied, so what to change is in the
    message itself.
    """
    changes = []
    if parsed["max_price"] is not None:
        changes.append(f"raise the price above ${parsed['max_price']:g}")
    if parsed["size"]:
        changes.append(f"drop the size filter ({parsed['size']})")
    if parsed["description"]:
        changes.append(f"describe it differently than '{parsed['description']}'")

    if len(changes) > 1:
        advice = ", ".join(changes[:-1]) + ", or " + changes[-1]
    elif changes:
        advice = changes[0]
    else:
        advice = "say a bit more about what you're looking for"

    return f"No listings found under this price or size. You could {advice}."


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the loop once and return the finished session.

    Args:
        query:    what the user asked for, in plain language
                  (e.g. "vintage graphic tee under $30, size M").
        wardrobe: a wardrobe dict — get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py.

    Returns:
        The session dict. **Check session["error"] first** — if it isn't None,
        the run ended early and the later fields will still be None.

    ─────────────────────────────────────────────────────────────────────────
    THE BRANCH RULE (README, Milestone 2):

        If `search_listings` returns fewer than one result, store 'No listings
        found under this price or size' in the session state and stop the
        loop. Otherwise, save the top result and proceed to `suggest_outfit`.

    It lives in the "search" step below, and it is the only place this
    function decides anything. The empty path sets `error` and goes straight
    to "done", so `suggest_outfit` is never called with nothing and the last
    three fields stay None — which is what makes the two paths tell themselves
    apart in a trace.

    HOW THE STATE MOVES:

        Each step writes its result into `session`, and the next step reads
        its inputs back out of `session`. Nothing is handed straight from one
        call to the next, even where that would be shorter. A local variable
        that has been overwritten cannot be printed; a session field can,
        which is what makes a finished run one printable object rather than
        something you have to infer.

    ─────────────────────────────────────────────────────────────────────────
    IN UNIT 4 you come back and add two things:

      • Trace calls. One per step. `trace.step("search_listings", inputs=...,
        returned=...)` — see trace.py. Your README needs the output.

      • A handler for ModelUnavailable, so a bad key produces a message rather
        than a stack trace. The import is already at the top of this file.
    """
    session = new_session(query, wardrobe)

    step = "parse"
    iterations = 0

    while step != "done":
        # The stop condition. This loop is short enough that it should never
        # fire — which is the reason to keep it, not a reason to drop it.
        iterations += 1
        trace.check_iterations(iterations)

        if step == "parse":
            session["parsed"] = parse_query(session["query"])
            step = "search"

        elif step == "search":
            parsed = session["parsed"]
            session["search_results"] = search_listings(
                description=parsed["description"],
                size=parsed["size"],
                max_price=parsed["max_price"],
            )

            # ── THE BRANCH ───────────────────────────────────────────────────
            if len(session["search_results"]) < 1:
                session["error"] = _nothing_found_message(session["parsed"])
                step = "done"
            else:
                step = "select"

        elif step == "select":
            session["selected_item"] = session["search_results"][0]
            step = "suggest"

        elif step == "suggest":
            session["outfit_suggestion"] = suggest_outfit(
                session["selected_item"],
                session["wardrobe"],
            )
            step = "card"

        elif step == "card":
            session["fit_card"] = create_fit_card(
                session["outfit_suggestion"],
                session["selected_item"],
            )
            step = "done"

        else:  # a typo in a step name, caught loudly rather than silently
            raise RuntimeError(f"run_agent reached an unknown step: {step!r}")

    return session


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:
    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(f"  fit_card is {session['fit_card']!r} — it should still be None here")
        return

    item = session["selected_item"] or {}
    print(f"  found:    {item.get('title')} — ${item.get('price')} on {item.get('platform')}")
    print(f"  outfit:   {session['outfit_suggestion']}")
    print(f"  fit card: {session['fit_card']}")


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== A query the data can match ===")
    _show(run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    ))

    print("\n=== A query it can't ===")
    _show(run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    ))

    print(
        "\nThe second one should stop before the fit card. If both paths look "
        "the same,\nthe branch isn't doing anything yet."
    )
