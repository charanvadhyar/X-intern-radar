# x-intern-radar

Every 6 hours this watches X for early-stage startups offering internships and similar roles. Claude screens each post against your profile and writes a personalised email and DM for every good match. You get a GitHub issue (GitHub emails it to you) listing each opportunity with its drafts.

**Nothing is ever sent for you.** When the post has an email address, the email is saved to your Gmail **Drafts** (optional). For DM-only posts, you copy the DM text into X yourself.

## How it works

1. **Search X** (`radar/x_client.py`): runs the searches in `config.yaml` on the official X API. It only fetches posts newer than the last run, and stops once `monthly_post_budget` is reached.
2. **Screen** (`radar/analyze.py`): Claude reads 20 posts per call and keeps only real opportunities. It drops people who are job hunting themselves, paid courses and spam. It pulls out the company, role, contact email (only if it's actually in the post) and apply link, then scores how well each one fits you (0 to 10).
3. **Draft**: for matches scoring at or above `min_relevance`, Claude writes a short email and a DM based on `profile.md`.
4. **Deliver**: Gmail drafts (optional), a digest in `data/digests/`, and a GitHub issue.

## Setup (one time)

Add these under **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Where to get it |
|---|---|
| `X_BEARER_TOKEN` | X Developer Console (console.x.com): your app's Keys and tokens. Set a spending limit there too. |
| `ANTHROPIC_API_KEY` | console.anthropic.com: API keys |
| `GMAIL_ADDRESS` *(optional)* | The Gmail account that should hold the drafts |
| `GMAIL_APP_PASSWORD` *(optional)* | Google Account → Security → 2-Step Verification → App passwords |

Then go to **Actions → X intern radar → Run workflow**. Leave "sample" ticked for a free test run on the saved posts in `tests/sample_posts.json`. After that the schedule takes over.

## Costs (rough)

- **X API:** about $0.005 per post returned. With 3 searches × 20 posts × 4 runs a day, the worst case is around $36 a month. The `monthly_post_budget: 4000` setting caps it at about $20. Most runs return fewer posts because only new ones count.
- **Claude:** screening is batched (one call per 20 posts at low effort), and drafting only runs for matches. Expect a few dollars a month.

## Tuning

- Edit `config.yaml` to change the searches, budget, how often posts count as a match, or the model.
- Edit `profile.md` when your resume changes.
- Edit the `cron` line in `.github/workflows/radar.yml` to change how often it runs.

## Local run

```bash
pip install -r requirements.txt
python -m pytest -q                                     # offline tests
ANTHROPIC_API_KEY=... python -m radar.main --sample tests/sample_posts.json --state /tmp/s.json
```

## Dashboard (GitHub Pages)

`docs/index.html` is a small dashboard that lists every opportunity. Each one has copy buttons for the email and DM, plus "applied" and "skipped" tracking that's saved in your browser.

The page itself holds no data. When you open it, you paste a **fine-grained GitHub token** that can only read this repo's contents. The token stays in your browser and is used to load `data/opportunities.jsonl` straight from the private repo, so anyone else who opens the link only sees the token prompt.

To enable it: go to **Settings → Pages**, set Source to "Deploy from a branch", pick `main` and `/docs`. On the free plan, Pages needs a public repo. GitHub Pro (free with the Student Developer Pack) allows Pages on a private repo.
