import requests
from urllib.parse import quote
import time
from datetime import datetime
import base64
from dotenv import load_dotenv
import os

# -------------------------
# 환경변수 불러오기
# -------------------------
load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# -------------------------
# 유틸 함수들
# -------------------------
def get_spotify_token(client_id, client_secret):
    print("▶️ Spotify 토큰 요청 중...")
    auth = f"{client_id}:{client_secret}"
    b64_auth = base64.b64encode(auth.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    res = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    res.raise_for_status()
    token = res.json()["access_token"]
    print("✅ Spotify 토큰 발급 완료")
    return token

def search_youtube_video(query):
    print(f"🔍 YouTube 검색: {query}")
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=1&q={quote(query)}&key={YOUTUBE_API_KEY}"
    res = requests.get(url)
    res.raise_for_status()
    items = res.json().get("items", [])
    time.sleep(1)  # YouTube 제한 대응
    return items[0]["id"]["videoId"] if items else None

def make_sql(track_id, video_id, desc):
    return f"""-- {desc}
INSERT INTO track (id, mv_url)
VALUES ('{track_id}', '{video_id}')
ON DUPLICATE KEY UPDATE
    mv_url = VALUES(mv_url);"""

def load_synced_artists(file_path="synced_artists.txt"):
    if not os.path.exists(file_path):
        return set()
    with open(file_path, "r", encoding="utf-8") as f:
        return set(line.split("#")[0].strip() for line in f if line.strip())

def save_synced_artist(artist_id, artist_name, file_path="synced_artists.txt"):
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"{artist_id} # {artist_name}\n")

# -------------------------
# Spotify 요청 안전 실행
# -------------------------
def safe_get(url, headers, max_retries=3):
    for _ in range(max_retries):
        res = requests.get(url, headers=headers)
        if res.status_code == 429:
            retry_after = int(res.headers.get("Retry-After", 1))
            print(f"🕒 429 오류 발생. {retry_after}초 대기 후 재시도")
            time.sleep(retry_after)
            continue
        res.raise_for_status()
        time.sleep(0.3)
        return res
    raise Exception("❌ Spotify API 요청 실패 (429 반복)")

# -------------------------
# Spotify API 함수들
# -------------------------
SPOTIFY_TOKEN = get_spotify_token(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
HEADERS = {"Authorization": f"Bearer {SPOTIFY_TOKEN}"}

def get_artist_name(artist_id):
    url = f"https://api.spotify.com/v1/artists/{artist_id}"
    return safe_get(url, HEADERS).json()["name"]

def get_artist_top_tracks(artist_id):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks?market=KR"
    return safe_get(url, HEADERS).json()["tracks"]

def get_artist_albums(artist_id):
    albums = {}
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album&market=KR&limit=50"
    for item in safe_get(url, HEADERS).json().get("items", []):
        albums[item["id"]] = item["name"]
    return albums

def get_album_tracks(album_id):
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
    return safe_get(url, HEADERS).json().get("items", [])

def get_track_popularity(track_id):
    url = f"https://api.spotify.com/v1/tracks/{track_id}"
    return safe_get(url, HEADERS).json()["popularity"]

# -------------------------
# 아티스트 리스트
# -------------------------
artist_ids = [
    "06HL4z0CvFAxyc27GXpf02",  # Imagine Dragons
    "2h93pZq0e7k5yf4dywlkpM",  # Frank Ocean
]

synced_artists = load_synced_artists()
artist_ids = [aid for aid in artist_ids if aid not in synced_artists]

# -------------------------
# DML 출력 파일 설정
# -------------------------
output_file = "mv_upserts.sql"
today = datetime.now().strftime("%Y-%m-%d")

with open(output_file, "a", encoding="utf-8") as f:
    f.write(f"\n-- ===== {today} 수집 시작 =====\n\n")

# -------------------------
# 메인 루프
# -------------------------
for artist_id in artist_ids:
    try:
        artist_name = get_artist_name(artist_id)
        print(f"\n🎤 아티스트 처리 중: {artist_name} ({artist_id})")
        sql_lines = [f"-- {artist_name} ({artist_id})"]
        used_track_ids = set()
        added_count = 0

        # 대표곡 1개
        top_tracks = get_artist_top_tracks(artist_id)
        top_track = top_tracks[0]
        top_track_id = top_track["id"]
        top_track_name = top_track["name"]

        print(f"🎵 대표곡: {top_track_name}")
        video_id = search_youtube_video(f"{artist_name} {top_track_name} official music video")
        if video_id:
            sql_lines.append(make_sql(top_track_id, video_id, f"아티스트 대표곡: {top_track_name}"))
            used_track_ids.add(top_track_id)
            added_count += 1

        # 앨범 대표곡 최대 5개
        albums = get_artist_albums(artist_id)
        album_representatives = []

        for album_id, album_name in albums.items():
            try:
                print(f"📀 앨범 처리 중: {album_name}")
                tracks = get_album_tracks(album_id)
                if not tracks:
                    continue

                max_popularity = -1
                rep_track_id = None
                rep_track_name = None

                for track in tracks:
                    tid = track["id"]
                    tname = track["name"]
                    if tid in used_track_ids:
                        continue
                    popularity = get_track_popularity(tid)
                    if popularity > max_popularity:
                        max_popularity = popularity
                        rep_track_id = tid
                        rep_track_name = tname

                if rep_track_id:
                    album_representatives.append(
                        (album_id, album_name, rep_track_id, rep_track_name, max_popularity)
                    )

            except Exception as e:
                print(f"⚠️ 앨범 '{album_name}' 오류: {e}")

        top_albums = sorted(album_representatives, key=lambda x: x[4], reverse=True)[:5]
        for album_id, album_name, track_id, track_name, popularity in top_albums:
            if added_count >= 6:
                break
            print(f"💿 앨범 대표곡: {track_name} ({popularity})")
            if track_id not in used_track_ids:
                video_id = search_youtube_video(f"{artist_name} {track_name} official music video")
                if video_id:
                    sql_lines.append(make_sql(track_id, video_id, f"앨범: {album_name} 대표곡: {track_name}"))
                    used_track_ids.add(track_id)
                    added_count += 1

        # 보충: 부족하면 top-tracks에서 채우기
        for track in top_tracks:
            if added_count >= 6:
                break
            tid = track["id"]
            tname = track["name"]
            if tid in used_track_ids:
                continue
            print(f"➕ 보충 곡: {tname}")
            video_id = search_youtube_video(f"{artist_name} {tname} official music video")
            if video_id:
                sql_lines.append(make_sql(tid, video_id, f"추가 인기곡 보충: {tname}"))
                used_track_ids.add(tid)
                added_count += 1

        sql_lines.append(f"-- {artist_name} 끝\n")

        with open(output_file, "a", encoding="utf-8") as f:
            f.write("\n\n".join(sql_lines) + "\n\n")

        save_synced_artist(artist_id, artist_name)
        print(f"✅ 아티스트 처리 완료: {artist_name}\n")

    except Exception as e:
        print(f"❌ 아티스트 오류: {artist_id} - {e}")

with open(output_file, "a", encoding="utf-8") as f:
    f.write(f"-- ===== {today} 수집 끝 =====\n\n")
