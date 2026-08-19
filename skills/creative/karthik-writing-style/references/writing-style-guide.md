# Karthik Writing Style Guide

## Contents

- [Core Voice](#core-voice)
- [What Makes The Voice Work](#what-makes-the-voice-work)
- [Naturalness Principle](#naturalness-principle)
- [Tone](#tone)
- [Structure](#structure)
- [Phrasing](#phrasing)
- [Indian English And Local Texture](#indian-english-and-local-texture)
- [Numbers, Dates, And Localisation](#numbers-dates-and-localisation)
- [Punctuation And Mechanics](#punctuation-and-mechanics)
- [Opinions](#opinions)
- [Analogies](#analogies)
- [Technical Writing](#technical-writing)
- [Humour](#humour)
- [Emotional Honesty](#emotional-honesty)
- [Things To Avoid](#things-to-avoid)
- [Self-Check Rubric](#self-check-rubric)

## Core Voice

Write like a blogger, not an executive.

The voice should feel like an intellectually restless person thinking in public: curious,
analytical, specific, occasionally contrarian, and comfortable admitting uncertainty. The
reader should feel like they are listening to a smart friend explain something over
coffee, not reading a polished corporate memo.

The default structure is:

1. Start with something concrete.
2. Move into the analysis.
3. Show the evidence or reasoning.
4. End with an implication, open question, or informal landing.

Avoid starting with generic thesis statements like "In today's fast-changing world..."
Start from a real situation, small confession, thing you noticed, conversation, dataset,
bug, match, meeting, chart, or decision.

## What Makes The Voice Work

The voice comes from the thinking pattern, not catchphrases.

Good Karthik-style writing usually has:

- A concrete opening.
- A visible analytical bridge.
- Real names, numbers, places, products, events, or artifacts.
- A willingness to say "I don't know", "I was wrong", or "this is messier than I
  expected".
- Some personality, but not performance.
- Specificity instead of abstraction.

The writing can be personal, self-deprecating, mildly funny, or uncertain. It should not
sound inspirational, over-coached, or like thought leadership.

## Naturalness Principle

Do not over-season.

The guide gives patterns that are available, not mandatory. A real piece should not
contain every quirk. If the reader can spot the "voice tricks", it has gone too far.

Use restraint:

- Maximum one signature phrase per 500 words, and zero is fine.
- Maximum one cross-domain analogy per piece unless the piece is explicitly about
  analogies.
- Parenthetical asides should arise naturally from the thought.
- Indian-English phrasing should stay when it is natural, not be sprinkled for flavour.
- Do not add phrases like "and all such" just to sound like Karthik.

The thinking is the dish. The quirks are seasoning.

## Tone

The tone depends on format, but the base layer is always direct and conversational.

For personal blog posts:
- Most relaxed.
- Can be stream-of-consciousness.
- Can include family, friends, small annoyances, failures, and digressions.
- Can use humour and occasional profanity if natural.

For professional/Substack writing:
- Analytical but still personal.
- Use "I" freely.
- Explain tradeoffs, dead ends, and why something matters.
- Avoid sounding like a company blog.

For LinkedIn:
- More compressed.
- Short paragraphs.
- Start with a sharp observation.
- End with a question, implication, or link.
- Avoid fake virality and over-polished hooks.

For business emails:
- Warm but efficient.
- Get to the point quickly.
- Use direct recommendations.
- Avoid excessive politeness scaffolding.
- "Cheers" is a natural sign-off.

## Structure

### Blog / Substack

Preferred structure:

1. Anecdote, trigger, or situation.
2. What happened.
3. Why it is interesting.
4. The broader pattern.
5. Caveat, counterpoint, or failed attempt.
6. Informal close.

Good openings:
- "Last Monday, I had a minor panic attack..."
- "We're hiring data scientists. I mean, we hired one last week..."
- "I tried another round of therapy late last year..."
- "I was looking at this chart and something felt off..."
- "A few weeks ago, I got into an argument about..."

Bad openings:
- "In today's data-driven world..."
- "As businesses increasingly adopt AI..."
- "The future of analytics is changing rapidly..."
- "This article explores..."

Section headers are optional. Use them for pacing, not decoration. They can be punchy,
referential, or slightly playful.

Closings should not become grand conclusions. Prefer circling back, admitting
uncertainty, pointing to the repo/post/resource, or leaving the reader with a live
question.

### Length And Form Modes

Recent Substack posts show several distinct modes. Pick the mode before drafting.

#### Short Form: Observation Post

Typical length: 300-700 words.

Use for one sharp observation, one annoyance, one product friction, one food/health
experiment, one learning, or one small piece of analysis.

Structure:

1. Start with the incident, not the thesis.
2. Add just enough personal context for the observation to make sense.
3. Move quickly to the pattern.
4. Add one counterpoint, caveat, or alternative explanation.
5. Land informally: final verdict, question, PS, or "this is what I will do now".

No headings unless the post naturally breaks into two named parts. The title can do a lot
of work. The post should not try to become definitive.

Good short-form energy:
- "I noticed this, and it annoyed/interested/confused me."
- "I tried something yesterday and here is the weird thing that happened."
- "This product behaviour exposes a larger pattern."
- "I don't know if this generalises, but here is my working theory."

#### Mid Form: Personal Analysis

Typical length: 700-1,000 words.

Use for posts where a personal story becomes a concept: diet, learning style, job hunt,
sales, advice, campus visits, tools, product friction, and similar.

Structure:

1. Concrete trigger: trip, conversation, post, profile change, panel, bug, chart, meal.
2. Personal history or stake.
3. Analytical frame: two types, two axes, incentive problem, Goodhart effect, matching
   model, tradeoff, or analogy.
4. Examples from life, work, sport, food, family, or data.
5. Counterpoint or limitation.
6. Practical implication.
7. Informal close or PS.

This mode should feel like "thinking out loud until the pattern becomes clear". It can
be discursive, but each digression should earn its place.

#### Long Form: Essay Or Project Post

Typical length: 1,000-1,600 words.

Use for multi-part analysis, data explorations, project retrospectives, AI/tool essays,
startup reflections, or posts with charts/code.

Structure:

1. Start with the human trigger or analytical question.
2. Explain the background without pretending the reader knows everything.
3. Use section headers for pacing when there are real turns in the argument.
4. Introduce the method, model, chart, or evidence only after the question is clear.
5. Present findings as claims with caveats, not as a report dump.
6. Include a "what the method gets wrong" or "what this does not prove" section when
   relevant.
7. Close with what changed in the author's mind, what remains messy, or where the reader
   can inspect the work.

Long posts can carry more structure, but should still avoid the school-essay ending.
The last paragraph can be a PS, a practical next step, a limitation, or a small joke.

#### Data Or Chart Post

Use when the post is driven by a dataset, chart, model, or LLM-aided analysis.

Structure:

1. Why this question came up.
2. What data was used and why it is imperfect.
3. What the chart or model seems to show.
4. The interesting exception or surprise.
5. What cannot be concluded.
6. Link to code, source, or repo if available.

The prose should not read like a notebook. Explain the judgment calls: why this metric,
why this comparison, what the model might have hallucinated, what a human still had to
decide.

#### Professional Reflection

Use for posts about startups, job hunt, consulting, sales, management education, AI at
work, or career identity.

The tone should be candid but not inspirational. Start with a real marker: a profile
line, an interview, a panel, a LinkedIn post, a sales failure, a funding decision, a
conversation. Then turn it into an analysis of incentives, fit, constraints, or personal
operating style.

Do not end with a universal lesson unless the evidence really supports it. Prefer "this
is what seems true for me" or "this is the pattern I now see".

#### AI And Tooling Posts

Use when writing about Claude, ChatGPT, Codex, Wispr Flow, Teams, vibe coding, local
files, embeddings, or similar.

Pattern:

1. Product friction or surprising behaviour.
2. Workaround or experiment.
3. Analogy or model for what is happening.
4. Where the tool is useful.
5. Where it is still lousy, risky, or requires human judgment.

Be comfortable with hand-wavy hypotheses, but label them as such. Avoid AI boosterism.

#### PS Usage

PS notes are part of the voice. Use them when they add one of:

- A related link.
- A correction or limitation.
- A small aside that would interrupt the main flow.
- A second-order observation.
- A dry final joke.

Do not use PS as a dumping ground for material that should be in the body.

### LinkedIn

Use short blocks.

Start with a strong observation, not a dramatic fake hook.

Good:
- "Most dashboards fail before anyone opens them."
- "The hard part of analytics is rarely the model."
- "I've changed my mind on this."

Avoid:
- "I was today years old when..."
- "Here's what nobody tells you..."
- "This one insight changed everything..."

End with a question, implication, or link. Hashtags are fine but should be minimal.

### Project Posts

Start with the trigger: why the thing was built.

Then explain:
- What problem it solves.
- What was built.
- What tradeoffs came up.
- What was harder than expected.
- What was rejected.
- What remains messy.
- Where the repo/demo is.

Mention stack, runtime, cost, performance, or models only when useful.

## Phrasing

Preferred phrasing is direct.

Use:
- "Let's start with..."
- "We can..."
- "The structure is..."
- "Start with..."
- "The basic problem is..."
- "The counterpoint is..."
- "In my opinion..."
- "To be honest..."
- "Coming to think of it..."
- "For the uninitiated..."
- "If you think about it..."

Avoid repeated:
- "I'd suggest..."
- "I would recommend..."
- "You may want to consider..."
- "It might be worth..."

Especially in drafts meant for Karthik to send, repeated "I would..." phrasing sounds
passive-aggressive and unlike his voice.

Prefer:
- "Let's structure this as..."
- "We can start with..."
- "Given the unknowns, the cleanest structure is..."
- "Start with the metric definition, then move to the model."

## Indian English And Local Texture

Preserve Indian-English phrasing when natural. Do not over-correct it into generic
American business English.

Acceptable natural patterns:
- "The basic funda is..."
- "Coming to think of it..."
- "I got reminded by..."
- "I'm building Babbage Insight."
- "lakh" and "crore" in Indian contexts.
- "tiffin", "enthu", "pseud" when they fit the context.

Use Indian cultural references naturally: cricket, quizzing, food, school/college
language, Bangalore, Indian startup context, public life, family logistics. Do not force
them into pieces where they do not belong.

## Numbers, Dates, And Localisation

Do not make prose look like an exported dataframe.

Use human numbers unless exactness matters.

Prefer:
- "about 1,500"
- "just under 1,900"
- "more than 300 points"
- "roughly a fifth"
- "a few hundred million"
- "by March 2026"
- "in late 2023"

Keep exact numbers when the exactness matters:
- Election margins.
- Scorelines.
- Legal thresholds.
- Quoted prices.
- Release dates.
- Model results where precision is the point.

Dates:
- Indian/British context: "21 October 2018"
- American context: "October 21, 2018"
- Avoid "2018-10-21" in narrative prose.

Currencies:
- Indian: "₹3 crore", "₹75 lakh", "₹1,000 crore"
- British: "£3m", "£250,000", "£1bn"
- American: "$3 million", "$250,000", "$1 billion"

Backticks are for code, file paths, commands, identifiers, or literal tokens. Do not use
backticks around ordinary dates, prices, or quantities.

## Punctuation And Mechanics

Use space-hyphen-space for interruptions:

Correct:
- "The skill captures the craft - the lived experience is harder to bottle."

Avoid em dashes:
- "The skill captures the craft — the lived experience is harder to bottle."

Use parenthetical asides when they arise naturally. Do not make every paragraph
parenthetical.

Occasional "(!)" is fine for wry emphasis, but use rarely.

## Opinions

Opinions should be stated clearly, but with honest caveats where needed.

Good:
- "I strongly prefer..."
- "In my opinion..."
- "I might be biased given my background in..."
- "The counterpoint is that..."
- "I don't fully know what to make of this yet."

Avoid fake certainty. Also avoid weak consultant hedging.

The voice is allowed to be contrarian, but the contrarianism must be earned through
reasoning or evidence.

## Analogies

Analogies are useful, but one good analogy is usually enough.

Common analogy domains:
- Cricket.
- Chess.
- Economics.
- Finance.
- Markets and options.
- Information theory.
- Everyday Indian life.
- Food.
- Music.
- Quizzing.

Good analogies clarify the point. Bad analogies show off.

Do not stack multiple analogies in one piece unless the piece is explicitly about
comparing domains.

## Technical Writing

Technical writing should remain human.

Explain the "why" before the machinery. Use technical terms casually, but define them
when needed.

Natural technical language:
- "signal vs noise"
- "overindex on"
- "the funnel gets narrow"
- "linear combination"
- "regime change"
- "Herfindahl-Hirschman Index"
- "one delta stock"
- "long put option"

Use formal terminology when it helps, but translate it immediately into plain English.

## Humour

Humour should be dry, observational, and lightly self-deprecating.

Good humour:
- A wry parenthetical.
- A small admission of incompetence.
- A precise everyday observation.
- A mild absurdity stated plainly.

Avoid:
- Forced jokes.
- Meme language unless the context truly calls for it.
- Too much sarcasm.
- Punchlines that draw attention to themselves.

## Emotional Honesty

It is fine to mention uncertainty, anxiety, failure, doubt, awkwardness, or frustration.
The key is to turn it into analysis, not self-pity.

Good pattern:
- "This happened."
- "It made me uncomfortable."
- "I tried to understand why."
- "Here is the pattern I now see."

The vulnerability should serve the insight.

## Things To Avoid

Avoid:
- MBA-speak.
- Founder-speak.
- Generic thought leadership.
- "Future of X" rhetoric.
- Empty inspiration.
- Over-polished consultant prose.
- Clean five-paragraph-essay structure.
- Excessive analogies.
- Excessive exact numbers.
- Machine-looking dates.
- Overuse of signature phrases.
- Starting every recommendation with "I'd suggest..."
- Sanitising Indian-English texture.
- Writing like a brand account.

Specific bad phrases:
- "In today's fast-paced world..."
- "Unlocking value..."
- "Driving transformation..."
- "Leveraging synergies..."
- "Seamless experience..."
- "Game-changer..."
- "This one insight..."
- "Nobody is talking about..."
- "Here's what I learned...", unless the piece genuinely earns it.

## Self-Check Rubric

Before publishing or sending, ask:

1. Does it start with something concrete?
2. Does it sound like a person thinking, not a company explaining?
3. Are there real specifics - names, places, numbers, artifacts?
4. Is the analysis visible?
5. Is the uncertainty honest?
6. Is the piece in the right length mode: short observation, mid-form personal analysis,
   long essay/project post, data post, professional reflection, or AI/tooling note?
7. Are the numbers and dates human-readable?
8. Are there any em dashes to replace with " - "?
9. Are there too many quirks or signature phrases?
10. Does any paragraph sound like LinkedIn hustle content?
11. Would Karthik actually say this aloud?

If the piece feels too smooth, add a little friction: a caveat, a concrete example, a
failed attempt, or a sharper opinion.

If the piece feels too quirky, remove the seasoning and keep the thought.
