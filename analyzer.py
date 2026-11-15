import os, datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def get_youtube():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build("youtube", "v3", credentials=creds)

def analyze_channel_algorithm():
    yt = get_youtube()
    ch = yt.channels().list(part="contentDetails", mine=True).execute()
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = yt.playlistItems().list(part="snippet", playlistId=uploads_id, maxResults=20).execute()
    vid_ids = [item["snippet"]["resourceId"]["videoId"] for item in pl.get("items", [])]
    if not vid_ids:
        return {"best_games": ["GTA San Andreas", "GTA 6"], "hours_since_last": 99.0, "report": "No videos yet."}

    vids = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(vid_ids)).execute().get("items", [])
    report_lines = []
    game_scores = {"GTA San Andreas": 100, "GTA 6": 100, "GTA 5": 50, "GTA 4": 50, "GTA 3": 20}
    latest_pub = None

    for v in vids:
        title = v["snippet"]["title"]
        pub_str = v["snippet"]["publishedAt"]
        pub_dt = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        if latest_pub is None or pub_dt > latest_pub:
            latest_pub = pub_dt

        stats = v.get("statistics", {})
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        score = views + (likes * 15) + (comments * 30)
        report_lines.append(f"{views} views | {likes} likes | {title[:55]}")

        for g in game_scores:
            if g.lower() in title.lower():
                game_scores[g] += score

    hours_since = 99.0
    if latest_pub:
        hours_since = (datetime.datetime.now(datetime.timezone.utc) - latest_pub).total_seconds() / 3600.0

    ranked_games = sorted(game_scores.keys(), key=lambda k: game_scores[k], reverse=True)
    summary = "\n".join(report_lines[:10])
    print("=== ALGORITHM PERFORMANCE REPORT ===")
    print(summary)
    print(f"Top Ranked Games: {ranked_games[:3]} | Hours Since Last Upload: {hours_since:.2f}h")
    return {"best_games": ranked_games[:3], "hours_since_last": hours_since, "report": summary}

if __name__ == "__main__":
    analyze_channel_algorithm()
