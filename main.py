import os
import json
import asyncio
import requests
import logging
import discord
from discord.ext import commands

EPIC_DEVICE_ID     = os.getenv("EPIC_DEVICE_ID", "YOUR_DEVICE_ID")
EPIC_DEVICE_SECRET = os.getenv("EPIC_DEVICE_SECRET", "YOUR_DEVICE_SECRET")
EPIC_ACCOUNT_ID    = os.getenv("EPIC_ACCOUNT_ID", "YOUR_ACCOUNT_ID")
EPIC_CLIENT_SECRET = os.getenv(
    "EPIC_CLIENT_SECRET",
    "M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU="
)

OFFERS_URL = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/world/info"
TOKEN_URL  = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"

STATE_FILE = "old_vbucks_missons.json"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID    = int(os.getenv("CHANNEL_ID", YOUR_CHANNEL_ID ))
ROLE_ID       = int(os.getenv("ROLE_ID", YOUR_ROLE_ID )) 

POLL_INTERVAL = 60
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("STW Vbucks Tracker")

def get_refresh_token() -> str:
    payload = {
        'grant_type':  'device_auth',
        'device_id':   EPIC_DEVICE_ID,
        'secret':      EPIC_DEVICE_SECRET,
        'account_id':  EPIC_ACCOUNT_ID
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {EPIC_CLIENT_SECRET}'
    }
    resp = requests.post(TOKEN_URL, headers=headers, data=payload)
    resp.raise_for_status()
    token = resp.json().get('refresh_token')
    logger.info("Obtained new refresh token.")
    return token

def get_access_token(refresh_token: str) -> str:
    payload = {
        'grant_type':    'refresh_token',
        'refresh_token': refresh_token,
        'token_type':    'eg1'
    }
    headers = {
        'Content-Type':    'application/x-www-form-urlencoded',
        'Authorization':   f'Basic {EPIC_CLIENT_SECRET}',
        'X-Epic-Device-ID':'device_auth'
    }
    resp = requests.post(TOKEN_URL, headers=headers, data=payload)
    resp.raise_for_status()
    token = resp.json().get('access_token')
    logger.info("Fetched new access token.")
    return token

def fetch_offers(access_token: str) -> dict:
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent':    'Mozilla/5.0'
    }
    resp = requests.get(OFFERS_URL, headers=headers)
    resp.raise_for_status()
    logger.info("Fetched /world/info JSON from Epic.")
    return resp.json()


def load_seen_missions() -> list:
    if not os.path.isfile(STATE_FILE):
        return []
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                valid = [
                    entry for entry in data
                    if isinstance(entry, dict)
                    and "theaterId" in entry
                    and "quantity" in entry
                ]
                logger.info(f"Loaded {len(valid)} seen missions from the cache.")
                return valid
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading state file: {e}")
    return []

def save_seen_missions(seen: list):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(seen, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(seen)} missions to state file.")
    except IOError as e:
        logger.error(f"Error saving state file: {e}")

def get_location_and_description(offers_json: dict, theater_id: str) -> tuple[str, str]:
    theaters = offers_json.get("theaters", [])
    if not isinstance(theaters, list):
        theaters = []

    for entry in theaters:
        if not isinstance(entry, dict):
            continue
        unique_id = entry.get("uniqueId")
        if unique_id != theater_id:
            continue

        disp = ""
        desc = ""
        dn = entry.get("displayName")
        if isinstance(dn, dict):
            disp = dn.get("en", "")
        dd = entry.get("description")
        if isinstance(dd, dict):
            desc = dd.get("en", "")

        return (disp or "Unknown Location", desc or "No description available.")

    return ("Unknown Location", "No description available.")

def extract_vbucks_missions(offers_json: dict) -> list:
    missions = []
    raw_mission_alerts = offers_json.get("missionAlerts")

    if isinstance(raw_mission_alerts, dict):
        alerts = raw_mission_alerts.get("availableMissionAlerts", [])
        if not isinstance(alerts, list):
            alerts = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            theater_id = alert.get("theaterId")
            if not isinstance(theater_id, str):
                continue

            rewards = alert.get("missionAlertRewards", {})
            if not isinstance(rewards, dict):
                continue
            items = rewards.get("items", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("itemType") == "AccountResource:currency_mtxswap":
                    qty = item.get("quantity", 0)
                    if not isinstance(qty, int):
                        continue
                    location, desc = get_location_and_description(offers_json, theater_id)
                    missions.append({
                        "theaterId":    theater_id,
                        "quantity":     qty,
                        "display_name": location,
                        "description":  desc
                    })
                    break  

    elif isinstance(raw_mission_alerts, list):
        for block in raw_mission_alerts:
            if not isinstance(block, dict):
                continue
            theater_id = block.get("theaterId")
            if not isinstance(theater_id, str):
                continue

            alerts = block.get("availableMissionAlerts", [])
            if not isinstance(alerts, list):
                continue

            for alert in alerts:
                if not isinstance(alert, dict):
                    continue
                rewards = alert.get("missionAlertRewards", {})
                if not isinstance(rewards, dict):
                    continue
                items = rewards.get("items", [])
                if not isinstance(items, list):
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("itemType") == "AccountResource:currency_mtxswap":
                        qty = item.get("quantity", 0)
                        if not isinstance(qty, int):
                            continue
                        location, desc = get_location_and_description(offers_json, theater_id)
                        missions.append({
                            "theaterId":    theater_id,
                            "quantity":     qty,
                            "display_name": location,
                            "description":  desc
                        })
                        break 

    return missions

async def send_vbucks_embed(channel: discord.TextChannel, mission: dict):

    desc_text = f"{mission['display_name']}\n> V-Bucks: {mission['quantity']}"

    embed = discord.Embed(
        title=mission["description"],
        description=desc_text
    )

    role_mention = f"<@&{ROLE_ID}>"
    await channel.send(content=role_mention, embed=embed)
    logger.info(f"Sent embed for '{mission['display_name']}' worth {mission['quantity']} Vâbucks.")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    bot.loop.create_task(vbucks_tracker_loop())

async def vbucks_tracker_loop():

    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        logger.error(f"Could not find channel with ID {CHANNEL_ID}. Exiting tracker loop.")
        return

    seen_missions = load_seen_missions()
    seen_set = {(m["theaterId"], m["quantity"]) for m in seen_missions}

    while not bot.is_closed():
        try:
            refresh_token = get_refresh_token()
            access_token  = get_access_token(refresh_token)

            offers = fetch_offers(access_token)

            current_missions = extract_vbucks_missions(offers)
            logger.info(f"Found {len(current_missions)} current Vâbucks missions.")

            current_keys = {(m["theaterId"], m["quantity"]) for m in current_missions}
            seen_missions = [
                entry
                for entry in seen_missions
                if (entry["theaterId"], entry["quantity"]) in current_keys
            ]
            seen_set = {(e["theaterId"], e["quantity"]) for e in seen_missions}
            logger.info("Pruned JSON to only keep missions still in API response.")

            new_missions = []
            for m in current_missions:
                key = (m["theaterId"], m["quantity"])
                if key not in seen_set:
                    new_missions.append(m)
                    seen_set.add(key)
                    seen_missions.append({
                        "theaterId": m["theaterId"],
                        "quantity":  m["quantity"]
                    })

            logger.info(f"Identified {len(new_missions)} new missions.")

            for mission in new_missions:
                await send_vbucks_embed(channel, mission)

            save_seen_missions(seen_missions)

        except Exception as e:
            logger.error(f"[vbucks_tracker_loop] Exception: {e}", exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    if not DISCORD_TOKEN or CHANNEL_ID == 0:
        logger.error("ERROR: Set DISCORD_TOKEN and CHANNEL_ID environment variables.")
    else:
        bot.run(DISCORD_TOKEN)
