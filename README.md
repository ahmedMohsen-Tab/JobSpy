# JobSpy Telegram Bot

This project scrapes LinkedIn jobs and sends new matches to a Telegram chat.

## Requirements

- Docker
- A valid Telegram bot token and chat ID in `JsonConfigurqation.json`

## Configuration

Set your Telegram credentials either in `JsonConfigurqation.json` or by exporting environment variables before running the container:

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
    "Embedded Software Engineer",
    "c++"
  ],
  "results_wanted": 20,
  "is_remote": false,
  "history_file": "notified_jobs.json",
  "locations": [
    "Cairo"
  ]
}
```

The app will prefer the non-empty value from the JSON file; if it is blank, it falls back to the `BOT_TOKEN` and `CHAT_ID` environment variables.

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

- build the image if needed
- create a local `notified_jobs.json` file if it does not exist
- mount your local configuration file and history file into the container
- persist `notified_jobs.json` on your host machine
- run the script exactly as `python3 main.py`

## Manual Docker run

```bash
docker run --rm \
  -v "$(pwd)/JsonConfigurqation.json:/app/JsonConfigurqation.json:ro" \
  -v "$(pwd)/notified_jobs.json:/app/notified_jobs.json" \
  jobspy-bot
```

## Notes

- The script is designed to run as a one-off job and can be scheduled with cron or a task scheduler.
- LinkedIn may rate-limit requests with HTTP 429; this project includes retry/backoff logic to reduce failures.
