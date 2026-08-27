# Warranty Keeper — market research

**Recommendation: no-go.** Not because the app is hard to build, but because the
market has already run this experiment several times and the results are public.

---

## A note on method, before you trust anything below

Direct page fetching was blocked by the proxy in this environment. I could not
open App Store and Play listings in a browser and read the review sections
myself, which is how I would normally do this. Everything below comes from
search-engine retrieval of those same listing pages and of third-party trackers
(AppBrain, Capterra), which return listing text, pricing, ratings and install
counts, plus quoted review content.

That means: **install counts, ratings, and pricing below are second-hand from
listing/tracker summaries, not eyeballed by me on the page.** They are
consistent across multiple independent queries, and the picture they paint is
lopsided enough that I do not think a hands-on pass would flip the conclusion.
But if you are about to overrule this brief, the two numbers to re-check by hand
are the AppBrain install figures and the "not enough ratings" status on the older
iOS listings. Both are one browser tab each. Every URL I relied on is in
`opportunity.json` under `sources`.

---

## The one-paragraph version

The proposed product — photograph a receipt, log the item, offline, no account,
one-time unlock, free tier then paywall — is already shipping. Not "something
similar exists." The *exact* positioning, including the marketing language, is
live on both stores from at least four separate developers, priced at **$0.99 to
$1.99 one-time**. Meanwhile the category's best-established app is free with
unlimited items and cloud backup and still pulls roughly **260 installs a
month**, and the one genuinely good product this space produced — Centriq —
**shut down and deleted all user data in January 2025** after nearly a decade and
an industry award. The name "Warranty Keeper" is also already taken on Play and
twice on iOS.

---

## What I opened, and what it cost

### The apps that are already your app

| App | Platform | Price | What its listing says |
|---|---|---|---|
| **Warranty Wallet** | iOS | Free + **$1.99 one-time** unlock, no subscription | Works offline; *does not request internet access at all* |
| **Drawer: Warranty & Receipt** | iOS | **$0.99** paid up front | No internet connection required; no data, invoices or photos sent to any server, 100% local |
| **KeepSlip** | iOS | Free + IAP | "Secure, offline-first receipt organizer"; local storage, no cloud uploads; smart scanner auto-detects merchant name and purchase date |
| **Warranty Tracker & Reminder** (lozsolutiont) | Android | Free + IAP | Explicitly "an offline app"; product warranties, return deadlines, receipts, reminders |
| **Warrantly** (TechBasi) | iOS + Android | **Free for 10 warranties**, then a single **lifetime** Pro purchase | Receipt photos + PDFs, serial numbers, alerts at 1/3/7/14/30/60/90 days before expiry, optional cloud sync, no ads, no tracking |

Look at that Warrantly row against the brief. Free tier capped at a useful
number of items, one-time lifetime unlock, no subscription, receipt photos,
configurable pre-expiry reminders. That is the product spec in `idea.json`,
already shipped, on both target platforms, with cloud sync on top.

The offline / no-account / one-time-purchase triad is not our differentiator. It
is the category's standard marketing copy.

### The price ceiling, observed

- Drawer: **$0.99** up front
- Warranty Wallet: **$1.99** lifetime unlock
- Warranty Tracker & Manager: **$1.99**, with a *$0.99/year* remove-ads option
- Warranty Keeper: Receipt Log: $2.99/mo, $12.99/yr, or **$24.99 lifetime** — the
  outlier trying to charge real money, with no visible traction to show for it
- Warranty Keeper (Play): **free, unlimited items, cloud backup, no paywall**

The clearing price for this feature set is one to two dollars, one time. After
platform fees that is roughly **$1.40 net per sale**. That is the revenue line
you would be building against, and it is set by competitors, not by us.

### The number that actually decides this

Install volume, from AppBrain:

- **Warranty Keeper** (`com.warranty_keeper`) — 10,000+ lifetime installs, 4.32★
  from 320 ratings, last updated April 2026. **~260 installs in the last 30
  days.** This app is *free*, *unlimited*, and *cloud-backed up*. It is the
  best-established consumer warranty tracker on Play. It cannot break 300
  installs a month.
- **Warranty Tracker & Receipts** (`com.garanti.takip`) — **130 lifetime
  installs** since December 2024. 58 in the last 30 days.
- **Warranty Reminder Book** — ~2,000 lifetime installs, **6** in the last 30 days.

On iOS the picture is the same by a different measure: several listings,
including `id6449024145` which has been live since 2023, still show *"hasn't
received enough ratings or reviews to display an overview"* — Apple's way of
saying fewer than five ratings. Three years. Fewer than five ratings.

The only warranty app in this research with real volume is a **manufacturer's own
"Warranty Registration" app: ~740,000 installs, ~280/day.** That is the tell.
Demand for warranty record-keeping is real, but it converts at the point of sale,
handed to the customer by the seller — not through App Store search. We cannot
reach that channel with camera + local notifications and no backend.

### The corpse in the room

**Centriq shut down its consumer app on 31 January 2025 and deleted all user
data.** It let homeowners snap an appliance model label to pull manuals,
troubleshooting guides, parts, recalls and how-to videos, plus receipts,
warranties and reminders. It won the National Association of Home Builders
"Game Changer" award. It ran for close to a decade, changed ownership, tried
tiers at $17.95 / $29.95 / $59.95 / $99.95 a year, and still could not make the
consumer business work — the shutdown notes cite the difficulty of the home
services market. Third parties have since built Centriq CSV importers to catch
the refugees.

If a funded, awarded product with a far deeper feature moat than a photo-and-a-date
could not sustain this category, a $1.99 offline notepad will not.

---

## What the reviewers complain about — and why it's bad news for *this* spec

The one- and three-star reviews are usually where the wedge hides. Here they
point the opposite way from the brief.

**1. "It doesn't scan anything — I have to type it all in."**
A Warranty Keeper reviewer complains the app does not scan documents or
automatically detect product and warranty details, requiring manual entry. This
is the single most substantive complaint in the category, and it is a complaint
about *exactly what we are proposing to build*: photograph the receipt, then key
in the store, the price, the date, the warranty length. The photo is the easy
half; the typing is the drop-off.

This one is at least addressable within the constraints — Apple's Vision
framework and Google's ML Kit both do text recognition fully on-device, offline,
free. But KeepSlip already advertises exactly that (local scanner detecting
merchant name and purchase date), so it is parity, not a lead. And removing a
complaint from an audience that isn't arriving doesn't create an audience.

**2. "I lost everything."**
A Warranty-Tracker reviewer reported having 20+ entries saved, opening the app
one day to find all of them gone, losing every stored receipt — and then losing
money on items that failed inside their warranty period. They contacted the
developer and got no response. The developer's fix was a rebuild around cloud
sync.

This is the direct cost of the "no account, no backend" constraint. A local-only
store means a lost phone, a botched OS restore, or one corrupted database file
destroys a user's multi-year records with no recovery path, and the app is
designed to be trusted with records the user *only discovers are gone at the
worst possible moment*. You can mitigate with an aggressive encrypted-export
prompt, but you cannot eliminate it, and the one-star review writes itself.

**3. "No response from the developer."**
Recurs across the category. Consistent with a field of near-abandoned clones —
which is also what a $1.40-per-sale economy produces.

---

## The demand-side evidence, honestly stated

I want to be fair to the idea: the underlying pain is documented.

- Consumer Action's smartphone survey: **63%** of owners knew their device had a
  manufacturer warranty but did not know how to file a claim; **75%** did not
  know where to escalate an unresolved claim.
- Industry survey reporting: **62%** of consumers hit difficulty resolving
  warranty claims with retailers and manufacturers; **14%** never get it
  resolved. A third spend over 30 minutes trying; 16% spend over two hours.

But read what those numbers actually say. The friction people report is **not
knowing how to claim** and **the claim process fighting them**. It is not "I
photographed my receipt into the wrong place." A local receipt vault does not
touch the 62% number. It solves a prerequisite most people apparently never
reach.

There is no reliable public market size for consumer warranty-tracking apps, and
I am not going to manufacture one from global appliance spend. The install
counts above *are* the market sizing, and they are the honest version.

---

## Why not a pivot

I looked. Three adjacent shapes have more life in them than this one, and none
of them is a rescue of this brief:

- **Return windows, not warranty windows.** 30 days, not 3 years — a real
  deadline with real urgency and an actual reason to open the app this week.
  Several entrants (Warranty Tracker & Reminder, Warranty Wallet, Ravely) have
  already noticed and bundled returns. It fixes the retention hole but sits in
  the same low-demand, $1.99 pond.
- **General receipt/expense capture** with warranty as a field. Higher frequency,
  much larger market — and a brutally competitive one against Expensify, Google
  Photos search, and every banking app.
- **B2B: warranty registration at point of sale.** This is where the money
  demonstrably is — the manufacturer registration app at 740k installs, the
  Shopify warranty-registration apps with hundreds of reviews. It needs a
  backend, retailer relationships, and a sales motion. It violates every stated
  constraint and is not a six-week job.

None of these is "the same product in a better shape," which is what a pivot
recommendation should be. So: no-go, cleanly, rather than a hedged pivot that
sends the team into the same pond wearing a different hat.

---

## If you want to overrule me, do this first

Do not spend six weeks. Spend two days:

1. Rename. "Warranty Keeper" is taken on Play (10k+ installs, 320 ratings) and
   twice on iOS. Shipping under it forfeits our own brand term in the only free
   acquisition channel we have.
2. Run a small App Store / Play search-ads test against "warranty tracker",
   "receipt keeper", "warranty reminder" pointing at a one-page landing site.
   Measure cost per tap and per email capture.
3. **The kill line: if cost per interested user exceeds ~$1, stop.** We net $1.40
   on a $1.99 unlock, only a fraction of visitors convert, and there is no
   repeat purchase, no subscription, and no referral loop to make it back.

That test costs a few hundred dollars and two days. This build costs six weeks.

**Build estimate if you proceed anyway: 3.5 weeks**, not six — camera capture,
local database, date math, local notifications, one non-consumable IAP, and a
settings screen. The cheapness of the build is exactly what makes this category
a field of thirty identical apps splitting a few thousand installs a month.
