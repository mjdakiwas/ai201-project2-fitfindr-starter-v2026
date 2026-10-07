"""
The three FitFindr tools.

Each one is a standalone function you can call and test on its own, before any
of them are wired into the loop. Build and test them one at a time — three
untested tools joined by a loop is one problem that looks like six, because you
can't tell which layer is lying to you.

    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)             → str
    create_fit_card(outfit, new_item)              → str

The Tool Inventory section of the README is the written spec for all three —
what goes in, what comes back, and what comes back when there is nothing to
give. The code below is meant to match it line for line.
"""

import re

import config
from generate import generate
from utils.data_loader import load_listings


# ── Tool 1: search_listings ───────────────────────────────────────────────────
_STOPWORDS = {"a", "an", "and", "the", "for", "with", "in", "of", "on", "to", "at", "by", "from", "is", "it", "this", "that", "these", "those", "as", "but", "or", "if", "then", "so", "not", "be", "are", "was", "were", "has", "have", "had", "do", "does", "did", "will", "would", "can", "could", "should", "may", "might", "must", "shall", "also", "just", "like", "about", "up", "down", "out", "off", "again", "more", "most", "some", "any", "all", "no", "nor", "too", "very", "such", "only", "own", "same", "other", "another", "each", "every", "both", "either", "neither"}

def _keywords(text: str) -> set[str]:
    """Lowercase words worth matching on, stopwords removed."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}

def _size_tokens(size: str) -> set[str]:
    """
    Every size label one size string stands for, uppercased.

    A listing's size is a claim about what fits, not a single label. "S/M" fits
    an S or an M, so it becomes {"S", "M"} and both match. "W30 L30" is two
    measurements, so each one is matched on its own. "US 8" also yields a bare
    "8", because a user asking for shoes types "size 8", not "size US 8".

    Parentheticals are a human note about the fit, not a size, so they go:
    "XL (fits oversized)" is just an XL.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", size or "")  # drop parentheticals
    tokens: set[str] = set()
    for part in cleaned.split("/"):
        part = " ".join(part.split()).upper()
        if not part:
            continue
        tokens.add(part)
        if part.startswith("ONE SIZE"):
            continue  # don't shred it into "ONE" and "SIZE"
        shoe = re.fullmatch(r"US\s*(\d+(?:\.\d+)?)", part)
        if shoe:
            tokens.add(shoe.group(1))
        else:
            tokens.update(part.split())
    return tokens

def _size_matches(wanted: str, listing_size: str) -> bool:
    """
    True when a listing's size satisfies the size the user asked for.

    Whole tokens are compared, never substrings. `"l" in "xl"` is True and
    `"s" in "us 9"` is True, which is how a search for a small top ends up
    returning shoes. Comparing token sets instead means "L" and "XL" are two
    different sizes, and "M" still matches "S/M".

    No size asked for means everything passes. One-size items fit everyone, so
    they pass whatever was asked for.
    """
    if not wanted:
        return True
    listing_tokens = _size_tokens(listing_size)
    if any(token.startswith("ONE SIZE") for token in listing_tokens):
        return True
    return bool(_size_tokens(wanted) & listing_tokens)

def _word_hit(word: str, haystack: set[str]) -> bool:
    """
    One keyword against one bag of words, forgiving a trailing plural.

    Trims one or two characters rather than using rstrip("s"), which strips
    *every* trailing s: "dresses" became "dresse" and matched nothing, so a
    search for "dresses" found none of the dresses a search for "dress" found.
    """
    return (
        word in haystack
        or f"{word}s" in haystack        # tee   -> tees
        or word[:-1] in haystack         # jeans -> jean
        or word[:-2] in haystack         # dresses -> dress
    )

def _score(listing: dict, wanted: set[str]) -> int:
    """
    How well one listing answers the keywords, as a number.

    Two points for a hit in the fields that describe what the thing *is* —
    title, category, style tags. One point for a hit in the softer fields —
    the seller's blurb, the colours, the brand. So "graphic tee" ranks the
    listing tagged `graphic tee` above one that happens to say "tee" in a
    sentence, which is the ordering a person would expect.

    `brand` is None on most listings, so it's coerced to "" rather than read
    directly.
    """
    strong = _keywords(" ".join([
        listing.get("title") or "",
        listing.get("category") or "",
        " ".join(listing.get("style_tags") or []),
    ]))
    weak = _keywords(" ".join([
        listing.get("description") or "",
        listing.get("brand") or "",
        " ".join(listing.get("colors") or []),
    ]))

    score = 0
    for word in wanted:
        if _word_hit(word, strong):
            score += 2
        elif _word_hit(word, weak):
            score += 1
    return score

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the listings data for items matching a description, and optionally a
    size and a price ceiling.

    This is the tool that doesn't call the model, which makes it the easiest one
    to test and the one to move onto MCP in unit 4.

    Args:
        description: keywords describing what the user wants
                     (e.g. "vintage graphic tee").
        size:        a size string to filter by, or None to skip size filtering.
                     Matched case-insensitively and token by token, so "M"
                     matches "S/M" but not "XL", and "8" matches "US 8" but not
                     "US 8.5". One-size items match any requested size. See
                     `_size_matches` for the rule.
        max_price:   maximum price, inclusive, or None to skip price filtering.

    Returns:
        A list of matching listing dicts, best match first.
        **Returns an empty list when nothing matches — an empty list, not None,
        and not an exception.** Your loop branches on this.

    Each listing dict has these fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand (str or None), platform

    Note that `brand` is None for most listings. That is deliberate and
    realistic — thrift listings often have no brand. Nothing here reads it
    without a `or ""` behind it.

    How it works:
        1. Load every listing with load_listings().
        2. Drop anything over max_price, or in the wrong size, when each is
           given.
        3. Score what's left by weighted keyword overlap with `description`.
        4. Drop anything scoring zero — a listing that shares no word with the
           query is not a worse match, it's not a match.
        5. Sort by score, highest first, cheapest first within a tie, and
           return at most config.SEARCH_RESULT_LIMIT of them.

        A description with no usable keywords in it ("under $20", or "") is
        treated as "no keyword filter" rather than as "match nothing", so the
        price and size filters still do their job on their own.

    Test it from a terminal before you move on:
        python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"
    """
    wanted = _keywords(description)

    scored: list[tuple[int, float, dict]] = []
    for listing in load_listings():
        price = listing.get("price") or 0.0
        if max_price is not None and price > max_price:
            continue
        if not _size_matches(size, listing.get("size") or ""):
            continue

        score = _score(listing, wanted) if wanted else 1
        if score == 0:
            continue
        scored.append((score, price, listing))

    scored.sort(key=lambda row: (-row[0], row[1]))
    return [listing for _, _, listing in scored[: config.SEARCH_RESULT_LIMIT]]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

_STYLIST_SYSTEM = (
    "You are a thrift stylist helping someone decide whether a secondhand find "
    "is worth buying. Name specific garments, colours and silhouettes. Never "
    "invent clothes the user has not said they own. Write two short plain "
    "paragraphs, no headings, no bullet points, no markdown."
)


def _describe_item(item: dict) -> str:
    """One listing, flattened into labelled lines a prompt can carry."""
    item = item or {}
    lines = [
        f"Title: {item.get('title') or 'untitled item'}",
        f"Category: {item.get('category') or 'unlisted'}",
        f"Size: {item.get('size') or 'unlisted'}",
        f"Condition: {item.get('condition') or 'unlisted'}",
        f"Colours: {', '.join(item.get('colors') or []) or 'unlisted'}",
        f"Style tags: {', '.join(item.get('style_tags') or []) or 'none'}",
        f"Price: ${item.get('price', '?')} on {item.get('platform') or 'an unlisted platform'}",
        f"Seller's description: {item.get('description') or 'none given'}",
    ]
    # brand is None on most listings — only claim one when there is one.
    if item.get("brand"):
        lines.insert(1, f"Brand: {item['brand']}")
    return "\n".join(lines)


def _describe_wardrobe(items: list[dict]) -> str:
    """The user's wardrobe as one bullet per piece."""
    lines = []
    for piece in items:
        details = "; ".join(
            bit for bit in (
                piece.get("category"),
                ", ".join(piece.get("colors") or []),
                ", ".join(piece.get("style_tags") or []),
            ) if bit
        )
        lines.append(f"- {piece.get('name') or 'unnamed piece'} ({details})")
    return "\n".join(lines)


def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest one or two outfits.

    This one calls the model, through `generate()`. You don't need to think
    about rate limits — the adapter handles pacing for you.

    Args:
        new_item: a listing dict — the item the user is considering.
        wardrobe: a wardrobe dict with an 'items' key holding a list of items.
                  **It may be empty.** Handle that.

    Returns:
        A non-empty string with outfit suggestions. **Never "" and never
        None** — criterion 1 needs all three tools to complete, and an empty
        return here would stall the next one.

        With an empty wardrobe it returns general styling advice — two outfits
        described in terms of staples — rather than raising or returning "".
        Unit 4 triggers the empty wardrobe on purpose, so the two branches are
        written to be told apart in the output: the stocked one names the
        user's pieces, the empty one opens by saying it doesn't know them.

    Criteria this answers (criteria.md):
        1 — completes and returns something the next tool can use.
        3 — `new_item` is only read here, never reassigned or mutated, so the
            id that arrives is the id that was sent.
        5 — the empty-wardrobe branch forbids second-person possessives in
            front of a garment, which is the thing that criterion scores as a
            hallucinated closet item.

    How it works:
        1. Read wardrobe['items'], defaulting a missing or None wardrobe to [].
        2. Empty: ask for general styling ideas for this item alone.
        3. Stocked: list the user's pieces in the prompt and ask for
           combinations that name them.
        4. Return the model's answer, falling back to a plain sentence if the
           model hands back nothing, so the return is never "".

    Test it from a terminal before you move on:
        python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
    """
    items = (wardrobe or {}).get("items") or []
    item_block = _describe_item(new_item)

    if not items:
        prompt = (
            "A shopper is considering this secondhand listing:\n\n"
            f"{item_block}\n\n"
            "They have told us nothing about what they already own, so you do "
            "not know a single thing in their closet.\n\n"
            "Open by saying you don't know what they own. Then describe two "
            "ways to wear this piece using staples in general — jeans, a white "
            "tee, black boots, that kind of thing. Close with one line on the "
            "vibe it gives and who it suits.\n\n"
            "Never say or imply they already own anything. Write 'pair it with "
            "straight-leg jeans', never 'pair it with your straight-leg jeans' "
            "and never 'the jeans you already have'. No second-person "
            "possessives in front of a garment at all."
        )
    else:
        prompt = (
            "A shopper is considering this secondhand listing:\n\n"
            f"{item_block}\n\n"
            "Here is what they already own:\n\n"
            f"{_describe_wardrobe(items)}\n\n"
            "Suggest two outfits built around the new item. Every other piece "
            "in each outfit must be one of the items listed above, named as it "
            "is written there. Say in one line why each outfit works — colour, "
            "silhouette or style. If the new item clashes with everything they "
            "own, say that plainly instead of forcing a match."
        )

    suggestion = generate(prompt, system=_STYLIST_SYSTEM).strip()
    return suggestion or (
        "Couldn't put an outfit together for this one — try a different "
        "listing, or add a few pieces to your wardrobe first."
    )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

_CAPTION_SYSTEM = (
    "You write short first-person captions for secondhand fashion finds, the "
    "kind a real person posts — not a product description and not an "
    "advertisement. Two to four sentences. No hashtags, no bullet points, no "
    "markdown, no headings."
)


def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Write a short caption someone would actually post about the find.

    This calls the model too.

    Args:
        outfit:   the outfit suggestion string from suggest_outfit().
        new_item: the listing dict for the item.

    Returns:
        A two-to-four sentence caption naming the item, its price, its
        platform and its vibe.
        If `outfit` is empty or whitespace, returns a message saying the outfit
        is missing and what to do about it, rather than raising — this tool is
        downstream of suggest_outfit, so an empty `outfit` means the step
        before it produced nothing. That message is an error, not a caption,
        and is not scored as one.

    Criteria this answers (criteria.md):
        1 — always returns a non-empty string, so the run completes.
        4 — the prompt asks for the four elements by name and bounds the
            length; the fallback below meets the same bar, so the guard can't
            be the thing that fails the criterion.

    The caption should read like a real post rather than a product description,
    mention the item and its price and platform once each, and be specific about
    the vibe.

    It should also come out **differently for different inputs**. Two settings
    at the top of `config.py` decide that: CACHE_ENABLED hands back an answer
    already given for an identical prompt, and TEMPERATURE at 0.0 gives the
    same words every time. TEMPERATURE is 0.9 here, and run_eval.py turns the
    cache off, so five evaluation tries are five real answers.

    How it works:
        1. Return early if `outfit` is empty or whitespace only.
        2. Build a prompt with the item details and the outfit.
        3. Call generate() and return the answer, with a plain fallback so the
           return is never "".

    Test it from a terminal before you move on:
        python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
    """
    if not (outfit or "").strip():
        return (
            "No fit card — there's no outfit to write about. Run "
            "suggest_outfit() first and pass what it returns in as `outfit`."
        )

    item = new_item or {}
    title = item.get("title") or "this piece"
    platform = item.get("platform") or "a resale app"
    vibe = ", ".join(item.get("style_tags") or []) or "secondhand"

    # "$18.0" is a tell that a machine wrote it. Whole prices lose the decimal.
    raw_price = item.get("price")
    price = f"{raw_price:g}" if isinstance(raw_price, (int, float)) else "?"

    prompt = (
        "Write a caption about a secondhand find.\n\n"
        f"The item:\n{_describe_item(item)}\n\n"
        f"How it's being worn:\n{outfit.strip()}\n\n"
        "Write it in the first person, like someone posting their own find.\n\n"
        "Four things must appear in it, once each:\n"
        f"  1. the item — say what the garment is in your own words. It is a "
        f"'{title}', but do not paste that title in; describe it the way you'd "
        f"say it out loud.\n"
        f"  2. what it cost — ${price}\n"
        f"  3. where it came from — {platform}\n"
        "  4. the vibe — name the era, mood, aesthetic or scene it belongs to "
        f"(it is tagged {vibe}). 'cute' and 'nice' do not count as a vibe.\n\n"
        "Write at least two sentences and at most four. Count them before you "
        "answer."
    )

    caption = generate(prompt, system=_CAPTION_SYSTEM).strip()

    # The fallback has to satisfy the same bar as a real caption — two to four
    # sentences naming the item, the price, the platform and the vibe —
    # otherwise the thing guarding the criterion is the thing that fails it.
    return caption or (
        f"Thrifted a {title} for ${price} on {platform}. "
        f"It has that {vibe} look I keep going back to. "
        f"Wearing it with {outfit.strip().rstrip('.')}."
    )
