import os
import requests
from supabase import create_client
from config import TARGET_USERS
from dotenv import load_dotenv

# .env 読み込み
load_dotenv()

# Supabase 接続
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_id_by_username(username, token):
    """
    ユーザー名からユーザーIDを取得。
    trn_xrepost_user_cache にキャッシュされていれば再利用。
    """
    res = supabase.table("trn_xrepost_user_cache").select("*").eq("username", username).execute()
    if res.data:
        return res.data[0]["user_id"]

    # キャッシュなし → API取得
    url = f"https://api.x.com/2/users/by/username/{username}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        user_id = r.json()["data"]["id"]
        # Supabase にキャッシュ保存
        supabase.table("trn_xrepost_user_cache").insert({
            "username": username,
            "user_id": user_id
        }).execute()
        print(f"💾 キャッシュ保存: {username} -> {user_id}")
        return user_id
    except Exception as e:
        print(f"❌ ユーザーID取得失敗: {username} -> {e}")
        return None

def get_latest_tweet(user_id, token):
    """
    指定ユーザーIDの最新ツイートを取得
    """
    url = f"https://api.x.com/2/users/{user_id}/tweets"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, headers=headers, params={"max_results":5})
        res.raise_for_status()
        data = res.json()
        if "data" in data and data["data"]:
            return data["data"][0]
        print(f"ℹ️ ユーザー {user_id} に新しいツイートなし")
        return None
    except Exception as e:
        print(f"❌ ツイート取得エラー: {user_id} -> {e}")
        return None

def already_reposted(target_user_id, tweet_id, bot_user_id):
    res = supabase.table("trn_xrepost_logs").select("*") \
        .eq("target_user_id", target_user_id) \
        .eq("reposted_by_user_id", bot_user_id).execute()
    return res.data and res.data[0]["last_reposted_id"] == tweet_id

def save_last_repost(target_user_id, tweet_id, bot_user_id):
    res = supabase.table("trn_xrepost_logs").select("*") \
        .eq("target_user_id", target_user_id) \
        .eq("reposted_by_user_id", bot_user_id).execute()
    
    if res.data:
        supabase.table("trn_xrepost_logs").update({"last_reposted_id": tweet_id}) \
            .eq("target_user_id", target_user_id).eq("reposted_by_user_id", bot_user_id).execute()
        print(f"✅ 更新: {bot_user_id} -> {target_user_id} の最新リポストID {tweet_id}")
    else:
        supabase.table("trn_xrepost_logs").insert({
            "target_user_id": target_user_id,
            "reposted_by_user_id": bot_user_id,
            "last_reposted_id": tweet_id
        }).execute()
        print(f"✅ 新規登録: {bot_user_id} -> {target_user_id} のリポストID {tweet_id}")

def repost(tweet_id, bot_user_id, token):
    url = f"https://api.x.com/2/users/{bot_user_id}/retweets"
    try:
        res = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json={"tweet_id": tweet_id})
        res.raise_for_status()
        print(f"🔁 リポスト成功: {bot_user_id} -> {tweet_id}")
        return res.json()
    except Exception as e:
        print(f"❌ リポスト失敗: {bot_user_id} -> {tweet_id} : {e}")
        return None

def main():
    print("🚀 Bot処理開始")
    for key, bot in TARGET_USERS.items():
        if not bot.get("enabled", False):
            print(f"⏭ Bot {bot['my_user_id']} は無効のためスキップ")
            continue

        bot_id = bot["my_user_id"]
        token = os.getenv(f"BEARER_TOKEN_{key}")
        if not token:
            print(f"⚠️ トークン未設定: {bot_id} (BEARER_TOKEN_{key})")
            continue

        print(f"🔹 Bot稼働中: {bot_id} (対象 {len(bot['target_userid'])} ユーザー)")

        for user in bot["target_userid"]:
            # ユーザーIDをキャッシュ取得
            target_user_id = get_user_id_by_username(user["id"], token)
            if not target_user_id:
                continue  # 取得失敗時はスキップ

            latest = get_latest_tweet(target_user_id, token)
            if latest:
                tweet_id = latest["id"]
                if already_reposted(target_user_id, tweet_id, bot_id):
                    print(f"ℹ️ すでにリポスト済み: {bot_id} -> {tweet_id}")
                else:
                    repost(tweet_id, bot_id, token)
                    save_last_repost(target_user_id, tweet_id, bot_id)

    print("🏁 Bot処理終了")

if __name__ == "__main__":
    main()
