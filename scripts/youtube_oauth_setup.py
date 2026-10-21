"""
ONE-TIME, RUN ON YOUR OWN COMPUTER (never in GitHub Actions): creates the
YouTube refresh token the daily run uses to upload Shorts to the Cobble
Tales channel.

    pip install google-auth-oauthlib
    python scripts/youtube_oauth_setup.py path/to/client_secret.json

A browser window opens. Sign in with the Google account that owns the
Cobble Tales channel. If that account has more than one channel (for
example Career Edge too), Google asks which one: pick Cobble Tales. The
script then prints the channel it connected to, plus the three values to
save as GitHub Actions secrets: YT_CLIENT_ID, YT_CLIENT_SECRET,
YT_REFRESH_TOKEN. Delete client_secret.json afterwards; never commit it.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    # prompt=consent makes Google return a refresh token even if you've
    # authorized this client before (e.g. for Career Edge).
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    me = build("youtube", "v3", credentials=creds).channels().list(part="snippet", mine=True).execute()
    names = [c["snippet"]["title"] for c in me.get("items", [])]
    print(f"\nConnected to YouTube channel: {', '.join(names) or '(none found)'}")
    if names and not any("cobble" in n.lower() for n in names):
        print("WARNING: that doesn't look like the Cobble Tales channel. Run this again and pick Cobble Tales.")
    print("\n=== Save these as GitHub Actions secrets in cobble-tales-bot ===")
    print(f"YT_CLIENT_ID     = {creds.client_id}")
    print(f"YT_CLIENT_SECRET = {creds.client_secret}")
    print(f"YT_REFRESH_TOKEN = {creds.refresh_token}")
    print("================================================================")
    print("Now delete client_secret.json.")


if __name__ == "__main__":
    main()
