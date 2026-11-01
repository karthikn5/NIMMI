"""Clicks in customer emails: a person's count, an email security scanner's don't (mail plan, phase 6).

The patterns below are the ones the public sources describe for real scanners (mail_plan.md, phase 6): Microsoft Defender's Safe Links and gateways like Mimecast,
Proofpoint and Barracuda open an email's links seconds after delivery, several at once, often with an ordinary browser's user agent from a shared cloud address;
some name themselves or an HTTP library in the user agent; checks by HEAD request. And the people they must not be confused with: a person who clicks fast, or
clicks two links in a row."""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import Contact, EmailClick, EmailJob, EmailLink, IntegrationSettings
from database import async_session
from mail import clicks

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"


@pytest.fixture(autouse=True)
def _settled_before(run):
    """Other tests' clicks in the shared database aren't these tests' business."""
    async def go():
        async with async_session() as db:
            await db.execute(update(EmailClick).where(EmailClick.settled_at.is_(None)).values(settled_at=datetime.utcnow()))
            await db.commit()
    run(go)


class Mail:
    """One email with its links, sent at `sent`."""
    def __init__(self, run, user, bot, to, sent, labels=("Our prices", "Book a time", "Brochure.pdf")):
        self.run, self.user, self.to, self.sent = run, user, to, sent
        self.ip = f"2001:db8::{uuid.uuid4().hex[:4]}"  # its own network: the tests share a database
        self.job_id, self.tokens = run(self._make, user, bot, to, sent, labels)

    async def _make(self, user, bot, to, sent, labels):
        async with async_session() as db:
            job = EmailJob(user_id=user.id, bot_id=bot, kind=f"chat_lead#{uuid.uuid4().hex[:6]}", ref_id=uuid.uuid4().hex, to_email=to, automation="chat_lead", step=1,
                           subject="Your enquiry", body="x", status="sent", send_at=sent, sent_at=sent)
            db.add(job)
            await db.flush()
            tokens = []
            for label in labels:
                token = uuid.uuid4().hex[:22]
                kind = "book" if label == "Book a time" else "file" if label.endswith(".pdf") else "link"
                db.add(EmailLink(token=token, user_id=user.id, job_id=job.id, kind=kind, target="https://example.com/" + label.replace(" ", "-"), label=label, clicks=0))
                tokens.append(token)
            await db.commit()
            return job.id, tokens

    def click(self, n, after, agent=CHROME, ip=None, language=True):
        async def go():
            async with async_session() as db:
                link = await db.get(EmailLink, self.tokens[n])
                clicks.record(db, link, ip or self.ip, agent, language, now=self.sent + timedelta(seconds=after))
                await db.commit()
        self.run(go)

    def settle(self):
        return self.run(clicks.settle_due, datetime.utcnow() + timedelta(days=1))

    def state(self):
        async def go():
            async with async_session() as db:
                job = await db.get(EmailJob, self.job_id)
                rows = (await db.execute(select(EmailClick).where(EmailClick.job_id == self.job_id).order_by(EmailClick.at))).scalars().all()
                links = [await db.get(EmailLink, t) for t in self.tokens]
                return SimpleNamespace(clicked=job.clicked_at, people=[r.person for r in rows], reasons=[r.reasons for r in rows],
                                       counts=[(l.clicks or 0, l.scanner_clicks or 0) for l in links])
        return self.run(go)


@pytest.fixture
def mail(make_user, run):
    user = make_user()
    bot = user.bot()
    base = datetime.utcnow() - timedelta(hours=2)
    return lambda to="asha@example.com", sent=base, **k: Mail(run, user, bot, to, sent, **k)


def test_a_safe_links_sweep_counts_for_nothing(mail):
    m = mail()
    for n, after in enumerate((4, 4.6, 5.2)):  # every link, seconds after delivery, an ordinary browser's user agent
        m.click(n, after)
    m.settle()
    s = m.state()
    assert s.people == [False, False, False] and s.clicked is None and s.counts == [(0, 1), (0, 1), (0, 1)]
    assert any("3 of the email's links" in " ".join(r) for r in s.reasons)


def test_a_sweep_after_a_slow_delivery_still_shows(mail):
    m = mail()
    for n, after in enumerate((95, 95.4, 96.1)):  # the sweep, but long after sending: three links in a second still isn't a person
        m.click(n, after)
    m.settle()
    assert m.state().people == [False, False, False]


@pytest.mark.parametrize("agent", ["python-requests/2.31.0", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/120.0.0.0 Safari/537.36",
                                   "Mozilla/5.0 (compatible; Barracuda Sentinel)", "Mimecast URL Protect", "Proofpoint URL Defense", "curl/8.4.0", "Go-http-client/1.1",
                                   "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) BingPreview/1.0b", "WhatsApp/2.23.20.0 A",
                                   "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)"])
def test_a_scanner_or_a_library_that_names_itself(mail, agent):
    m = mail()
    m.click(0, 3600, agent=agent)  # an hour later, one link: only the name gives it away
    m.settle()
    assert m.state().people == [False]


def test_a_gateway_opening_many_peoples_emails(mail):
    mails = [mail(to=f"staff{n}@bigcompany.example") for n in range(5)]
    for n, m in enumerate(mails):
        m.click(0, 300 + n * 1.5, ip="2001:db8:20::1")  # five people's emails, one company address, within seconds: its gateway scanning
    mails[0].settle()
    assert all(m.state().people == [False] for m in mails)


def test_a_person_who_clicks_fast_still_counts(mail):
    m = mail()
    m.click(1, 8, agent=IPHONE)  # waiting for it, one link, eight seconds after sending
    m.settle()
    s = m.state()
    assert s.people == [True] and s.clicked is not None and s.counts[1] == (1, 0)


def test_a_person_who_clicks_two_links_counts(mail):
    m = mail()
    m.click(0, 600)
    m.click(1, 606)  # the prices, then Book a time
    m.settle()
    assert m.state().people == [True, True]


def test_people_at_one_office_clicking_at_different_times_count(mail):
    mails = [mail(to=f"team{n}@office.example") for n in range(5)]
    for n, m in enumerate(mails):
        m.click(0, 600 + n * 120, ip="2001:db8:40::1")  # the same office address, minutes apart
    mails[0].settle()
    assert all(m.state().people == [True] for m in mails)


def test_a_click_with_nothing_to_go_on_counts_for_little_alone(mail):
    m = mail()
    m.click(0, 5, agent="", language=False)  # no user agent, seconds after sending
    m.settle()
    assert m.state().people == [False]
    m2 = mail()
    m2.click(0, 3600, agent="", language=False)  # no user agent, but an hour later and alone: not enough to say
    m2.settle()
    assert m2.state().people == [True]


def test_a_click_isnt_judged_until_its_sweep_could_show(mail, run):
    m = mail()
    m.click(0, 5)
    assert run(clicks.settle_due, m.sent + timedelta(seconds=10)) == 0, "too soon"
    m.click(1, 5.5)
    m.click(2, 6)
    assert run(clicks.settle_due, m.sent + timedelta(seconds=40)) == 3
    assert m.state().people == [False, False, False], "the first click was judged with the others"


def test_each_click_is_settled_once(mail, run):
    import asyncio
    m = mail()
    m.click(0, 900)
    async def both():
        return await asyncio.gather(*(clicks.settle_due(datetime.utcnow() + timedelta(days=1)) for _ in range(3)))
    assert sum(run(both)) == 1
    assert m.state().counts[0] == (1, 0)


def test_the_link_opens_for_everyone_and_a_head_request_isnt_a_click(client, mail, run):
    m = mail()
    opened = client.get(f"/api/email/l/{m.tokens[0]}", follow_redirects=False, headers={"user-agent": "python-requests/2.31.0"})
    assert opened.status_code == 302 and opened.headers["location"] == "https://example.com/Our-prices"
    checked = client.head(f"/api/email/l/{m.tokens[0]}", follow_redirects=False)
    assert checked.status_code == 302
    async def count():
        async with async_session() as db:
            return (await db.execute(select(EmailClick).where(EmailClick.job_id == m.job_id))).scalars().all()
    assert len(run(count)) == 1, "only the GET is kept"
    m.settle()
    assert m.state().people == [False]


def test_the_address_is_never_kept(mail, run):
    m = mail()
    m.click(0, 900, ip="203.0.113.99")
    async def kept():
        async with async_session() as db:
            return (await db.execute(select(EmailClick.network).where(EmailClick.job_id == m.job_id))).scalar_one()
    network = run(kept)
    assert network and "203.0.113.99" not in network and len(network) == 16


def test_three_links_spread_over_ten_seconds_need_another_sign(mail):
    m = mail()
    for n, after in enumerate((900, 904, 908)):  # a quick reader with tabs, an hour after sending: a person
        m.click(n, after)
    m.settle()
    assert m.state().people == [True, True, True]
    m2 = mail()
    for n, after in enumerate((6, 10, 14)):  # the same pace, seconds after sending: a scanner
        m2.click(n, after)
    m2.settle()
    assert m2.state().people == [False, False, False]

