# bot_fun.py
# A fast and friendly ICS bot with one-liner command parsing and 12-hour time support
# pip install "python-telegram-bot==21.4" icalendar tzdata

import io
import re
import logging
import datetime as dt
from zoneinfo import ZoneInfo

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes
from icalendar import Calendar, Event, Alarm

# ===== CONFIG =====
BOT_TOKEN = "5874721630:AAEX727ifMjn-e8yULU1IrLrp71rm3rr8S0"  # replace before running
DEFAULT_TZ = "Asia/Kolkata"
DEFAULT_DURATION_MIN = 60  # when end time is not specified
MAX_REMINDER_MIN = 10080   # 7 days

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("funics")

# ===== PARSING HELPERS =====
def parse_date(text: str) -> dt.date | None:
    """Accepts YYYY-MM-DD, DD-MM-YYYY, DD-MM, DD/MM/YYYY, DD/MM.
       If year is missing, uses current year; if date already passed, rolls to next year."""
    text = text.strip()
    fmts = ("%Y-%m-%d", "%d-%m-%Y", "%d-%m", "%d/%m/%Y", "%d/%m")
    for fmt in fmts:
        try:
            d = dt.datetime.strptime(text, fmt)
            if fmt in ("%d-%m", "%d/%m"):
                today = dt.date.today()
                year = today.year
                cand = dt.date(year, d.month, d.day)
                if cand < today:
                    cand = dt.date(year + 1, d.month, d.day)
                return cand
            return d.date()
        except ValueError:
            continue
    return None

def parse_time_12_24(text: str) -> dt.time | None:
    """
    Accepts 12h and 24h:
      - 12h: '2 PM', '2:05 PM', '12 AM', '12:30 am', '8pm', '08 pm'
      - 24h: '14:05', '1405', '14'
    Returns dt.time or None.
    """
    s = text.strip().lower()

    # 12h with am/pm (allow optional space)
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", s)
    if m:
        h = int(m.group(1))
        mnt = int(m.group(2) or 0)
        ap = m.group(3)
        if not (1 <= h <= 12 and 0 <= mnt <= 59):
            return None
        if ap == "am":
            h = 0 if h == 12 else h
        else:
            h = 12 if h == 12 else h + 12
        return dt.time(hour=h, minute=mnt)

    # 12h compact like "8pm"
    m2 = re.fullmatch(r"(\d{1,2})(am|pm)", s)
    if m2:
        h = int(m2.group(1))
        ap = m2.group(2)
        if not (1 <= h <= 12):
            return None
        if ap == "am":
            h = 0 if h == 12 else h
        else:
            h = 12 if h == 12 else h + 12
        return dt.time(hour=h, minute=0)

    # 24h fallbacks
    for fmt in ("%H:%M", "%H%M", "%H"):
        try:
            t = dt.datetime.strptime(text.strip(), fmt).time()
            if fmt == "%H":
                return dt.time(hour=t.hour, minute=0)
            return t
        except ValueError:
            continue
    return None

def smart_parse(command_text: str) -> dict:
    """
    Parse:
      /event <title> @ <date> <start[-end]> [#location] [!description] [r<mins>]

    Examples:
      /event Team Sync @ 25-08 10:00 AM-11:15 AM #Office r15
      /event Dinner @ 2025-08-26 8 PM #Jubilee Hills
      /event Quick Call @ 26/08 2:30 pm
    """
    data = {
        "timezone": DEFAULT_TZ,
        "reminder": 0,
        "location": None,
        "description": None,
    }

    text = command_text.strip()
    if text.startswith("/event"):
        text = text[len("/event"):].strip()

    # Extract reminder r<mins>
    m = re.search(r"\br(\d{1,5})\b", text, flags=re.IGNORECASE)
    if m:
        mins = int(m.group(1))
        data["reminder"] = max(0, min(MAX_REMINDER_MIN, mins))
        text = (text[:m.start()] + " " + text[m.end():]).strip()

    # Extract #location (up to next control token or end)
    m = re.search(r"#([^!@r]+)", text)
    if m:
        data["location"] = m.group(1).strip()
        text = text.replace(m.group(0), "").strip()

    # Extract !description (till end)
    m = re.search(r"!(.+)$", text)
    if m:
        data["description"] = m.group(1).strip()
        text = text[:m.start()].strip()

    # Split into title and schedule by '@'
    if "@" not in text:
        data["title"] = text.strip() or "Untitled"
        data["needs_more"] = "schedule"
        return data

    title_part, schedule_part = map(str.strip, text.split("@", 1))
    data["title"] = title_part if title_part else "Untitled"

    # schedule_part expected: "<date> <time>" or "<date> <start-end>"
    parts = schedule_part.split()
    if len(parts) < 2:
        data["needs_more"] = "date_time"
        return data

    date_str = parts[0]
    time_str = parts[1]

    date_obj = parse_date(date_str)
    if not date_obj:
        data["needs_more"] = "date"
        return data

    # Time range or single time
    if "-" in time_str:
        start_str, end_str = map(str.strip, time_str.split("-", 1))
        t_start = parse_time_12_24(start_str)
        t_end = parse_time_12_24(end_str)
        if not t_start or not t_end:
            data["needs_more"] = "time_range"
            return data
        data["date"] = date_obj.isoformat()
        data["start_time"] = t_start.strftime("%H:%M")
        data["end_time"] = t_end.strftime("%H:%M")
    else:
        t_start = parse_time_12_24(time_str)
        if not t_start:
            data["needs_more"] = "time"
            return data
        data["date"] = date_obj.isoformat()
        data["start_time"] = t_start.strftime("%H:%M")
        data["end_time"] = None  # default +60 mins

    return data

# ===== ICS BUILDER =====
def build_ics(data: dict) -> bytes:
    tz = ZoneInfo(data.get("timezone") or DEFAULT_TZ)
    date = dt.date.fromisoformat(data["date"])
    sh, sm = map(int, data["start_time"].split(":"))
    dtstart = dt.datetime(date.year, date.month, date.day, sh, sm, tzinfo=tz)

    if data.get("end_time"):
        eh, em = map(int, data["end_time"].split(":"))
        dtend = dt.datetime(date.year, date.month, date.day, eh, em, tzinfo=tz)
    else:
        dtend = dtstart + dt.timedelta(minutes=DEFAULT_DURATION_MIN)

    if dtend <= dtstart:
        dtend = dtstart + dt.timedelta(minutes=DEFAULT_DURATION_MIN)

    cal = Calendar()
    cal.add("prodid", "-//Fun ICS Bot//Telegram//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    event = Event()
    event.add("uid", f"{int(dt.datetime.now(dt.timezone.utc).timestamp())}@fun-ics")
    event.add("dtstamp", dt.datetime.now(dt.timezone.utc))
    event.add("summary", data["title"])
    event.add("dtstart", dtstart)
    event.add("dtend", dtend)

    if data.get("location"):
        event.add("location", data["location"])
    if data.get("description"):
        event.add("description", data["description"])

    reminder = data.get("reminder") or 0
    if isinstance(reminder, int) and reminder > 0:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", f"Reminder: {data['title']}")
        alarm.add("trigger", dt.timedelta(minutes=-reminder))  # minutes before start
        event.add_component(alarm)

    cal.add_component(event)
    return cal.to_ical()

# ===== COMMAND HANDLERS =====
HELP_TEXT = (
    "Create and share events quickly:\n\n"
    "Syntax:\n"
    "/event <title> @ <date> <start[-end]> [#location] [!description] [r<mins>]\n\n"
    "Time supports 12-hour with AM/PM and 24-hour.\n"
    "Date supports DD-MM, DD/MM, or YYYY-MM-DD.\n"
    "Defaults: timezone Asia/Kolkata, +60m duration if end missing, no reminder unless r<mins>.\n\n"
    "Examples:\n"
    "- /event Team Sync @ 25-08 10:00 AM-11:15 AM #Office r15\n"
    "- /event Dinner @ 2025-08-26 8 PM #Jubilee Hills\n"
    "- /event Quick Call @ 26/08 2:30 pm\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Fun ICS Bot is ready 🎉\n\n"
        "Use /event to create an event in one line.\n"
        "Type /help for syntax and examples."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def event_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    try:
        data = smart_parse(text)
        # If missing schedule/title bits, ask minimally what’s needed
        if "needs_more" in data:
            need = data["needs_more"]
            if need == "schedule":
                await update.message.reply_text(
                    "Add schedule after '@'. Example:\n"
                    "/event Team Sync @ 25-08 10:00 AM-11:00 AM"
                )
            elif need == "date_time":
                await update.message.reply_text(
                    "Add date and time after '@'. Example:\n"
                    "/event Team Sync @ 25-08 10:00 AM-11:00 AM"
                )
            elif need == "date":
                await update.message.reply_text(
                    "Could not parse the date. Try formats: DD-MM, DD/MM, or YYYY-MM-DD."
                )
            elif need == "time":
                await update.message.reply_text(
                    "Could not parse the time. Try 12h like '2 PM' or '2:30 PM'."
                )
            elif need == "time_range":
                await update.message.reply_text(
                    "Could not parse time range. Use '10:00 AM-11:15 AM' or similar."
                )
            else:
                await update.message.reply_text("Please provide title, date, and time.")
            return

        # Build ICS
        ics_bytes = build_ics(data)
        filename = f"{data['title'].strip().replace(' ', '_')}.ics"
        bio = io.BytesIO(ics_bytes)
        bio.name = filename

        # Friendly echo of what was parsed
        date_disp = dt.date.fromisoformat(data["date"]).strftime("%d %b %Y")
        start_disp = data["start_time"]
        end_disp = data["end_time"] or f"+{DEFAULT_DURATION_MIN}m"
        tz_disp = data.get("timezone", DEFAULT_TZ)
        loc_disp = data.get("location") or "-"
        rem_disp = data.get("reminder") or 0

        msg = (
            f"Event ready ✅\n"
            f"- Title: {data['title']}\n"
            f"- When: {date_disp} {start_disp}–{end_disp}\n"
            f"- TZ: {tz_disp}\n"
            f"- Location: {loc_disp}\n"
            f"- Reminder: {rem_disp} min\n\n"
            f"Sending .ics…"
        )
        await update.message.reply_text(msg)
        await update.message.reply_document(InputFile(bio, filename=filename), caption="Share this .ics via WhatsApp or email.")
    except Exception as e:
        log.exception("Failed to process /event")
        await update.message.reply_text("Sorry, something went wrong creating your event. Check syntax with /help and try again.")

# ===== APP =====
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Set BOT_TOKEN first")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("event", event_cmd))
    print("Fun ICS bot running. Try /event Title @ 25-08 10:00 AM-11:00 AM #Place r15")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
