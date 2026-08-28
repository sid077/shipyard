# Scouting sweep 002 — productivity, lifestyle, fitness

**Pass 1 of 2. Breadth, not depth.** Goal: ~12 leads worth a second look, plus an
explicit reject pile. Nothing here is validated. Every claim below is tagged with
the URL I actually opened; where I could not open a source I say so.

**Studio constraints applied as a filter throughout:** Expo/React Native, offline-first,
one-time unlock or RevenueCat sub, on-device camera / local notifications / local
storage / platform vision+speech APIs, 3–6 weeks of spec-able build, organic store
search for distribution, no marketplace, no licensed content, no seeded dataset, no
regulated advice, no support desk.

Date of sweep: 2026-08-28.

---

## Status

- [ ] Leads gathered
- [ ] Reject pile recorded

---

## Method note / limitation

`play.google.com` listing pages are **blocked by the network proxy** from this
environment (`proxy refused the connection`), so I could not read Play install
counts first-hand. Where an install count appears below it came verbatim out of a
search-result snippet, and is marked `[snippet, not fetched]`. Apple App Store
pages and most blogs/Reddit fetch fine. Second pass should re-verify install
counts from a machine that can reach Play.

---

## Cross-cutting finding — read this before the leads

**The single most important data point in this sweep is Cal AI.** Two teenagers
built a photo-based calorie tracker in March–May 2024 using third-party AI APIs
(not a proprietary model), hit >1M downloads, roughly $10M collected by May 2025,
$50M+ ARR, bootstrapped with no outside funding, and sold to MyFitnessPal — deal
closed December 2025, announced March 2026.

- https://techcrunch.com/2025/03/16/photo-calorie-app-cal-ai-downloaded-over-a-million-times-was-built-by-two-teenagers/
- https://www.cnbc.com/2025/09/06/cal-ai-how-a-teenage-ceo-built-a-fast-growing-calorie-tracking-app.html
- https://superframeworks.com/case-study/cal-ai
- https://getlatka.com/companies/calai.app (claims $40M ARR 2026 — Latka figures are self-reported, treat as soft)

Two conclusions, and they point in opposite directions:

1. **The pattern is proven and it is exactly this studio's shape.** Point the
   camera at a thing → get structured data back → subscription. Small team, no
   backend of consequence, no seeded dataset, organic distribution. That is the
   template to look for in every lead below.
2. **Calorie tracking specifically is now closed.** The winner exited to the
   incumbent and is being merged with MyFitnessPal's 20M-food database. Do not
   propose a food-photo app. Whatever the studio builds, the "camera → structured
   data" wedge must point at a noun nobody has claimed yet.

Corollary risk to test in pass 2: Cal AI's inference ran on third-party AI APIs,
i.e. **a backend and a per-call cost**. The studio's brief says offline-first and
"every dependency on a backend is a liability". Any camera→AI lead below inherits
this tension and it must be resolved before build, not during. On-device vision
(Apple Vision framework / ML Kit) handles OCR, barcodes and simple object
detection well and offline; it does not handle open-ended "what is this meal".
**Prefer leads where on-device OCR/barcode is enough.**

---

## Leads

### L1 — Medication reminder for the multi-med household (paywall-squeeze play)

**What:** An offline, one-time-unlock pill/dose reminder that handles an unlimited
number of medications, complex schedules, and a second person (an ageing parent),
with no account and no subscription.

**Who for:** Caregivers managing a parent on six-plus prescriptions, and anyone
polypharmacy-adjacent who resents a subscription for a local notification.

**Demand signal — this is the strongest single wedge I found today:**
In **January 2026 Medisafe eliminated its unlimited-medication free tier; the free
version now allows only two medications.** For a caregiver whose parent is on six
or more prescriptions, premium becomes effectively mandatory.
- https://www.yougot.ai/blog/technology/app-comparisons/medisafe-alternative-for-medication-reminders
- https://be-tended.com/guides/medication-reminder-apps-caregivers/

Reported complaint pattern is friction, not bugs: notification fatigue from
multiple reminders per medication, onboarding burden of manually entering every
medication, and feature overload for people who want something simple. Also
reported: after an update users could not change daily medications without
repeatedly saving. Medisafe's Play listing is
https://play.google.com/store/apps/details?id=com.medisafe.android.client
(**could not fetch — proxy blocked**; install count unverified).

**Why it fits the studio:** local notifications + local storage, literally the two
cheapest capabilities on the list. No backend. No dataset — the user types their
own medication names, so no drug database is required (and typing them means no
licensing problem).

**The thing that could kill it:** this is close to the **regulated-advice** line.
Reminding someone to take a pill they already have is fine; suggesting doses,
interactions, or anything resembling clinical guidance is not. The spec must be
brutally clear that the app never interprets. Also, a missed-dose notification for
an elderly parent is exactly the kind of feature that generates support email when
it fails, and there is no support desk. **Both need resolving in pass 2.**

**Verify in pass 2:** confirm the Jan-2026 free-tier change from Medisafe's own
pricing page, not a competitor's comparison blog (both sources above are
commercially interested). Pull actual 1-star reviews since Jan 2026. Check whether
Apple's and Google's own built-in health apps already do this for free.

---

### L2 — Wardrobe cataloguing (category has proven willingness to pay, incumbents are split)

**What:** Photo-catalogue your clothes, track what you actually wear, plan outfits.

**Who for:** People with large wardrobes who over-buy and want cost-per-wear.

**Demand signal — real prices, real money, multiple funded players:**
- **Whering** — free, no paid tier at all. https://whering.co.uk/best-wardrobe-apps-2025
- **Acloset** — free only to 100 items, then paid; reported from £30/yr basic up to
  £120/yr "expert", with a £2.99/mo tier cited elsewhere (sources disagree — verify).
- **Indyx** — wear analytics gated behind **$60/yr or $7/mo**.
  https://www.myindyx.com/versus/acloset-vs-whering
- Enough competitors to sustain a whole SEO comparison industry (Vesta, StylePal,
  Nouva all publishing "vs" posts), which is itself a signal that acquisition
  traffic here is contested. https://vestatheapp.com/blog/vesta-vs-indyx-whering-acloset

**Named complaint:** Acloset's AI auto-tagging is inconsistent — "getting category
right more often than color". A tagging-accuracy wedge is plausible.

**Why I am cautious:** the biggest player is **free**, which caps price. And the
core loop needs background removal + attribute tagging on garment photos, which is
the "open-ended vision" problem flagged above, not the cheap OCR case.

**Verify in pass 2:** Stylebook is reportedly a **paid one-time** wardrobe app —
if true it is the single best proof that this category supports the studio's
preferred model. Confirm its price on its own App Store page. Pull 1-star reviews
for Whering and Acloset.

---

### L3 — Music practice logging (thin incumbents, unproven demand)

**What:** Practice timer + session log + recordings for people learning an instrument.

**Demand signal — weak, and I want to be honest that it is weak.** The space is
full of very small, very recent App Store entries with no dominant player:
Practice Log (https://apps.apple.com/us/app/practice-log/id6757978130), Only
Practice, Instrumentive (https://apps.apple.com/us/app/-/id1491754465), Tempo
Tracker, Simple Practice Tracker, Music Practice Journal, plus Modacity and
Pract.is. https://pract.is/blog/best-apps-to-track-your-music-practice-time-5-options-compared

**Read:** a crowd of tiny apps and no big winner usually means the category does
not monetise, not that it is unclaimed. I found **no** review counts, install
counts, or complaint threads to support demand. Carrying it as a lead only because
the build fits the studio perfectly (timer, local storage, mic). **If pass 2 finds
no paying-user evidence, drop it fast.**

---

### L4 — Craft project tracker (knitting/crochet) — small but people pay, and pay *one-time*

**What:** Row counter + project tracker + pattern/notes store for knitters and
crocheters. Offline by nature — people knit on trains and in waiting rooms.

**Demand signal — actual published price ladders, including a lifetime tier:**
- **Knit With Me: Project Tracker — $1.99/mo, $8.99/yr, $18.99 lifetime.**
  https://apps.apple.com/us/app/id6443686048
- YarnBuddy — free with IAP, one of the established names.
  https://apps.apple.com/app/id1267678125
- Knitting Counter: Row Tracker — premium tier adds Apple Watch, pattern viewer,
  activity logs. https://apps.apple.com/lb/app/knitting-counter-row-tracker/id6464153799
- A verbatim 1-star-adjacent review of Easy Knitty: *"knocked down one star bc
  sometimes it doesn't realize I have the premium version"* — i.e. receipt-validation
  failures, which is a RevenueCat-shaped problem the studio would handle better.
  https://apps.apple.com/us/app/easy-knitty-row-counter-knit/id1557552992

**Why it is interesting despite being small:** the category has *already proven*
users will pay a **one-time $18.99 unlock** — the exact monetisation the studio
prefers — and the whole product is counters, timers and local storage. Genuinely
3–6 weeks. Zero backend. Zero dataset. Zero regulatory exposure. Craft communities
(Ravelry, r/knitting) are dense and word-of-mouth-driven, which suits organic
distribution.

**Why I am not more excited:** the ceiling is low, it is crowded with near-identical
entries, and I have **no install or revenue figures** — only price cards. Also
Ravelry is the de-facto community hub and any pattern-library ambition runs
straight into content the studio does not own.

**Verify in pass 2:** review counts on YarnBuddy and Knit With Me (proxy for
install base); r/knitting and r/crochet threads on what people actually complain
about; whether Ravelry integration is required to be taken seriously (it would be
a dependency the studio cannot control).

---

### L5 — Screen-time / friction-before-opening apps — **high price ceiling, probably unbuildable here**

**Demand signal is the strongest price point in the whole sweep:** **Opal charges
$99.99/year.** https://waittounlock.com/blog/screen-time-vs-app-blockers ·
https://alternativeto.net/software/opal-focus
one sec (https://apps.apple.com/app/id1532875441) uses a delay-and-breathe
intervention rather than a block, and a study found six weeks of use cut targeted
social-media usage by **57%** — covered in Fortune:
https://fortune.com/well/2023/03/06/one-sec-app-can-help-cut-your-social-media-use

**And the killer, stated plainly in the competitive coverage:** many people churn
through three or four of these apps and conclude nothing works, because *you*
control the off switch and every limit can be ended, ignored or uninstalled.

**Why this is filed as a lead-with-a-warning rather than a lead:** $100/yr proves
real willingness to pay for this pain. But blocking/delaying other apps requires
iOS **Family Controls / DeviceActivity / ManagedSettings** entitlements and an
Android accessibility-service or usage-stats permission — native, platform-specific,
entitlement-gated work that is a poor fit for an Expo codebase shipping to both
stores from one source, and Apple gates the entitlement by request. **My honest
expectation is that pass 2 kills this on buildability.** It is in the file because
the price signal is too loud to omit, and because if there is a cheap RN-shaped
version of the *friction* idea, the willingness-to-pay is already demonstrated.

---

### L6 — Scan-a-page → vocabulary flashcards (best pure on-device-OCR fit found)

**What:** Point the camera at a page of a foreign-language book, menu or sign; the
app OCRs it, you tap the words you don't know, and it builds a spaced-repetition
deck. Entirely offline after capture.

**Who for:** Intermediate language learners reading native material — the group
that has outgrown Duolingo and is doing "sentence mining" by hand.

**Demand signal:** the workaround already exists and people are doing it the hard way.
- **EveryWord — AI Flashcards** scans books, generates audio, makes Anki-style
  cards from photo recognition. https://apps.apple.com/gd/app/everyword-ai-flashcards/id1642461047
- **BookToAnki** exists purely to extract vocabulary from whole books so learners
  don't have to type words out manually — a desktop-ish tool whose entire pitch is
  removing manual transcription. https://alternativeto.net/software/booktoanki/about
- Anki/AnkiDroid is the free open-source incumbent with **6000+ pre-made shared
  decks**, and the well-known complaint is that its mobile card-*creation* flow is
  miserable. (AnkiMobile on iOS is notably a paid app — verify its price in pass 2;
  it is one of the few proven paid learning tools.)

**Why it fits:** OCR is the one vision task that runs **fully on-device, offline,
free and reliably** on both platforms (Apple Vision / ML Kit text recognition).
No backend, no per-call AI cost, no licensed content — the user supplies the book.
Spaced repetition is a well-specified algorithm. This is a genuinely 3–6-week scope.

**Supporting monetisation evidence:** **77% of consumer spending on iOS books-and-
reference apps came from one-time purchases**, not subscriptions — the studio's
preferred model is the *dominant* model in exactly this category.
https://www.statista.com/statistics/1483573/app-spending-subscriptions-and-one-time-purchase-by-category

**Risks to test:** translation/definition lookup is the obvious next feature and it
needs either a dictionary the studio does not own or an online API — the wedge has
to survive without it. Anki is free and beloved. Non-Latin scripts (Japanese,
Chinese, Arabic) are where demand is densest and OCR is hardest.

---

### L7 — ADHD executive-function tools (loud demand, no winner, but AI-shaped competitors flooding in)

**What:** Task initiation and time-blindness aids — visual timers, routine
micro-step breakdowns, planned-vs-actual time tracking.

**Demand signal:** a dense and *recent* cluster of App Store entries all naming the
same two pains in their own listing copy, which means they are all bidding for the
same search terms:
- ADHD Manage Time Tasks To-do — pitches "smart reminders based on energy levels
  for time blindness". https://apps.apple.com/us/app/-/id6473707647
- ForFocus: ADHD Pomodoro Timer — "beats time-blindness, procrastination and
  distraction with visual timers, energy-level tasks, AI task breakdowns".
  https://apps.apple.com/us/app/-/id6747602434
- ADHD Routine — micro-task routine breakdown, visual timers, hourly reminders,
  planned-vs-actual time. https://apps.apple.com/qa/app/adhd-routine-self-organization/id6745971858
- ADHD Lifehacks For Adults Pro. https://apps.apple.com/app/id1624890673
- Non-app demand leaking into other formats: a paid Gumroad **ADHD iPad planner
  template**, i.e. people paying for a PDF because no app fits.
  https://remarkabletemplates.gumroad.com/l/ADHD-Planner-2025-iPad-Ultimate-Digital-Organizer-Focus-Efficiency

**Caveats I could not resolve:** I did **not** find the r/ADHD threads I was looking
for — search returned listings and SEO round-ups, not community voice. Given r/ADHD
is one of the largest health subreddits, pass 2 must go to the source directly;
this lead is currently built on supply-side evidence (lots of apps) rather than
demand-side (people asking). Supply without demand evidence is how the music-practice
lead (L3) got weak, and the same doubt applies here. Also: "AI task breakdown" is the
feature everyone is shipping and it implies an LLM backend the studio doesn't want.
The differentiated version is probably the *non*-AI one — a great visual timer.

**Also note the support-burden risk:** an ADHD audience is a high-empathy, high-
contact audience. One operator, no support desk.

---

### L8 — Offline trip/packing organiser — **thin, but the incumbent is visibly weak**

**Demand signal, mostly negative-space:** TripIt is the incumbent and is taking real
damage. Reported: **a server outage on 22 December 2025 with 120+ down reports**,
support that failed to respond or offer goodwill, users auto-renewed into annual
subscriptions without warning with **nonrefundable fees**, itinerary email parsing
that misses items, and an interface widely called dated.
https://www.trustpilot.com/review/www.tripit.com ·
https://www.wandrly.app/reviews/tripit · https://www.going.com/guides/tripit-review ·
https://www.pilotplans.com/blog/review-of-tripit

**Why it is only half a lead:** TripIt's actual value is *automatic itinerary parsing
from forwarded confirmation emails* — that is a mail backend plus airline-format
knowledge, and it is precisely what the studio cannot maintain with nobody on call.
Strip that out and you have a packing list, which is a free-template problem. The
interesting sliver is **offline access to your own trip documents**, since the Dec-2025
outage is a clean argument for local-first. Weakest of the leads; carried for the
outage evidence, which is a reusable argument for offline-first positioning generally.

---

## Reject pile

### R1 — Strength-training workout logger — **REJECT, saturated by excellent cheap incumbents**
Hevy Pro is **$2.99/mo, $23.99/yr, or $74.99 lifetime**; Strong PRO is $4.99/mo,
$29.99/yr, $99.99 forever. Both average **~4.9 stars across many thousands of
ratings**, and Hevy is fully usable and ad-free even unpaid.
https://www.sensai.fit/blog/hevy-vs-strong-2026 ·
https://www.sensai.fit/blog/fitness-app-pricing-free-tier-comparison
There is no price gap (the incumbent is $3/mo), no quality gap (4.9 stars), and no
feature gap a six-week build closes. This is the clearest no in the sweep.

### R2 — Photo-based calorie / food logging — **REJECT, the exit already happened**
See the cross-cutting finding. Cal AI took this to $50M+ ARR and sold to
MyFitnessPal in Dec 2025; the product now sits on MFP's 20M-food database, which
is exactly the seeded dataset this studio cannot own.
https://superframeworks.com/case-study/cal-ai

### R3 — Personal CRM / "keep in touch with friends" — **REJECT on price ceiling**
Crowded with tiny apps and the price floor has collapsed: **FidesRM is $0.99**
(https://apps.apple.com/ca/app/fidesrm/id6745396981), alongside inTouch
(https://apps.apple.com/us/app/intouch-personal-crm/id6475792802), Queue
(https://apps.apple.com/us/app/queue-personal-crm/id1451429218), Covve, Dex
(free to 20 relationships, then from $9.99/mo). The apps that charge real money
(Dex) are B2B-networking-flavoured, which is a different product and a different
buyer. Consumer side monetises at a dollar.

### R4 — Gift tracking / occasion reminders — **REJECT, no evidence of payment**
Long tail of near-identical recent App Store entries — Gift Recorder
(https://apps.apple.com/app/id1514423614), Gift Locker, Gift Tracking, Gift Finder
Reminder & Planner, Surprise (https://apps.apple.com/us/app/id882141352), Giftplanner
— and the "best of" coverage is written by GiftList, a commercially interested
party (https://giftlist.com/blog/birthday-gift-tracking-5-tools-to-never-miss-a-date).
I found no install counts, no review volume, and no price anyone defends. Highly
seasonal demand (Nov–Dec) is a bad fit for a studio with one shot per six weeks.

### R5 — Privacy-first period tracking — **REJECT, free and non-profit incumbents**
The privacy wedge is real and post-Roe salient, but it is **already taken by
free, open-source, nonprofit-funded apps**: drip (Mozilla-associated, open source,
no account, no server — https://apps.apple.com/app/id1584564949), Euki (nonprofit,
no account/email/phone, open source on GitHub, includes a duress PIN —
https://apps.apple.com/app/euki/id1469213846), and Periodical/Mensinator.
https://www.expressvpn.com/blog/period-tracking-apps/
Competing on privacy against a nonprofit that charges nothing and publishes its
source is unwinnable, and charging for reproductive-health privacy is a bad look
that will show up in reviews. The one gap noted — drip and Euki are "basic
trackers with no sync, no cross-device access, no cycle insights" — is a gap the
studio also cannot fill: sync needs a backend, and "insights" edges toward
regulated medical advice.

### R6 — Consumer PT / rehab home-exercise adherence — **HOLD, not yet rejected**
Searched, but returned almost entirely academic literature (JMIR/PMC RCTs) rather
than a consumer market. Useful finding buried in it: apps built specifically for
osteoarthritis had **the lowest quality and lowest behaviour-change potential** of
any chronic-condition app category, and there is currently no effective digital
intervention for exercise adherence in chronic musculoskeletal pain.
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11006223/ ·
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9516363/
That is a real unmet need — but the same literature says uptake depends on **a
therapist instructing the patient to use it**, which is a partnership/distribution
channel the studio explicitly cannot build. Also sits near the regulated-advice
line. A dedicated scout is still working this space; revisit before final reject.
