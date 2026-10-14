import os
import re
import json
import time
import html
import random
import shutil
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from jobspy import scrape_jobs

# Catalog of known technical skills for extraction
COMMON_SKILLS = [
    # Languages
    "c++", "c#", "c", "python", "java", "javascript", "typescript", "golang", "go",
    "rust", "php", "ruby", "swift", "kotlin", "scala", "bash", "shell",
    # Embedded & Hardware
    "embedded systems", "embedded c", "embedded linux", "rtos", "freertos", "autosar",
    "can", "can bus", "can-bus", "lin", "uart", "spi", "i2c", "arm", "cortex",
    "stm32", "microcontroller", "microcontrollers", "firmware", "device drivers",
    "dsp", "fpga", "verilog", "vhdl", "pcb", "iot", "matlab", "simulink",
    # Frontend & Fullstack
    "react", "angular", "vue", "next.js", "node.js", "express", "html", "css",
    "sass", "tailwind", "redux", "graphql", "rest api", "restful api",
    # Backend & Frameworks
    "django", "flask", "fastapi", "spring boot", "asp.net", "laravel",
    # DevOps, Cloud & Databases
    "docker", "kubernetes", "aws", "azure", "gcp", "linux", "git", "ci/cd",
    "jenkins", "sql", "postgresql", "mysql", "mongodb", "redis", "oracle",
    # Engineering Practices
    "unit testing", "oop", "design patterns", "microservices", "agile", "scrum"
]

UPPERCASE_SKILLS = {
    "c++", "c#", "c", "sql", "aws", "gcp", "ci/cd", "rtos", "can", "can bus", "can-bus",
    "lin", "uart", "spi", "i2c", "arm", "dsp", "iot", "fpga", "pcb", "html", "css",
    "oop", "api", "rest api", "vhdl"
}


def normalize_locations(locations):
    """Accepts a single location or a nonempty list of location names."""
    if isinstance(locations, str):
        locations = [locations]
    if not isinstance(locations, list) or not locations or any(
        not isinstance(loc, str) or not loc.strip() for loc in locations
    ):
        raise ValueError("locations must be a nonempty list of location strings.")
    return list(dict.fromkeys(loc.strip() for loc in locations))


def normalize_search_terms(search_terms):
    """Accepts a single search term or a nonempty list of search terms."""
    if isinstance(search_terms, str):
        search_terms = [search_terms]
    if not isinstance(search_terms, list) or not search_terms or any(
        not isinstance(term, str) or not term.strip() for term in search_terms
    ):
        raise ValueError("search_terms must be a nonempty list of search term strings.")
    return list(dict.fromkeys(term.strip() for term in search_terms))


def load_configuration():
    """Reads settings from JsonConfigurqation.json beside this script."""
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "JsonConfigurqation.json"
    if not config_path.exists():
        alt_path = base_dir / "JsonConfiguration.json"
        if alt_path.exists():
            config_path = alt_path

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    if not isinstance(config, dict):
        raise ValueError("Configuration file must contain a JSON object.")

    config["bot_token"] = (config.get("bot_token") or os.environ.get("BOT_TOKEN") or "").strip()
    config["chat_id"] = (config.get("chat_id") or os.environ.get("CHAT_ID") or "").strip()

    required_keys = ("bot_token", "chat_id")
    missing_keys = [key for key in required_keys if not config.get(key)]
    if not config.get("search_terms") and not config.get("search_term"):
        missing_keys.append("search_terms")

    if missing_keys:
        raise ValueError(
            "Missing required settings. Set them in JsonConfigurqation.json or provide BOT_TOKEN and CHAT_ID environment variables. Missing: "
            + ", ".join(missing_keys)
        )

    config["search_terms"] = normalize_search_terms(
        config.get("search_terms", config.get("search_term"))
    )
    config["locations"] = normalize_locations(
        config.get("locations", config.get("location", ["Cairo, Egypt"]))
    )
    config["sites"] = config.get("sites", ["linkedin"])
    config["results_wanted"] = int(config.get("results_wanted", 20))
    hours = config.get("hours_old")
    config["hours_old"] = int(hours) if hours is not None and str(hours).strip() != "" else None
    config["is_remote"] = bool(config.get("is_remote", False))
    config["match_title_only"] = bool(config.get("match_title_only", False))
    config["exclude_terms"] = [
        str(term).strip().lower() for term in config.get("exclude_terms", []) if str(term).strip()
    ]
    return config


class JobNotifierBot:
    """Scrapes job postings across boards and forwards accurate new listings to Telegram."""

    def __init__(self, config):
        self.bot_token = config["bot_token"]
        self.chat_id = config["chat_id"]
        self.search_terms = config["search_terms"]
        self.locations = config["locations"]
        self.sites = config.get("sites", ["linkedin"])
        self.results_wanted = config.get("results_wanted", 20)
        self.hours_old = config.get("hours_old")
        self.is_remote = config.get("is_remote", False)
        self.match_title_only = config.get("match_title_only", False)
        self.exclude_terms = config.get("exclude_terms", [])

        base_dir = Path(__file__).resolve().parent
        history_file = config.get("history_file", "notified_jobs.json")
        self.history_file = (
            str((base_dir / history_file).resolve())
            if not Path(history_file).is_absolute()
            else history_file
        )

        # Handle directory created in Docker mount edge case
        history_path = Path(self.history_file)
        if history_path.exists() and history_path.is_dir():
            backup_path = history_path.with_name(f"{history_path.name}.invalid-dir-backup")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            history_path.rename(backup_path)
            shutil.rmtree(backup_path)

        self.notified_jobs_map = {}
        self.notified_jobs = self._load_history()

    def _clean_job_url(self, job_url):
        """Returns the full clean job URL without dynamic tracking query parameters."""
        url = str(job_url).strip()
        if not url or url.lower() == "nan":
            return ""
        # Strip tracking query parameters (e.g. ?trackingId=..., ?refId=...) while preserving full URL path
        return url.split("?")[0].rstrip("/")

    def _is_already_notified(self, clean_url, raw_id=None):
        """Checks if a job URL or legacy ID was already recorded in history."""
        if not clean_url:
            return True
        if clean_url in self.notified_jobs:
            return True
        # Backwards compatibility: match if history contains legacy numeric IDs or li_<id>
        if raw_id and str(raw_id).strip() in self.notified_jobs:
            return True
        match = re.search(r"/jobs/view/(\d+)", clean_url)
        if match:
            job_num = match.group(1)
            if job_num in self.notified_jobs or f"li_{job_num}" in self.notified_jobs:
                return True
        return False

    def _load_history(self):
        """Loads previously notified jobs from JSON. Supports both legacy string arrays and rich object arrays."""
        history_path = Path(self.history_file)
        self.notified_jobs_map = {}
        url_set = set()

        if history_path.exists() and history_path.is_file():
            try:
                content = history_path.read_text(encoding="utf-8").strip()
                if not content:
                    return url_set
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            u = str(item.get("url", "")).strip()
                            if u:
                                url_set.add(u)
                                self.notified_jobs_map[u] = item
                        elif isinstance(item, str) and item.strip():
                            u = item.strip()
                            url_set.add(u)
                            self.notified_jobs_map[u] = {
                                "url": u,
                                "name": "Previously Notified",
                                "location": "Unknown",
                                "years_of_experience": "Not Specified",
                                "skills": []
                            }
                return url_set
            except json.JSONDecodeError:
                return set()
        history_path.parent.mkdir(parents=True, exist_ok=True)
        return set()

    def _save_history(self):
        """Saves updated history list of rich job objects to disk (preserves latest 5,000 entries)."""
        history_path = Path(self.history_file)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        records = list(self.notified_jobs_map.values())[-5000:]
        with history_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    def _extract_experience(self, description, row_exp=None, job_level=None):
        """Extracts required years of experience from structured fields or description text."""
        # 1. Structured experience field from JobSpy if present
        if row_exp and str(row_exp).strip() and str(row_exp).lower() not in ("nan", "none", "not specified"):
            return str(row_exp).strip()

        desc = str(description or "")
        if desc:
            patterns = [
                r"(\d+\s*(?:to|-)\s*\d+)\s*(?:\+)?\s*(?:years?|yrs?)\b(?:\s+of)?(?:\s+(?:relevant|hands-on|professional|work))?\s+experience",
                r"(\d+\+?)\s*(?:years?|yrs?)\b(?:\s+of)?(?:\s+(?:relevant|hands-on|professional|work))?\s+experience",
                r"(?:experience|exp)[\s:]+(?:at\s+least\s+)?(\d+\s*(?:to|-)\s*\d+|\d+\+?)\s*(?:years?|yrs?)\b",
                r"(?:minimum|min|at least)\s+(\d+\+?)\s*(?:years?|yrs?)\b(?:\s+of)?\s+experience",
            ]
            for pattern in patterns:
                match = re.search(pattern, desc, re.IGNORECASE)
                if match:
                    return f"{match.group(1).strip()} years"

        # 2. Fallback to seniority/job level if available
        if job_level and str(job_level).strip() and str(job_level).lower() not in ("nan", "none", "not specified"):
            return str(job_level).strip()

        return "Not Specified"

    def _extract_skills(self, description, raw_skills=None):
        """Extracts key technical skills from structured fields or by scanning description text."""
        found_skills = []
        seen = set()

        # 1. Structured skills if provided by the scraper
        if raw_skills and str(raw_skills).strip() and str(raw_skills).lower() not in ("nan", "none", "not specified"):
            if isinstance(raw_skills, list):
                for s in raw_skills:
                    s_str = str(s).strip()
                    if s_str and s_str.lower() not in seen:
                        found_skills.append(s_str)
                        seen.add(s_str.lower())
            elif isinstance(raw_skills, str):
                for s in re.split(r"[,;|]+", raw_skills):
                    s_str = s.strip()
                    if s_str and s_str.lower() not in seen:
                        found_skills.append(s_str)
                        seen.add(s_str.lower())

        # 2. Regex scan in description text
        desc = str(description or "")
        if desc:
            desc_lower = desc.lower()
            for skill in COMMON_SKILLS:
                pattern = rf"(?:^|\W){re.escape(skill)}(?:$|\W)"
                if re.search(pattern, desc_lower):
                    display_name = skill.upper() if skill in UPPERCASE_SKILLS else skill.title()
                    if skill.lower() not in seen:
                        found_skills.append(display_name)
                        seen.add(skill.lower())

        return found_skills[:12] if found_skills else ["Not Specified"]

    def _normalize_tech_text(self, text):
        """Normalizes common technology terms so 'front-end', 'c/c++', and 'react.js' match reliably."""
        t = text.lower()
        t = re.sub(r"\bfront[\s-]end\b", "frontend", t)
        t = re.sub(r"\bback[\s-]end\b", "backend", t)
        t = re.sub(r"\bfull[\s-]stack\b", "fullstack", t)
        t = re.sub(r"\breact[\s.-]?js\b", "react", t)
        t = re.sub(r"\bnode[\s.-]?js\b", "node", t)
        t = re.sub(r"\bvue[\s.-]?js\b", "vue", t)
        t = re.sub(r"\bc\s*/\s*c\+\+", "c++", t)
        t = re.sub(r"\bcpp\b", "c++", t)
        return t

    def is_accurate_match(self, title, search_term):
        """Validates job title against search keywords and negative exclusion filters."""
        title_norm = self._normalize_tech_text(title)
        term_norm = self._normalize_tech_text(search_term)

        # 1. Negative / exclusion keyword filter
        for excluded in self.exclude_terms:
            ex_clean = excluded.lower()
            if re.search(rf"(?:^|\W){re.escape(ex_clean)}(?:$|\W)", title_norm):
                return False, f"matches exclude term '{excluded}'"

        # 2. Title relevance filter (if enabled)
        if self.match_title_only:
            # Check full search term first
            if re.search(rf"(?:^|\W){re.escape(term_norm)}(?:$|\W)", title_norm):
                return True, "matches full search term"

            # Check individual keywords (filtering out tiny words unless known tech keywords)
            known_short_tech = {"c", "c++", "c#", "go", "r", "js", "ts", "ai", "ml", "ui", "ux", "qa"}
            keywords = [
                kw for kw in re.split(r"[\s/,-]+", term_norm)
                if len(kw) >= 3 or kw in known_short_tech
            ]
            if keywords:
                for kw in keywords:
                    if re.search(rf"(?:^|\W){re.escape(kw)}(?:$|\W)", title_norm):
                        return True, f"matches keyword '{kw}'"
            return False, f"title does not contain '{search_term}' (match_title_only is enabled)"

        return True, "passed"

    def fetch_jobs(self, search_term, location):
        """Fetches job listings with backoff retry logic and error recovery."""
        timeframe_msg = f" (past {self.hours_old}h)" if self.hours_old else " (any time)"
        print(f"\n🔎 Searching {self.sites} for '{search_term}' in '{location}'{timeframe_msg}...")
        for attempt in range(1, 4):
            try:
                kwargs = {
                    "site_name": self.sites,
                    "search_term": search_term,
                    "location": location,
                    "results_wanted": self.results_wanted,
                    "is_remote": self.is_remote,
                    "verbose": 0,
                }
                if self.hours_old:
                    kwargs["hours_old"] = self.hours_old

                jobs_df = scrape_jobs(**kwargs)
                if jobs_df is None or getattr(jobs_df, "empty", True):
                    print("   -> 0 listings returned by job boards.")
                    return pd.DataFrame()
                print(f"   -> Retrieved {len(jobs_df)} raw listings from job boards.")
                return jobs_df.fillna("Not Specified")
            except Exception as exc:
                delay = attempt * 10 + random.randint(2, 5)
                print(f"   -> Warning: Attempt {attempt} failed ({exc}). Retrying in {delay}s...")
                time.sleep(delay)

        print(f"   -> Failed to retrieve jobs for '{search_term}' in '{location}' after 3 attempts.")
        return pd.DataFrame()

    def send_telegram_messages(self, jobs):
        """Sends new jobs in well-formatted, batched HTML Telegram messages."""
        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        sent_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

        # Split jobs into batches of 5 to avoid Telegram character limits
        batch_size = 5
        batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
        total_batches = len(batches)

        for batch_idx, batch in enumerate(batches, start=1):
            entries = []
            for item_idx, job in enumerate(batch, start=(batch_idx - 1) * batch_size + 1):
                title = html.escape(str(job["name"]))
                company = html.escape(str(job["company"]))
                location = html.escape(str(job["location"]))
                url = job["url"]
                site = html.escape(str(job.get("site", "Job")).capitalize())
                experience = html.escape(str(job.get("years_of_experience", "Not Specified")))
                skills = job.get("skills", [])
                skills_str = html.escape(", ".join(skills[:6])) if skills else "Not Specified"

                entry = (
                    f"<b>{item_idx}. <a href=\"{url}\">{title}</a></b>\n"
                    f"🏢 <b>Company:</b> {company}\n"
                    f"📍 <b>Location:</b> {location} ({site})\n"
                    f"⏳ <b>Experience:</b> {experience}\n"
                    f"🛠️ <b>Skills:</b> {skills_str}"
                )
                if job.get("job_type") and job["job_type"] != "Not Specified":
                    entry += f"\n💼 <b>Type:</b> {html.escape(str(job['job_type']))}"
                entries.append(entry)

            message = (
                f"🎯 <b>Job Matches ({batch_idx}/{total_batches})</b> | <i>{sent_at}</i>\n"
                f"Found {len(jobs)} new jobs\n\n"
                + "\n\n".join(entries)
            )

            try:
                res = requests.post(
                    api_url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "link_preview_options": {"is_disabled": True},
                    },
                    timeout=15,
                )
                res.raise_for_status()
                time.sleep(1)
            except requests.exceptions.RequestException as err:
                print(f"Failed to send Telegram message: {err}")
                return False

        return True

    def run(self):
        """Executes search, filters for accuracy, extracts metadata, deduplicates, and alerts."""
        new_jobs = []
        pending_records = {}
        raw_total = 0
        filtered_count = 0
        duplicate_count = 0

        for search_term in self.search_terms:
            for location in self.locations:
                jobs_df = self.fetch_jobs(search_term, location)
                if jobs_df.empty:
                    time.sleep(random.uniform(3, 5))
                    continue

                raw_total += len(jobs_df)
                for _, row in jobs_df.iterrows():
                    job_url = str(row.get("job_url", "")).strip()
                    title = str(row.get("title", "Unknown")).strip()
                    company = str(row.get("company", "Unknown")).strip()
                    location = str(row.get("location", "Unknown")).strip()
                    clean_url = self._clean_job_url(job_url)

                    if not clean_url:
                        continue

                    # Accuracy check: Title relevance & exclusions
                    is_match, reason = self.is_accurate_match(title, search_term)
                    if not is_match:
                        print(f"   ⏩ [Filtered Out] '{title}' at {company} ({reason})")
                        filtered_count += 1
                        continue

                    # Deduplication check by full clean URL
                    if clean_url in pending_records or self._is_already_notified(clean_url, row.get("id")):
                        print(f"   🔁 [Already Seen] '{title}' at {company}")
                        duplicate_count += 1
                        continue

                    # Extract Years of Experience & Required Skills
                    description = str(row.get("description", ""))
                    experience = self._extract_experience(
                        description=description,
                        row_exp=row.get("experience_range"),
                        job_level=row.get("job_level")
                    )
                    skills = self._extract_skills(
                        description=description,
                        raw_skills=row.get("skills")
                    )

                    print(f"   ✅ [New Match] '{title}' at {company} | Exp: {experience} | Skills: {len(skills)}")

                    job_record = {
                        "url": clean_url,
                        "name": title,
                        "company": company,
                        "location": location,
                        "years_of_experience": experience,
                        "skills": skills,
                        "site": str(row.get("site", "job")),
                        "job_type": str(row.get("job_type", "")),
                        "date_notified": datetime.now().astimezone().isoformat(timespec="seconds")
                    }

                    new_jobs.append(job_record)
                    pending_records[clean_url] = job_record

                # Randomized sleep between queries to avoid bot detection
                time.sleep(random.uniform(4, 7))

        print(f"\n📊 Summary: {raw_total} scraped | {len(new_jobs)} new matches | {filtered_count} filtered out | {duplicate_count} already notified.")

        if new_jobs:
            if self.send_telegram_messages(new_jobs):
                for clean_url, record in pending_records.items():
                    self.notified_jobs.add(clean_url)
                    self.notified_jobs_map[clean_url] = record
                self._save_history()
                print(f"🎉 Successfully notified {len(new_jobs)} jobs to Telegram and saved rich records!")
            else:
                print("⚠️ Failed to dispatch Telegram alerts; jobs will retry next run.")
        elif raw_total > 0:
            print("ℹ️ Jobs were found on the boards, but none matched your current filter settings or all were already notified.")
            print("   👉 Tip: In JsonConfigurqation.json, set 'match_title_only': false, or empty 'exclude_terms', or remove 'hours_old'.")
        else:
            print("ℹ️ The job boards returned 0 listings for your search terms and location.")


if __name__ == "__main__":
    try:
        app_config = load_configuration()
    except Exception as exc:
        raise SystemExit(f"Configuration error: {exc}") from None

    bot = JobNotifierBot(app_config)
    bot.run()