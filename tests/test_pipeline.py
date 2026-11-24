import json
from pathlib import Path
from types import SimpleNamespace

from radar import main as radar_main
from radar.analyze import Analyzer, Outreach, PostVerdict, Verdicts
from radar.gmail_drafts import build_message
from radar.state import State
from radar.x_client import parse_search_response

SAMPLE = Path(__file__).parent / "sample_posts.json"


def test_parse_search_response():
    posts, newest = parse_search_response(json.loads(SAMPLE.read_text()))
    assert newest == "1004"
    assert [p.id for p in posts] == ["1001", "1002", "1003", "1004"]
    assert posts[0].author_username == "tinyinfer_cto"
    assert posts[0].link == "https://x.com/tinyinfer_cto/status/1001"
    assert posts[3].urls == ["https://example.com/cohort"]


def test_parse_empty_response():
    assert parse_search_response({"meta": {"result_count": 0}}) == ([], None)


def test_state_budget_and_seen(tmp_path):
    s = State(tmp_path / "s.json")
    s.add_reads(20)
    s.mark_seen(["a", "b", "a"])
    s.save()
    s2 = State(tmp_path / "s.json")
    assert s2.posts_read_this_month() == 20
    assert s2.is_seen("a") and not s2.is_seen("c")
    assert s2.seen == ["a", "b"]


def test_draft_message_is_not_sent():
    m = build_message("me@gmail.com", "jobs@x.ai", "Hi", "Body")
    assert m["To"] == "jobs@x.ai" and m["Subject"] == "Hi"


class FakeMessages:
    def __init__(self):
        self.calls = []

    def parse(self, **kw):
        self.calls.append(kw)
        if kw["output_format"] is Verdicts:
            v = [
                PostVerdict(post_id="1001", is_opportunity=True, kind="internship", company="TinyInfer",
                            role="Engineering intern", contact_email="jobs@tinyinfer.ai", contact_method="email",
                            relevance=9, reason="Edge inference, matches Trivikrama"),
                PostVerdict(post_id="1002", is_opportunity=False, kind="not_relevant", contact_method="unknown",
                            relevance=0, reason="Seeker"),
                PostVerdict(post_id="1003", is_opportunity=True, kind="founding_role", role="Founding intern",
                            contact_method="dm", relevance=8, reason="Retrieval, matches ColVec"),
                PostVerdict(post_id="9999", is_opportunity=True, kind="other", contact_method="dm",
                            relevance=10, reason="hallucinated id"),
            ]
            return SimpleNamespace(stop_reason="end_turn", parsed_output=Verdicts(verdicts=v))
        return SimpleNamespace(stop_reason="end_turn",
                               parsed_output=Outreach(email_subject="S", email_body="B", dm_text="D"))


def test_end_to_end_with_fake_claude(tmp_path, monkeypatch):
    fake = FakeMessages()
    monkeypatch.setattr(radar_main, "DATA", tmp_path)
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    import radar.analyze as an
    orig_init = an.Analyzer.__init__

    def init(self, profile, model="m", client=None):
        orig_init(self, profile, model, client=SimpleNamespace(messages=fake))

    monkeypatch.setattr(an.Analyzer, "__init__", init)
    state_path = tmp_path / "state.json"
    assert radar_main.run(["--sample", str(SAMPLE), "--state", str(state_path)]) == 0

    digest = (tmp_path / "latest_digest.md").read_text()
    assert "TinyInfer" in digest and "Founding intern" in digest
    assert "9999" not in digest  # ids Claude invents are dropped
    lines = (tmp_path / "opportunities.jsonl").read_text().splitlines()
    assert len(lines) == 2
    # one classify call + two draft calls
    assert len(fake.calls) == 3
    # second run: everything already seen, no Claude calls
    fake.calls.clear()
    radar_main.run(["--sample", str(SAMPLE), "--state", str(state_path)])
    assert fake.calls == []
