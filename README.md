# Gaming Shorts Agent

An experimental, self-hosted automation project for preparing short-form gaming videos and publishing them to a connected YouTube channel. The repository is named `gta-shorts-agent`; the OAuth application display name is **Gaming Shorts Agent**.

> **Status:** Experimental. This project is maintained for its owner's personal workflow. It is not an official product of YouTube, Google, GitHub, Telegram, Rockstar Games, Take-Two Interactive, MEGA, pCloud, Meta, or any AI provider.

## What it currently contains

- **Video rendering:** FFmpeg-based vertical 9:16 output, two gameplay segments, animated on-screen captions, and generated narration.
- **Narration and script generation:** Edge TTS plus configured AI providers (Gemini, Groq, and OpenRouter where credentials are available).
- **Cloud clip ingestion:** A GitHub Actions workflow and `loader.py` that can receive queued sources and copy verified files to configured MEGA or pCloud remotes using rclone.
- **Publishing:** YouTube Data API upload integration in `main.py`; optional Instagram publishing is present but requires separate Meta credentials and configuration.
- **Owner notifications and commands:** Telegram bot integrations for queueing, triggering workflows, and reporting status.
- **History:** Repository files such as `history.json` and `config.json are used to track processed sources and the latest published video.

Features depend on valid credentials, API availability, provider limits, and workflow configuration. A workflow being triggered does not guarantee a successful upload.

## Important storage clarification

The loader currently downloads an input file to temporary storage on the GitHub Actions runner (under `/tmp`) before uploading it to a configured cloud remote. It is **not** a zero-byte or direct cloud-to-cloud transfer. Temporary runner storage, bandwidth, GitHub Actions minutes, and third-party storage quotas may be used.

## Repository layout

- `main.py` — content preparation, rendering orchestration, and publishing.
- `render_engine.py` — narration, captions, and FFmpeg rendering.
- `loader.py` — source ingestion and cloud transfer.
- `render_bot.py`, `telegram_bot.py` — Telegram control and notifications.
- `.github/workflows/` — GitHub Actions workflows.
- `history.json`, `config.json`, `links.txt` — project state and queue files.
- `docs/` — public project homepage, privacy policy, and terms.

## Setup overview

This is a technical project and requires familiarity with GitHub Actions, API credentials, OAuth, Telegram bots, rclone, and the connected storage providers.

1. Fork or clone the repository and review the source code before enabling workflows.
2. Configure only the GitHub Actions secrets required by the workflows you intend to use.
3. Configure the OAuth client and authorize the YouTube account that owns the channel.
4. Configure Telegram and, if used, the rclone remotes for MEGA/pCloud.
5. Review each workflow's triggers and permissions before enabling scheduled execution.
6. Run a manual test with a video you own or are authorized to use. Confirm the rendered file and the YouTube result before relying on scheduled runs.

### GitHub Actions secrets

Secret names referenced by the current workflows/code include:

- `GH_PAT` (repository Contents read/write for the workflow's Git operations, if used)
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `TELEGRAM_CHANNEL_ID`
- `RCLONE_CONF`
- `GEMINI_API_KEY`, optional `GROQ_API_KEY`, `OPENROUTER_API_KEY`
- `TG_API_ID`, `TG_API_HASH` (for the Telegram ingestion path)
- `YT_COOKIES` (only where a permitted source workflow requires it; never commit cookies)
- `IG_USER_ID`, `IG_ACCESS_TOKEN` (optional Instagram integration)

Do **not** put tokens, passwords, cookies, refresh tokens, or private configuration in source files, issues, screenshots, or commits. Never share secret values in a chat.

## Content and rights

Only process gameplay clips, music, images, and other material that you created, own, or have permission to use. Check the applicable platform terms and licenses. The project does not grant rights to third-party game footage, music, or other content. Avoid misleading metadata, spam, repetitive uploads, and attempts to evade platform safeguards.

## Public website and policies

- [Project homepage](./docs/index.md)
- [Privacy policy](./docs/privacy.md)
- [Terms of use](./docs/terms.md)

The policy documents describe the current repository implementation as inspected and should be updated whenever the code, providers, or data handling changes. They are informational project documents, not legal advice.

## Troubleshooting

- Review the failed GitHub Actions run and its step logs.
- Check that required secrets exist and have the minimum permissions needed.
- Do not repeatedly retry failed uploads without checking whether the video already published.
- For OAuth errors, check the consent-screen scopes and reauthorization status; do not expose the refresh token.
- For cloud transfer failures, check the rclone remote configuration and confirm the destination file exists and has the expected size.

## Support

For project questions, use the repository's GitHub Issues. Do not post credentials, personal data, private video links, or account identifiers in public issues.

## License

No license is currently declared for this repository. Unless a license is added, standard copyright applies and reuse is not automatically permitted.
