---
layout: page
title: Gaming Shorts Agent
permalink: /
---

# Gaming Shorts Agent

**A personal, experimental workflow for preparing and publishing gaming Shorts.**

Gaming Shorts Agent connects GitHub Actions, FFmpeg, YouTube Data API, Telegram, optional AI text-generation services, and optional cloud-storage providers to help its owner prepare short-form gaming videos.

## What it does

- Prepares vertical gaming videos with FFmpeg.
- Generates narration and timed captions.
- Uses configured AI services to help prepare scripts and metadata.
- Can ingest queued clips and transfer them to configured cloud storage.
- Can upload videos to the owner's connected YouTube channel.
- Sends workflow notifications and accepts owner commands through Telegram.

This is an experimental personal automation project, not a public video-hosting service. Availability depends on API access, account permissions, provider limits, and workflow configuration. A successful workflow trigger does not guarantee a successful publication.

## Data and permissions

The project uses the permissions and credentials configured by its owner. YouTube authorization is used for the owner's channel operations, such as uploading videos and, where enabled, reading channel information or managing comments/videos. Telegram is used for commands and notifications. Configured cloud and AI providers process the specific files or text sent to them by the workflow.

Read the [Privacy Policy]({{ '/privacy/' | relative_url }}) and [Terms of Use]({{ '/terms/' | relative_url }}) before using or adapting the project.

## Project source

The source code and setup notes are available in the [GitHub repository](https://github.com/shayanroyxyz/gta-shorts-agent).

## Independent project

Gaming Shorts Agent is not affiliated with or endorsed by Google, YouTube, GitHub, Telegram, Meta, MEGA, pCloud, Rockstar Games, or Take-Two Interactive. Game names and trademarks belong to their respective owners.
