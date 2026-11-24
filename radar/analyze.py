"""Claude steps: classify posts in batches, then draft outreach for the good ones."""
from __future__ import annotations

import json
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from .x_client import Post


class PostVerdict(BaseModel):
    post_id: str
    is_opportunity: bool = Field(description="True only for a real, current internship or early-career opportunity someone is offering")
    kind: Literal["internship", "founding_role", "fellowship", "other", "not_relevant"]
    company: Optional[str] = None
    role: Optional[str] = None
    contact_email: Optional[str] = Field(None, description="An email address written in the post or bio, exactly as written; null if none")
    apply_link: Optional[str] = None
    contact_method: Literal["email", "dm", "link", "unknown"]
    location: Optional[str] = None
    relevance: int = Field(description="0-10 fit for this candidate")
    reason: str = Field(description="One short sentence on why")


class Verdicts(BaseModel):
    verdicts: list[PostVerdict]


class Outreach(BaseModel):
    email_subject: str
    email_body: str
    dm_text: str = Field(description="Under 280 characters")


CLASSIFY_SYSTEM = """You screen posts from X for a job-seeking student.
Keep only posts where a startup or founder is actively offering an internship, founding/junior engineering role, fellowship or similar opportunity the candidate could apply to now.
Reject: people looking for internships themselves, generic advice, memes, recruiters spamming many unrelated jobs, courses, paid programs, and anything that asks the candidate to pay.
Only report an email address if it literally appears in the post or the author's bio. Never invent contact details.
Score relevance 0-10 against the candidate profile below (technical roles, early-stage startups, remote or India-friendly score higher).

<candidate_profile>
{profile}
</candidate_profile>"""

DRAFT_SYSTEM = """You write short, genuine cold outreach for a student applying to a startup opportunity found on X.
Rules:
- Sound like a real person, not a template. No flattery, no "I hope this finds you well", no buzzwords.
- Email: 90-150 words. Open by referencing their specific post. Pick the 1-2 most relevant things from the candidate's profile for THIS role, with concrete numbers where they exist. End with one clear ask (a quick chat, or how to apply) and the candidate's GitHub/LinkedIn.
- Subject: specific, under 9 words.
- DM: under 280 characters, same idea, casual.
- Never claim experience the profile does not show. Never invent facts about the company beyond the post and bio.
- Sign off with the candidate's first name.

<candidate_profile>
{profile}
</candidate_profile>"""


def _post_block(p: Post) -> dict:
    return {
        "post_id": p.id,
        "author": f"@{p.author_username} ({p.author_name})",
        "author_bio": p.author_bio,
        "text": p.text,
        "links": p.urls,
        "posted_at": p.created_at,
    }


class Analyzer:
    def __init__(self, profile: str, model: str = "claude-opus-5-5", client: anthropic.Anthropic | None = None):
        self.profile = profile
        self.model = model
        self.client = client or anthropic.Anthropic()

    def classify(self, posts: list[Post]) -> list[PostVerdict]:
        if not posts:
            return []
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=[{"type": "text", "text": CLASSIFY_SYSTEM.format(profile=self.profile), "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": "Return one verdict per post, using the same post_id.\n\n"
                + json.dumps([_post_block(p) for p in posts], ensure_ascii=False, indent=1),
            }],
            output_format=Verdicts,
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            return []
        wanted = {p.id for p in posts}
        return [v for v in resp.parsed_output.verdicts if v.post_id in wanted]

    def draft(self, post: Post, verdict: PostVerdict) -> Outreach | None:
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=[{"type": "text", "text": DRAFT_SYSTEM.format(profile=self.profile), "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "medium"},
            messages=[{
                "role": "user",
                "content": "Write outreach for this opportunity.\n\n"
                + json.dumps({"post": _post_block(post), "extracted": verdict.model_dump()}, ensure_ascii=False, indent=1),
            }],
            output_format=Outreach,
        )
        if resp.stop_reason == "refusal":
            return None
        return resp.parsed_output
