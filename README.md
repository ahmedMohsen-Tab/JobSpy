# JobSpy Telegram Bot

This project scrapes jobs across multiple job boards (LinkedIn, Bayt, Indeed, Glassdoor) and sends accurate, deduplicated matches to a Telegram chat.

## Requirements

- Docker
- A valid Telegram bot token and chat ID in `JsonConfigurqation.json` or as environment variables.

## Configuration

Set your Telegram credentials and search preferences in `JsonConfigurqation.json` or by exporting environment variables before running:

```bash
export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
export CHAT_ID="YOUR_TELEGRAM_CHAT_ID"
```

Example `JsonConfigurqation.json`:

```json
{
  "bot_token": "",
  "chat_id": "",
  "search_terms": [
    "frontend", "backend", "fullstack", "react"
  ],
  "locations": [
    "Cairo, Egypt"
  ],
  "sites": [
    "linkedin", "bayt"
  ],
  "results_wanted": 20,
  "hours_old": 48,
  "is_remote": false,
  "match_title_only": true,
  "exclude_terms": [
    "senior", "lead", "principal", "manager", "director", "intern"
  ],
  "history_file": "notified_jobs.json"
}
```

### Accuracy Settings
- **`match_title_only`** (`true`/`false`): Filters out jobs where your search term is only mentioned in the description, keeping only relevant title matches.
- **`exclude_terms`**: List of negative keywords. Any job title containing these words (e.g., senior, intern) is excluded.
- **`hours_old`**: Only pulls listings posted within the last N hours (e.g., 24 or 48), avoiding old stale listings.
- **`sites`**: List of job boards to scrape (`linkedin`, `bayt`, `indeed`, `glassdoor`). Combining boards increases coverage and mitigates LinkedIn rate-limiting.

## Build the Docker image

```bash
./run.sh build
```

or:

```bash
docker build -t jobspy-bot .
```

## Run the container

```bash
./run.sh run
```

This command will:
- Build the image if needed
- Safely persist and preserve `notified_jobs.json` on your host machine
- Run the scraper and send formatted HTML alerts to Telegram
