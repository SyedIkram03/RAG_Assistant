# 🤖 Telegram RAG Reminder Assistant

This project is a **Telegram-based RAG (Retrieval-Augmented Generation) Assistant** that helps you manage reminders and events using simple, natural language commands.

The idea is very straightforward: instead of opening multiple apps or calendars, you just talk to a Telegram bot like a human — and it remembers things for you.

This bot is intentionally built using **only free-tier APIs**, runs completely on your **local machine**, and is beginner-friendly. No paid services, no hidden dependencies.

---

## ✨ What This Bot Can Do

- Add reminders using natural language  
  _“Remind me to submit the assignment tomorrow at 9am”_
- Add events via simple commands
- Automatically trigger reminders at the right time
- Delete reminders or events when they’re no longer needed
- Act as a **lightweight RAG Assistant**, interpreting user intent instead of strict formats
- Work fully inside Telegram
- Run locally on Windows / macOS / Linux

This is not just a command-based bot — it’s designed to **understand intent**, which is why it’s referred to as a **RAG Assistant**.

---

## 🧠 Why RAG Assistant?

The bot doesn’t rely on rigid inputs. Instead, it:

1. Takes natural language input from Telegram
2. Interprets intent (add / delete / list reminders or events)
3. Extracts time, date, and context
4. Stores and retrieves relevant reminder data when needed

That combination of **retrieval + understanding + action** is what makes it a RAG-style assistant.

---

## 🛠️ Tech Stack

- **Python 3.10+**
- **python-telegram-bot**
- **Google APIs (Free Tier)**
- **dotenv** for environment variables
- **requirements.txt** for dependency management

---

## 📂 Project Structure

```
telegram-rag-reminder-bot/
│
├── main.py              # Bot entry point
├── requirements.txt     # All Python dependencies
├── .env                 # API keys (ignored by git)
├── README.md
```

---

## 🔑 APIs Used & How to Get Them

### 1️⃣ Telegram Bot API

**Steps:**
1. Open Telegram
2. Search for **@BotFather**
3. Run:
   ```
   /start
   /newbot
   ```
4. Give your bot a name
5. Copy the **Bot Token**

Add it to `.env`:
```
BOT_TOKEN=your_telegram_bot_token_here
```

---

### 2️⃣ Google API (Free Tier)

Used for natural language handling and future extensibility.

**Steps:**
1. Go to Google Cloud Console
2. Create a new project
3. Enable required APIs (Calendar / NLP if needed)
4. Create an **API Key**

Add it to `.env`:
```
GOOGLE_API_KEY=your_google_api_key_here
```

---

## 🚀 Running the Bot Locally (From Scratch)

### Step 1: Clone the Repository

```bat
git clone https://github.com/yourusername/telegram-rag-reminder-bot.git
cd telegram-rag-reminder-bot
```

---

### Step 2: Create a Virtual Environment (Recommended)

```bat
python -m venv venv
```

Activate it:
```bat
venv\Scripts\activate
```

---

### Step 3: Install Dependencies

All dependencies are handled through **requirements.txt**:

```bat
pip install -r requirements.txt
```

No manual installs. No extra steps.

---

### Step 4: Create `.env` File

In the project root, create a file named `.env`:

```
BOT_TOKEN=your_telegram_bot_token_here
GOOGLE_API_KEY=your_google_api_key_here
```

---

### Step 5: Run the Bot

```bat
python main.py
```

If everything is set correctly, your Telegram RAG Assistant is now live.

---

## 💬 Supported Commands

| Command                            | What it does                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------- |
| `/addevent <natural language>`     | Add a calendar event using natural language                                            |
| `/editevent <natural language>`    | Edit an existing calendar event using natural language                                 |
| `/deleteevent <natural language>`  | Delete a calendar event by name or description                                         |
| `/events`                          | Show upcoming calendar events for the **next 1 month**                                 |
| `/remindme <text & time>`          | Create a reminder using natural language (e.g. “Dentist on 15th at 6:30pm”)            |
| `/listreminders`                   | List all active reminders                                                              |
| `/deletereminder <text or number>` | Delete a reminder by keyword or list index                                             |
| `/ask <question>`                  | Ask the RAG Assistant a question (uses context + AI)                                   |
| `/debugaccount`                    | Show connected Google account and calendar details                                     |
| `/hi`                              | Show the list of available commands                                                    |
| `/help`                            | Show the list of available commands                                                    |


**Example:**
```
/addreminder Team meeting tomorrow at 10am
```

---


This project intentionally uses **only one install command**:

```bat
pip install -r requirements.txt
```

---

## 🧯 Common Issues

### Bot starts but doesn’t respond
- Check if the bot token is correct
- Ensure `python main.py` is running
- Verify internet connection

---

### `NoneType` or credential-related errors
- Usually caused by missing `.env` variables
- Double-check file name and variable spelling

---

## 🔮 Possible Future Improvements

- Persistent storage (SQLite / PostgreSQL)
- Full Google Calendar sync
- Voice-based reminders
- Multi-user memory
- Advanced RAG pipeline

---

## 📜 License

MIT License — free to use, modify, and build on top of.

---

If you’re building this as a learning project or planning to expand it into a real assistant — you’re on the right path. This bot is intentionally simple, transparent, and hackable.

