"""Run one scan: X search -> Claude screening -> outreach drafts -> digest.

Usage:
  python -m radar.main                     # live run (needs X_BEARER_TOKEN, ANTHROPIC_API_KEY)
  python -m radar.main --sample tests/sample_posts.json   # no X calls, uses saved posts
  python -m radar.main --no-claude --sample ...           # offline smoke test, no API calls
Nothing is ever sent. Emails become Gmail drafts only when GMAIL_ADDRESS and
GMAIL_APP_PASSWORD are set; everything also lands in the digest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .x_client import Post, XClient, parse_search_response
from .state import State

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def fetch_posts(cfg: dict, state: State, log) -> list[Post]:
    x = XClient(os.environ.get("X_BEARER_TOKEN", ""))
    budget = int(cfg.get("monthly_post_budget", 4000))
    per_query = int(cfg.get("max_results_per_query", 20))
    out: list[Post] = []
    for q in cfg["queries"]:
        used = state.posts_read_this_month()
        if used + per_query > budget:
            log(f"Monthly X budget reached ({used}/{budget} posts). Skipping remaining searches.")
            break
        key = State.query_key(q)
        posts, newest = x.search_recent(q, per_query, state.since_ids.get(key))
        state.add_reads(len(posts))
        if newest:
            state.since_ids[key] = newest
        log(f"Query {key}: {len(posts)} new posts")
        out.extend(posts)
    return out


def load_sample(path: str) -> list[Post]:
    posts, _ = parse_search_response(json.loads(Path(path).read_text()))
    return posts


def render_digest(items: list[dict], run_at: str) -> str:
    lines = [f"## Run {run_at} — {len(items)} opportunit{'y' if len(items) == 1 else 'ies'}", ""]
    for it in items:
        v, d, p = it["verdict"], it.get("outreach") or {}, it["post"]
        title = " · ".join(x for x in [v.get("company"), v.get("role")] if x) or "Opportunity"
        lines += [
            f"### {title}  (fit {v['relevance']}/10)",
            f"- Post: {p['link']} by @{p['author_username']}",
            f"- Why: {v['reason']}",
            f"- Contact: {v.get('contact_email') or v['contact_method']}"
            + (f" · Apply: {v['apply_link']}" if v.get("apply_link") else ""),
        ]
        if it.get("gmail_draft"):
            lines.append("- ✉️ Saved as a Gmail draft (review and send yourself)")
        if d:
            lines += ["", f"**Email subject:** {d['email_subject']}", "", "```", d["email_body"], "```",
                      "", "**DM:**", "", "```", d["dm_text"], "```"]
        lines.append("")
    return "\n".join(lines)


def run(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="JSON file shaped like an X search response; skips X")
    ap.add_argument("--no-claude", action="store_true", help="skip Claude (offline smoke test)")
    ap.add_argument("--state", default=str(DATA / "state.json"))
    args = ap.parse_args(argv)

    log = lambda m: print(m, flush=True)
    cfg = load_config()
    state = State(Path(args.state))
    profile = (ROOT / "profile.md").read_text()

    posts = load_sample(args.sample) if args.sample else fetch_posts(cfg, state, log)
    unique: dict[str, Post] = {}
    for p in posts:
        if not state.is_seen(p.id):
            unique[p.id] = p
    posts = list(unique.values())
    log(f"{len(posts)} unseen posts to screen")

    items: list[dict] = []
    if posts and not args.no_claude:
        from .analyze import Analyzer
        an = Analyzer(profile, model=cfg.get("model", "claude-opus-5-5"))
        size = int(cfg.get("classify_batch_size", 20))
        min_rel = int(cfg.get("min_relevance", 6))
        verdicts = []
        for i in range(0, len(posts), size):
            verdicts += an.classify(posts[i:i + size])
        keep = [v for v in verdicts if v.is_opportunity and v.relevance >= min_rel]
        log(f"{len(keep)} posts look like real opportunities")
        for v in sorted(keep, key=lambda v: -v.relevance):
            p = unique[v.post_id]
            o = an.draft(p, v)
            items.append({
                "post": {**p.__dict__, "link": p.link},
                "verdict": v.model_dump(),
                "outreach": o.model_dump() if o else None,
            })

    # Gmail drafts (optional). Never sends.
    addr, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if addr and pw:
        from .gmail_drafts import GmailDrafts, build_message
        to_draft = [it for it in items if it["outreach"] and it["verdict"].get("contact_email")]
        msgs = [build_message(addr, it["verdict"]["contact_email"], it["outreach"]["email_subject"],
                              it["outreach"]["email_body"]) for it in to_draft]
        try:
            n = GmailDrafts(addr, pw).save(msgs)
            for it in to_draft:
                it["gmail_draft"] = True
            log(f"Saved {n} Gmail drafts")
        except Exception as e:  # keep the digest even if Gmail fails
            log(f"Gmail drafts failed: {e}")

    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    DATA.mkdir(exist_ok=True)
    latest = DATA / "latest_digest.md"
    if items:
        digest = render_digest(items, run_at)
        day = DATA / "digests" / f"{run_at[:10]}.md"
        day.parent.mkdir(exist_ok=True)
        with day.open("a") as f:
            f.write(digest + "\n")
        with (DATA / "opportunities.jsonl").open("a") as f:
            for it in items:
                f.write(json.dumps({**it, "found_at": run_at}, ensure_ascii=False) + "\n")
        latest.write_text(digest)
    elif latest.exists():
        latest.unlink()

    if not args.no_claude:
        state.mark_seen(unique.keys())
    state.save()
    log(f"Done. {len(items)} opportunities this run. X posts read this month: {state.posts_read_this_month()}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
