import re
import os
import asyncio
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.constants import ParseMode

CONFIG_PATH = "config.txt"
STARTUP_FLAG = "startup_sent.flag"

WEEKDAY_MAP = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}

def startup_message_already_sent():
    return os.path.exists(STARTUP_FLAG)

def mark_startup_message_sent():
    with open(STARTUP_FLAG, "w") as f:
        f.write("sent")

def load_config():
    user_id = None
    bot_token = None
    start_message = None
    tasks = []

    with open(CONFIG_PATH, "r", encoding="utf8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue

        if line.startswith("USER_ID="):
            user_id = int(line.split("=", 1)[1])
            i += 1
            continue

        if line.startswith("BOT_TOKEN="):
            bot_token = line.split("=", 1)[1]
            i += 1
            continue

        # START_MESSAGE multiline
        if line.startswith("START_MESSAGE="):
            if line.endswith('"""'):  # triple quotes start and end on same line (empty message)
                start_message = ""
                i += 1
                continue

            if line.endswith('"""') and line.count('"""') == 2:
                # case: START_MESSAGE="""some message"""
                start_message = line.split('"""')[1]
                i += 1
                continue

            if line.endswith('"""'):
                # unlikely, but handle anyway
                i += 1
                continue

            # multiline START_MESSAGE begins here
            if line.endswith('"""') is False and line.count('"""') == 1:
                # remove START_MESSAGE= prefix and opening quotes
                start_message_lines = []
                # Check if triple quotes start at end of line
                if line.endswith('"""'):
                    i += 1
                else:
                    # remove prefix "START_MESSAGE="
                    prefix_removed = line[len("START_MESSAGE="):]
                    if prefix_removed.startswith('"""'):
                        prefix_removed = prefix_removed[3:]
                    start_message_lines.append(prefix_removed)
                    i += 1

                # read until closing triple quotes
                while i < len(lines) and lines[i].strip() != '"""':
                    start_message_lines.append(lines[i].rstrip('\n'))
                    i += 1
                i += 1  # skip closing """
                start_message = "\n".join(start_message_lines)
                continue

            # single line START_MESSAGE
            start_message = line.split("=", 1)[1]
            i += 1
            continue

        # Scheduled messages multiline
        m = re.match(r"([A-Z]{3})-(\d{2}):(\d{2})-\"\"\"", line)
        if m:
            weekday, hh, mm = m.groups()
            i += 1
            message_lines = []
            while i < len(lines) and lines[i].strip() != '"""':
                message_lines.append(lines[i].rstrip('\n'))
                i += 1
            i += 1  # skip closing """
            message = "\n".join(message_lines)
            tasks.append((weekday, int(hh), int(mm), message))
            continue

        # Scheduled messages single line
        m = re.match(r'([A-Z]{3})-(\d{2}):(\d{2})-"(.+)"', line)
        if m:
            weekday, hh, mm, message = m.groups()
            tasks.append((weekday, int(hh), int(mm), message))
            i += 1
            continue

        i += 1

    return user_id, tasks, bot_token, start_message

async def send_message(bot: Bot, user_id: str, message: str):
    print(f"[{datetime.now()}] Sending message to {user_id}: {message}")
    await bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.HTML)

async def schedule_jobs(bot: Bot, user_id: str, tasks, start_message: str):
    scheduler = AsyncIOScheduler()

    # Send startup message once
    if not startup_message_already_sent():
        await send_message(bot, user_id, start_message)
        mark_startup_message_sent()
    else:
        print("[INFO] Startup message suppressed (already sent).")

    # Schedule all messages according to config
    for weekday, hh, mm, message in tasks:
        # APScheduler's day_of_week: MON=0 .. SUN=6 is default, matches WEEKDAY_MAP
        trigger = CronTrigger(day_of_week=WEEKDAY_MAP[weekday], hour=hh, minute=mm)
        scheduler.add_job(send_message, trigger=trigger, args=[bot, user_id, message], name=f"{weekday}-{hh:02d}:{mm:02d}")
        print(f"[INFO] Scheduled: {weekday} {hh:02d}:{mm:02d} -> {message}")

    scheduler.start()
    print("[INFO] Scheduler started")

    # Keep the scheduler running forever
    while True:
        await asyncio.sleep(3600)

async def main():
    user_id, tasks, bot_token, start_message = load_config()
    if not all([user_id, bot_token]):
        print("[ERROR] USER_ID or BOT_TOKEN not set in config.")
        return

    bot = Bot(token=bot_token)

    try:
        await schedule_jobs(bot, user_id, tasks, start_message)
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[INFO] Bot stopped by user")
