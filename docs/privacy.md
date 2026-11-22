---
layout: page
title: Privacy Policy
permalink: /privacy/
---

**Effective date: 22 November 2026**

This Privacy Policy describes how the personal, owner-operated **Gaming Shorts Agent** software project (the “Project”) handles information when its owner runs the automation. The Project is an experimental code repository, not a hosted service offered to the public.

## 1. Information the Project may process

Depending on which features the owner enables, the Project may process:

- **YouTube account data:** OAuth credentials supplied by the owner; video upload details; video IDs; and, when owner commands request it, channel statistics or video/comment information returned by the YouTube Data API.
- **Video and source information:** video files, source URLs or Telegram message references, filenames, durations, generated scripts, captions, and file hashes.
- **Automation state:** queue entries, processing history, the latest video ID, selected content focus, and workflow logs.
- **Telegram information:** the configured bot token, owner chat/channel identifiers, messages or forwarded media used to issue commands, and notification delivery information.
- **AI and narration inputs:** prompts, topic descriptions, and script text sent to the AI or text-to-speech provider selected in the configuration.
- **Cloud-storage information:** files and file metadata transferred to the owner's configured MEGA or pCloud accounts.
- **Optional social publishing information:** Instagram account identifiers, access tokens, captions, and media supplied when the optional integration is configured.

The Project does not need a website visitor to sign in, and this static project website does not provide an account-registration form.

## 2. How information is used

Information is processed only to operate the configured workflow: prepare video content, render captions and narration, transfer source media, prevent repeated processing, publish to the owner's connected accounts, and send status notifications.

YouTube data obtained through Google APIs is used for the Project's user-facing YouTube features and is not used for advertising, sold, or intentionally shared with unrelated parties. The Project does not use Google user data to build advertising profiles.

## 3. Services that may process information

When enabled by the owner, information may pass through these providers:

- **Google / YouTube Data API:** OAuth authorization, video uploads, and selected channel/video/comment operations.
- **GitHub / GitHub Actions:** source-code hosting, workflow execution, repository state, configured Actions secrets, and workflow logs.
- **Telegram:** bot commands, notifications, and media/message references supplied to the bot.
- **Google Gemini, Groq, and OpenRouter:** prompts or text submitted for script and metadata generation, depending on which provider is configured.
- **Microsoft Edge TTS service:** text submitted to generate spoken narration.
- **MEGA and pCloud:** media files and related file metadata transferred to the owner's configured storage accounts.
- **Meta / Instagram Graph API:** media and captions when the optional Instagram publishing integration is configured.

Each provider handles information under its own terms and privacy documentation. The Project owner chooses which optional providers to connect.

## 4. Storage and retention

- OAuth tokens and API credentials are intended to be stored as GitHub Actions secrets or in the owner's private local configuration. They must not be committed to the public repository.
- Project state such as source filenames, hashes, upload timestamps, and YouTube video IDs may be committed to repository history.
- Media files may remain in the owner's configured MEGA or pCloud storage until the owner deletes them.
- The loader currently downloads source media to temporary storage on a GitHub Actions runner before transferring it to cloud storage. Temporary files and workflow logs may remain subject to the provider's retention and cleanup behavior.
- Telegram messages and notifications remain subject to Telegram's own retention and account settings.
- The Project owner is responsible for reviewing and deleting stored files, repository history, credentials, and provider-side data when no longer needed.

## 5. Security

The Project is experimental. No software system can guarantee absolute security. The owner should use least-privilege credentials, keep secrets out of source code and logs, review workflow permissions, rotate exposed credentials, and restrict access to connected accounts. Do not send passwords, OAuth refresh tokens, bot tokens, or private keys through public issues or chat.

## 6. Website visitors

This website is hosted by GitHub Pages. GitHub may process technical request information, including IP addresses, for security and service operation under GitHub's own policies. The Project does not intentionally add advertising trackers or analytics scripts to these pages.

## 7. Children's privacy

The Project is not designed as a service for collecting personal information from children. The owner should follow the age requirements and terms of every connected platform and obtain appropriate permission where required.

## 8. Your choices and questions

The Project owner can stop workflows, disconnect providers, revoke OAuth access in the relevant Google Account settings, remove Telegram bot access, and delete data held in connected storage or repository files.

For questions about this policy or the Project, use the repository's [GitHub Issues](https://github.com/shayanroyxyz/gta-shorts-agent/issues). Do not post private information or credentials in a public issue.

## 9. Changes

This policy must be updated when the Project's providers, features, or data practices change. The effective date above will be revised when material changes are made.
