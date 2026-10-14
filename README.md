# JobSpy Telegram Bot

This project scrapes jobs across multiple job boards (LinkedIn, Bayt, Indeed, Glassdoor), parses them using **Groq AI (Llama 3.3 70B)**, and sends formatted, deduplicated matches to a Telegram chat.

## Requirements

- Docker
- A valid Telegram bot token and chat ID
- *(Optional, recommended)* A free [Groq API Key](https://console.groq.com/keys) for high-accuracy AI parsing.

## Configuration

Set your credentials in `JsonConfigurqation.json` or by exporting environment variables:

```bash
export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
export CHAT_ID="YOUR_TELEGRAM_CHAT_ID"
export GROQ_API_KEY="gsk_..."   # Optional: Enables free Llama 3.3 70B parser
```

Example `JsonConfigurqation.json`:

```json
{
  "bot_token": "",
  "chat_id": "",
  "groq_api_key": "",
  "search_terms": [
    "c++",
    "Embedded Software Engineer"
  ],
  "locations": [
    "Cairo, Egypt"
  ],
  "sites": [
    "linkedin",
    "bayt"
  ],
  "results_wanted": 25,
  "hours_old": null,
  "is_remote": false,
  "match_title_only": false,
  "exclude_terms": [],
  "history_file": "notified_jobs.json"
}
```

### Groq AI Parsing
- When `groq_api_key` is provided (via `JsonConfigurqation.json` or `GROQ_API_KEY` env var), the bot uses **Llama 3.3 70B** to intelligently extract:
  - Required **Years of Experience** (ignoring company background years).
  - Core technical **Skills**.
  - **Seniority level**.
  - A 1-sentence concise **Job Summary**.
- If no key is set or the API fails, the bot automatically falls back to regex extraction.

### Accuracy Settings
- **`match_title_only`** (`true`/`false`): Filters out jobs where your search term is only mentioned in the description, keeping only relevant title matches.
- **`exclude_terms`**: List of negative keywords. Any job title containing these words (e.g., intern) is excluded.
- **`hours_old`**: Only pulls listings posted within the last N hours (e.g., 24, 48, or `null` for all active jobs).
- **`sites`**: List of job boards to scrape (`linkedin`, `bayt`, `indeed`, `glassdoor`).

## Build and Run

```bash
./run.sh run
```

This command will:
- Build the Docker container (with fast layer caching)
- Safely persist `notified_jobs.json` on your host machine
- Run the scraper, parse with Groq AI, and deliver rich Telegram cards
