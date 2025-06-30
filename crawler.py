import requests
from urllib.parse import quote
import time
from datetime import datetime
import base64
from dotenv import load_dotenv
import os

# .env에서 환경변수 읽기
load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def get_spotify_token(client_id, client_secret):
    auth = f"{client_id}:{client_secret}"
    b64_auth = base64.b64encode(auth.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    res = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    res.raise_for_status()
    return res.json()["access_token"]

def search_youtube_video(query):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=1&q={quote(query)}&key={YOUTUBE_API_KEY}"
    res = requests.get(url)
    res.raise_for_status()
    items = res.json().get("items", [])
    return items[0]["id"]["videoId"] if items else None

def make_sql(track_id, video_id, desc):
    return f"""-- {desc}
INSERT INTO track (id, mv_url)
VALUES ('{track_id}', '{video_id}')
ON DUPLICATE KEY UPDATE
    mv_url = VALUES(mv_url);"""

SPOTIFY_TOKEN = get_spotify_token(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
HEADERS = {"Authorization": f"Bearer {SPOTIFY_TOKEN}"}

def get_artist_name(artist_id):
    url = f"https://api.spotify.com/v1/artists/{artist_id}"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()["name"]

def get_artist_top_track(artist_id):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks?market=KR"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    track = res.json()["tracks"][0]
    return track["id"], track["name"]

def get_artist_albums(artist_id):
    albums = {}
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album&market=KR&limit=50"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    for item in res.json().get("items", []):
        albums[item["id"]] = item["name"]
    return albums

def get_album_tracks(album_id):
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json().get("items", [])

def get_track_popularity(track_id):
    url = f"https://api.spotify.com/v1/tracks/{track_id}"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()["popularity"]

# 아티스트 리스트 (원하는 만큼 넣으세요)
artist_ids = [
    # "06HL4z0CvFAxyc27GXpf02",  # Taylor Swift 예시
    "3Nrfpe0tUJi4K4DXYWgMUX",  # BTS 예시
]

output_file = "mv_upserts.sql"
today = datetime.now().strftime("%Y-%m-%d")

with open(output_file, "a", encoding="utf-8") as f:
    f.write(f"\n-- ===== {today} 수집 시작 =====\n\n")

for artist_id in artist_ids:
    try:
        artist_name = get_artist_name(artist_id)
        sql_lines = [f"-- {artist_name} ({artist_id})"]

        # 아티스트 대표곡 1개
        top_track_id, top_track_name = get_artist_top_track(artist_id)
        video_id = search_youtube_video(f"{artist_name} {top_track_name} official music video")
        if video_id:
            sql_lines.append(make_sql(top_track_id, video_id, f"아티스트 대표곡: {top_track_name}"))
        time.sleep(1)

        # 앨범 조회
        albums = get_artist_albums(artist_id)
        album_representatives = []

        for album_id, album_name in albums.items():
            try:
                tracks = get_album_tracks(album_id)
                if not tracks:
                    continue

                # 트랙들 중 인기 최고 트랙 찾기
                max_popularity = -1
                rep_track_id = None
                rep_track_name = None

                for track in tracks:
                    tid = track["id"]
                    pname = track["name"]
                    popularity = get_track_popularity(tid)
                    time.sleep(0.1)  # API 과부하 방지

                    if popularity > max_popularity:
                        max_popularity = popularity
                        rep_track_id = tid
                        rep_track_name = pname

                if rep_track_id and rep_track_name:
                    album_representatives.append(
                        (album_id, album_name, rep_track_id, rep_track_name, max_popularity)
                    )

            except Exception as e:
                print(f"⚠️ 앨범 '{album_name}' 처리 중 오류: {e}")

        # 인기 순 상위 5개 앨범 대표곡만 YouTube 검색 및 SQL 생성
        top_albums = sorted(album_representatives, key=lambda x: x[4], reverse=True)[:5]
        for album_id, album_name, track_id, track_name, popularity in top_albums:
            video_id = search_youtube_video(f"{artist_name} {track_name} official music video")
            if video_id:
                sql_lines.append(make_sql(track_id, video_id, f"앨범: {album_name} 대표곡: {track_name}"))
            time.sleep(1)

        sql_lines.append(f"-- {artist_name} 끝\n")

        with open(output_file, "a", encoding="utf-8") as f:
            f.write("\n\n".join(sql_lines) + "\n\n")

    except Exception as e:
        print(f"❌ 아티스트 '{artist_id}' 처리 오류: {e}")

with open(output_file, "a", encoding="utf-8") as f:
    f.write(f"-- ===== {today} 수집 끝 =====\n\n")
