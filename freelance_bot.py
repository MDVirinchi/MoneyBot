"""
Freelance Automation Bot
- Monitors Upwork RSS for matching jobs and saves AI-written proposals
- Generates deliverables using Claude AI
- Rotates through all skill keywords every cycle
- Tracks earnings across platforms
"""

import time
import json
import logging
import requests
import sys
from pathlib import Path
from datetime import datetime
import anthropic
import config

log = logging.getLogger("freelance_bot")
if not log.handlers:
    log.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [FREELANCE] %(message)s")
    _fh = logging.FileHandler("moneybot_freelance.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    _sh = logging.StreamHandler(open(sys.stdout.fileno(),
        mode="w", encoding="utf-8", buffering=1, closefd=False))
    _sh.setFormatter(_fmt)
    log.addHandler(_fh)
    log.addHandler(_sh)
    log.propagate = False

EARNINGS_FILE  = Path("freelance_earnings.json")
PROPOSALS_DIR  = Path("proposals")
SEEN_JOBS_FILE = Path("seen_jobs.json")

# All skill keywords — bot rotates through ALL of them, 5 per cycle
AI_SKILLS = [
    "article writing", "blog post", "copywriting", "seo content",
    "product description", "email writing", "social media content",
    "data entry", "research summary", "proofreading", "resume writing",
    "cover letter", "caption writing", "content writing", "ghostwriting",
    "website content", "newsletter writing", "press release", "listicle",
    "technical writing",
]

REMOTEOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# RemoteOK tags that match writing/content work
REMOTEOK_TAGS = [
    "writing", "copywriting", "content", "marketing", "seo",
    "social-media", "blog", "editing", "proofreading", "research",
]


# ── Claude AI fulfillment engine ──────────────────────────────────────────────

class FulfillmentEngine:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def fulfill(self, job_title: str, job_description: str) -> str:
        """Generate complete deliverable for a freelance job."""
        system = (
            "You are a professional freelance writer and content creator. "
            "Produce high-quality, original deliverables that exceed client expectations. "
            "Be thorough, professional, and match the tone requested."
        )
        prompt = f"""Job Title: {job_title}

Job Description:
{job_description}

Please produce the complete deliverable for this job. Make it professional,
original, and ready to submit directly to the client with no edits needed.
"""
        log.info(f"Generating deliverable for: {job_title[:60]}")
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    def write_proposal(self, job_title: str, job_description: str, budget: str = "varies") -> str:
        """Write a concise, winning job proposal."""
        prompt = f"""Write a short, compelling Upwork proposal for this job.

Job: {job_title}
Budget: {budget}
Description: {job_description[:600]}

Rules:
- Under 150 words
- Start with a specific insight about their project (NOT "I saw your job posting")
- Mention 1 relevant past result with a number
- End with a clear next step
- Sound human and confident, not salesy
"""
        message = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text


# ── RemoteOK job scanner ──────────────────────────────────────────────────────
# Upwork RSS was permanently removed (HTTP 410). RemoteOK has a free public API.

class JobScanner:
    def __init__(self):
        self.session = requests.Session()
        self._tag_index = 0

    def _next_tags(self, count=3) -> list:
        """Cycle through REMOTEOK_TAGS, 3 per scan cycle."""
        start = self._tag_index % len(REMOTEOK_TAGS)
        batch = [REMOTEOK_TAGS[(start + i) % len(REMOTEOK_TAGS)] for i in range(count)]
        self._tag_index = (self._tag_index + count) % len(REMOTEOK_TAGS)
        return batch

    def search(self) -> list:
        """Fetch jobs from RemoteOK for the next batch of tags."""
        tags = self._next_tags()
        log.info(f"Scanning RemoteOK for tags: {tags}")
        jobs = []
        for tag in tags:
            jobs.extend(self._fetch_tag(tag))
            time.sleep(1.5)  # polite delay
        return jobs

    def _fetch_tag(self, tag: str) -> list:
        url = f"https://remoteok.com/api?tag={tag}"
        jobs = []
        for attempt in range(3):
            try:
                r = self.session.get(url, headers=REMOTEOK_HEADERS, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    for item in data:
                        if not isinstance(item, dict) or "position" not in item:
                            continue
                        title = item.get("position", "")
                        company = item.get("company", "")
                        desc = item.get("description", "") or item.get("tags", "")
                        if isinstance(desc, list):
                            desc = ", ".join(desc)
                        link = item.get("url", f"https://remoteok.com/remote-jobs/{item.get('id','')}")
                        jobs.append({
                            "title": title,
                            "description": f"Company: {company}\n{str(desc)[:600]}",
                            "link": link,
                            "keyword": tag,
                            "platform": "remoteok",
                            "found_at": str(datetime.now()),
                        })
                    log.debug(f"  '{tag}': {len(jobs)} jobs")
                    break
                elif r.status_code == 429:
                    log.warning("RemoteOK rate limit, waiting 30s...")
                    time.sleep(30)
                else:
                    log.debug(f"  '{tag}': HTTP {r.status_code}")
                    break
            except Exception as e:
                log.warning(f"  '{tag}': {e} (attempt {attempt+1}/3)")
                time.sleep(5)
        return jobs


# ── Proposal saver ────────────────────────────────────────────────────────────

def save_proposal(job: dict, proposal_text: str):
    """Save AI-generated proposal to a text file for manual submission."""
    PROPOSALS_DIR.mkdir(exist_ok=True)
    safe_title = "".join(c for c in job["title"][:40] if c.isalnum() or c in " -_").strip()
    fname = PROPOSALS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.txt"
    content = (
        f"JOB TITLE : {job['title']}\n"
        f"URL       : {job['link']}\n"
        f"KEYWORD   : {job['keyword']}\n"
        f"FOUND AT  : {job['found_at']}\n"
        f"\n{'='*60}\nPROPOSAL:\n{'='*60}\n\n"
        f"{proposal_text}\n"
        f"\n{'='*60}\nTO SUBMIT:\n{'='*60}\n"
        f"1. Open the URL above\n"
        f"2. Click 'Apply Now'\n"
        f"3. Paste the proposal above\n"
        f"4. Send!\n"
    )
    fname.write_text(content, encoding="utf-8")
    log.info(f"Proposal saved -> proposals/{fname.name}")
    return fname


# ── Seen-jobs tracker ─────────────────────────────────────────────────────────

def load_seen_jobs() -> set:
    if SEEN_JOBS_FILE.exists():
        return set(json.loads(SEEN_JOBS_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen_jobs(seen: set):
    # Keep last 2000 to avoid infinite growth
    trimmed = list(seen)[-2000:]
    SEEN_JOBS_FILE.write_text(json.dumps(trimmed), encoding="utf-8")


# ── Earnings tracker ──────────────────────────────────────────────────────────

def load_earnings():
    if EARNINGS_FILE.exists():
        return json.loads(EARNINGS_FILE.read_text(encoding="utf-8"))
    return {"total_inr": 0, "jobs": []}

def log_earning(title: str, amount_inr: float, platform: str):
    data = load_earnings()
    data["total_inr"] += amount_inr
    data["jobs"].append({
        "title": title, "amount_inr": amount_inr,
        "platform": platform, "time": str(datetime.now())
    })
    EARNINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info(f"Earning logged: Rs.{amount_inr} from {platform} | Total: Rs.{data['total_inr']}")


# ── Demo: test AI fulfillment without any account ─────────────────────────────

def demo_fulfill():
    if not config.ANTHROPIC_API_KEY:
        log.error("Set ANTHROPIC_API_KEY in config.py to enable AI fulfillment.")
        return
    engine = FulfillmentEngine()
    sample = {
        "title": "Write a 500-word SEO blog post about sustainable fashion",
        "description": (
            "I need a blog post about sustainable fashion trends in 2025. "
            "Target keyword: 'sustainable fashion brands'. Tone: friendly, informative."
        ),
    }
    log.info("Running demo fulfillment...")
    result = engine.fulfill(sample["title"], sample["description"])
    output = Path("demo_output.txt")
    output.write_text(result, encoding="utf-8")
    log.info(f"Demo output saved to demo_output.txt ({len(result)} chars)")
    print("\n--- PREVIEW (first 300 chars) ---")
    print(result[:300])
    return result


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    if not config.ANTHROPIC_API_KEY:
        log.error("Set ANTHROPIC_API_KEY in config.py first.")
        return

    engine  = FulfillmentEngine()
    scanner = JobScanner()
    seen    = load_seen_jobs()

    # Count proposals already generated
    PROPOSALS_DIR.mkdir(exist_ok=True)
    existing = len(list(PROPOSALS_DIR.glob("*.txt")))
    log.info(f"Freelance bot started. {existing} proposals already in queue.")
    log.info(f"Source: RemoteOK (free API) | rotating {len(REMOTEOK_TAGS)} tags, 3 per cycle.")

    cycle = 0
    while True:
        cycle += 1
        log.info(f"--- Freelance scan cycle #{cycle} ---")
        try:
            jobs = scanner.search()
            new_jobs = [j for j in jobs if j["link"] not in seen]
            log.info(f"Found {len(jobs)} jobs, {len(new_jobs)} new.")

            for job in new_jobs[:5]:  # process up to 5 per cycle
                seen.add(job["link"])
                try:
                    proposal = engine.write_proposal(job["title"], job["description"])
                    save_proposal(job, proposal)
                except Exception as e:
                    log.error(f"Proposal generation failed for '{job['title'][:40]}': {e}")
                time.sleep(2)

            save_seen_jobs(seen)

            # Summary
            total_proposals = len(list(PROPOSALS_DIR.glob("*.txt")))
            log.info(f"Total proposals in queue: {total_proposals}. Next scan in 15 min.")

        except Exception as e:
            log.error(f"Freelance loop error: {e}", exc_info=True)

        time.sleep(900)  # 15 minutes


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo_fulfill()
    else:
        run()
