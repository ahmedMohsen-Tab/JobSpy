import os
import json
import time
import shutil
import requests
import io
import pandas as pd
from datetime import datetime
from pathlib import Path
from jobspy import scrape_jobs


def normalize_locations(locations):
    """Accepts a single location or a nonempty list of location names."""
    if isinstance(locations, str):
        locations = [locations]
    if not isinstance(locations, list) or not locations or any(
        not isinstance(location, str) or not location.strip()
        for location in locations
    ):
        raise ValueError("locations must be a nonempty list of location strings.")
    return list(dict.fromkeys(location.strip() for location in locations))


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
    config_path = Path(__file__).resolve().parent / "JsonConfigurqation.json"
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    if not isinstance(config, dict):
        raise ValueError("JsonConfigurqation.json must contain a JSON object.")

    config["bot_token"] = (config.get("bot_token") or os.environ.get("BOT_TOKEN") or "").strip()
    config["chat_id"] = (config.get("chat_id") or os.environ.get("CHAT_ID") or "").strip()

    required_keys = ("bot_token", "chat_id")
    missing_keys = [key for key in required_keys if not config.get(key)]
    if not config.get("search_terms") and not config.get("search_term"):
        missing_keys.append("search_terms")
    if missing_keys:
        raise ValueError(
            "Missing required settings. Set them in JsonConfigurqation.json or provide environment variables BOT_TOKEN and CHAT_ID. Missing: "
            + ", ".join(missing_keys)
        )
    config["search_terms"] = normalize_search_terms(
        config.get("search_terms", config.get("search_term"))
    )
    # Keep accepting the original single-location configuration.
    config["locations"] = normalize_locations(
        config.get("locations", config.get("location"))
    )
    return config


class JobNotifierBot:
    """Scrapes LinkedIn for job postings and forwards new listings to Telegram."""

    def __init__(self, bot_token, chat_id, search_term, locations, results_wanted=15,
                 is_remote=False, history_file="notified_jobs.json"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.search_terms = normalize_search_terms(search_term)
        self.locations = normalize_locations(locations)
        self.results_wanted = results_wanted
        self.is_remote = is_remote
        base_dir = Path(__file__).resolve().parent
        self.history_file = str((base_dir / history_file).resolve()) if not Path(history_file).is_absolute() else history_file
        history_path = Path(self.history_file)
        if history_path.exists() and history_path.is_dir():
            backup_path = history_path.with_name(f"{history_path.name}.invalid-dir-backup")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            history_path.rename(backup_path)
            shutil.rmtree(backup_path)
        self.notified_jobs = self._load_history()

    def _load_history(self):
        """Loads previously notified job URLs to prevent duplicate messages."""
        history_path = Path(self.history_file)
        if history_path.exists() and history_path.is_file():
            with history_path.open("r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    return set()
                return set(data)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        if history_path.exists() and history_path.is_dir():
            shutil.rmtree(history_path)
        if not history_path.exists():
            history_path.write_text("[]", encoding="utf-8")
        return set()

    def _save_history(self):
        """Saves the updated set of notified job URLs to disk."""
        history_path = Path(self.history_file)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        if history_path.exists() and history_path.is_dir():
            shutil.rmtree(history_path)
        with history_path.open("w", encoding="utf-8") as f:
            json.dump(list(self.notified_jobs), f)

    def fetch_jobs(self, search_term, location):
        """Fetches job data for one search term and location with LinkedIn rate-limit retries."""
        print(f"Searching LinkedIn for '{search_term}' in '{location}'...")
        last_error = None
        for attempt in range(4):
            try:
                jobs_df = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=search_term,
                    location=location,
                    results_wanted=max(5, min(self.results_wanted, 15)),
                    is_remote=self.is_remote,
                    verbose=0,
                )
                if jobs_df is None:
                    jobs_df = pd.DataFrame()
                if hasattr(jobs_df, "fillna"):
                    jobs_df.fillna("Not Specified", inplace=True)
                return jobs_df
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    delay = 15 * (attempt + 1)
                    print(f"LinkedIn rate-limited; retrying in {delay} seconds ({attempt + 1}/3)...")
                    time.sleep(delay)
                    continue
                raise

        if last_error is not None:
            raise last_error
        return pd.DataFrame()

    def send_telegram_digest(self, jobs):
        """Sends all new jobs in one dated Telegram message."""
        sent_at = datetime.now().astimezone().isoformat(timespec="seconds")
        entries = []
        for index, job in enumerate(jobs, start=1):
            entries.append(
                f"{index}. {job['title']}\n"
                f"Company: {job['company']}\n"
                f"Location: {job['location']}\n"
                f"URL: {job['url']}"
            )
        message = (
            f"New job matches | {sent_at}\n"
            f"Found {len(jobs)} new jobs\n\n"
            + "\n\n".join(entries)
        )
        api_url = f"https://api.telegram.org/bot{self.bot_token}"
        response = None

        try:
            if len(message) <= 4096:
                response = requests.post(
                    f"{api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "disable_web_page_preview": True
                    }
                )
            else:
                document = io.BytesIO(message.encode("utf-8"))
                response = requests.post(
                    f"{api_url}/sendDocument",
                    data={
                        "chat_id": self.chat_id,
                        "caption": f"New job matches | {sent_at}"
                    },
                    files={
                        "document": (
                            f"job_matches_{datetime.now().astimezone():%Y%m%d_%H%M%S}.txt",
                            document,
                            "text/plain"
                        )
                    }
                )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            print(f"Failed to send Telegram digest: {exc}")
            if response is not None:
                print(f"Telegram API Response: {response.text}")
            return False

    def run(self):
        """Searches each location, deduplicates alerts, and saves shared history."""
        new_jobs = []
        pending_urls = set()
        found_jobs = False
        for search_term in self.search_terms:
            for location in self.locations:
                jobs = self.fetch_jobs(search_term, location)
                if jobs is None or getattr(jobs, "empty", False):
                    time.sleep(5)
                    continue
                found_jobs = True
                for _, row in jobs.iterrows():
                    job_url = str(row.get("job_url", ""))

                    # Share URL history across all searches to avoid duplicate alerts.
                    if (
                        job_url
                        and job_url not in self.notified_jobs
                        and job_url not in pending_urls
                    ):
                        new_jobs.append({
                            "title": str(row.get("title", "Unknown")),
                            "company": str(row.get("company", "Unknown")),
                            "location": str(row.get("location", "Unknown")),
                            "url": job_url
                        })
                        pending_urls.add(job_url)
                time.sleep(5)

        if new_jobs and self.send_telegram_digest(new_jobs):
            self.notified_jobs.update(pending_urls)
            self._save_history()
            print(f"Successfully pushed {len(new_jobs)} new job alerts to Telegram.")
        elif new_jobs:
            print("Job digest was not delivered; jobs will be retried next run.")
        elif not found_jobs:
            print("No jobs found matching the criteria.")
        else:
            print("No new jobs posted since the last run.")

if __name__ == "__main__":
    try:
        config = load_configuration()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Unable to load configuration: {exc}") from None

    bot = JobNotifierBot(
        bot_token=config["bot_token"],
        chat_id=config["chat_id"],
        search_term=config["search_terms"],
        locations=config["locations"],
        results_wanted=config.get("results_wanted", 15),
        is_remote=config.get("is_remote", False),
        history_file=config.get("history_file", "notified_jobs.json")
    )

    bot.run()