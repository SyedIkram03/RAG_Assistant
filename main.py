import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import re
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

class CalendarBot:
    def __init__(self):
        self.service = None
        # Initialize Gemini client for /ask only
        try:
            self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        except:
            self.client = None
        
    def get_calendar_service(self):
        """Authenticate and return Google Calendar service"""
        if self.service:
            return self.service
            
        creds = None
        
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise FileNotFoundError(
                        "credentials.json not found! Please download it from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('calendar', 'v3', credentials=creds)
        return self.service
    
    def parse_datetime(self, text):
        """Parse datetime from natural language text"""
        text = text.lower().strip()
        now = datetime.now()
        
        # Extract time if present
        time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)', text)
        event_time = None
        
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            meridiem = time_match.group(3)
            
            if meridiem == 'pm' and hour != 12:
                hour += 12
            elif meridiem == 'am' and hour == 12:
                hour = 0
                
            event_time = f"{hour:02d}:{minute:02d}"
        
        # Parse date
        event_date = None
        
        # Check for "today"
        if 'today' in text:
            event_date = now.date()
        
        # Check for "tomorrow"
        elif 'tomorrow' in text:
            event_date = (now + timedelta(days=1)).date()
        
        # Check for day of week
        elif any(day in text for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            for i, day in enumerate(days):
                if day in text:
                    target_weekday = i
                    current_weekday = now.weekday()
                    days_ahead = target_weekday - current_weekday
                    
                    if days_ahead <= 0:
                        days_ahead += 7
                    
                    if 'next' in text and days_ahead < 7:
                        days_ahead += 7
                    
                    event_date = (now + timedelta(days=days_ahead)).date()
                    break
        
        # Check for specific date patterns like "15th", "on the 15th", "15"
        else:
            day_match = re.search(r'\b(\d{1,2})(st|nd|rd|th)?\b', text)
            if day_match:
                day = int(day_match.group(1))
                if 1 <= day <= 31:
                    # Assume current month or next month if day has passed
                    try:
                        event_date = datetime(now.year, now.month, day).date()
                        if event_date < now.date():
                            # Try next month
                            next_month = now.month + 1 if now.month < 12 else 1
                            next_year = now.year if now.month < 12 else now.year + 1
                            event_date = datetime(next_year, next_month, day).date()
                    except ValueError:
                        # Invalid day for month, try next month
                        next_month = now.month + 1 if now.month < 12 else 1
                        next_year = now.year if now.month < 12 else now.year + 1
                        try:
                            event_date = datetime(next_year, next_month, day).date()
                        except ValueError:
                            event_date = None
        
        # If no date found, default to today
        if event_date is None:
            event_date = now.date()
        
        return event_date, event_time
    
    def extract_title(self, text):
        """Extract event title from text by removing date/time keywords"""
        # Remove date/time indicators
        title = text
        
        # Remove time patterns
        title = re.sub(r'\d{1,2}:?\d{0,2}\s*(am|pm)', '', title, flags=re.IGNORECASE)
        
        # Remove date keywords
        keywords = ['today', 'tomorrow', 'on', 'at', 'the', 'next', 
                   'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                   'st', 'nd', 'rd', 'th']
        
        for keyword in keywords:
            title = re.sub(r'\b' + keyword + r'\b', '', title, flags=re.IGNORECASE)
        
        # Remove day numbers
        title = re.sub(r'\b\d{1,2}\b', '', title)
        
        # Clean up extra spaces
        title = ' '.join(title.split())
        
        return title.strip() or "Event"
    
    def add_event(self, title, event_date, event_time, duration_hours=1):
        """Add event to Google Calendar"""
        try:
            service = self.get_calendar_service()
            
            event = {'summary': title}
            
            if event_time:
                start_datetime = datetime.combine(event_date, datetime.strptime(event_time, '%H:%M').time())
                end_datetime = start_datetime + timedelta(hours=duration_hours)
                
                event['start'] = {'dateTime': start_datetime.isoformat(), 'timeZone': 'Asia/Kolkata'}
                event['end'] = {'dateTime': end_datetime.isoformat(), 'timeZone': 'Asia/Kolkata'}
            else:
                event['start'] = {'date': event_date.isoformat()}
                event['end'] = {'date': event_date.isoformat()}
            
            result = service.events().insert(calendarId='primary', body=event).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding event: {e}")
            raise
    
    def get_upcoming_events(self, days=30):
        """Get upcoming events for the next N days"""
        try:
            service = self.get_calendar_service()
            
            now = datetime.utcnow().isoformat() + 'Z'
            end = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'
            
            events_result = service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=end,
                maxResults=50,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            raise
    
    def find_event_by_keywords(self, keywords):
        """Find event matching keywords"""
        try:
            events = self.get_upcoming_events(days=365)
            
            keywords_lower = [k.lower() for k in keywords]
            
            for event in events:
                if event['summary'].startswith('🔔'):
                    continue
                title = event.get('summary', '').lower()
                if any(kw in title for kw in keywords_lower):
                    return event
            
            return None
        except Exception as e:
            logger.error(f"Error finding event: {e}")
            raise
    
    def update_event(self, event_id, title, event_date, event_time, duration_hours=1):
        """Update an existing event"""
        try:
            service = self.get_calendar_service()
            
            event = service.events().get(calendarId='primary', eventId=event_id).execute()
            
            event['summary'] = title
            
            if event_time:
                start_datetime = datetime.combine(event_date, datetime.strptime(event_time, '%H:%M').time())
                end_datetime = start_datetime + timedelta(hours=duration_hours)
                
                event['start'] = {'dateTime': start_datetime.isoformat(), 'timeZone': 'Asia/Kolkata'}
                event['end'] = {'dateTime': end_datetime.isoformat(), 'timeZone': 'Asia/Kolkata'}
            else:
                event['start'] = {'date': event_date.isoformat()}
                event['end'] = {'date': event_date.isoformat()}
            
            result = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
            return result
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            raise
    
    def delete_event(self, event_id):
        """Delete an event"""
        try:
            service = self.get_calendar_service()
            service.events().delete(calendarId='primary', eventId=event_id).execute()
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            raise
    
    def add_reminder(self, title, event_date, event_time):
        """Add a reminder as a calendar event"""
        try:
            service = self.get_calendar_service()
            
            reminder_datetime = datetime.combine(event_date, datetime.strptime(event_time, '%H:%M').time())
            
            event = {
                'summary': f"🔔 {title}",
                'start': {
                    'dateTime': reminder_datetime.isoformat(),
                    'timeZone': 'Asia/Kolkata'
                },
                'end': {
                    'dateTime': (reminder_datetime + timedelta(minutes=15)).isoformat(),
                    'timeZone': 'Asia/Kolkata'
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 0},
                        {'method': 'email', 'minutes': 0}
                    ]
                }
            }
            
            result = service.events().insert(calendarId='primary', body=event).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding reminder: {e}")
            raise
    
    def get_reminders(self):
        """Get all upcoming reminders"""
        events = self.get_upcoming_events(days=60)
        return [e for e in events if e.get('summary', '').startswith('🔔')]
    
    def find_reminder_by_keywords(self, keywords):
        """Find reminder matching keywords"""
        try:
            reminders = self.get_reminders()
            
            keywords_lower = [k.lower() for k in keywords]
            
            for reminder in reminders:
                title = reminder.get('summary', '').lower()
                if any(kw in title for kw in keywords_lower):
                    return reminder
            
            return None
        except Exception as e:
            logger.error(f"Error finding reminder: {e}")
            raise
    
    def ask_question(self, question):
        """Ask Gemini a general question"""
        try:
            if not self.client:
                return "Gemini API is not configured. Please add GEMINI_API_KEY to your .env file."
            
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=question
            )
            return response.text
        except Exception as e:
            logger.error(f"Error asking question: {e}")
            return f"Sorry, I couldn't process that question: {str(e)}"

# Initialize bot
bot = CalendarBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    welcome = """👋 Welcome to your Personal AI Calendar Assistant!

I help you manage your Google Calendar with simple commands.

📅 **Event Commands:**
/addevent <description> - Add a new event
/editevent <description> - Edit an existing event
/deleteevent <description> - Delete an event
/events - Show next 30 days

⏰ **Reminder Commands:**
/remindme <description> - Set a reminder
/listreminders - Show all reminders
/deletereminder <description> - Delete a reminder

💬 **Other Commands:**
/ask <question> - Ask me anything
/account - Check connected account
/help - Show this message

**Examples:**
/addevent Dinner with Zahra tomorrow at 9 pm
/remindme Call dentist on the 19th at 6:30 PM
/deleteevent graduation day
/ask What's the capital of France?

Just use the commands naturally! 🎯"""
    
    await update.message.reply_text(welcome)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    await start(update, context)

async def hi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to hi"""
    await update.message.reply_text(
        "👋 Hi there! How can I help you today?\n\n"
        "Use /help to see all available commands!"
    )

async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show connected Google account info"""
    try:
        service = bot.get_calendar_service()
        calendar = service.calendarList().get(calendarId='primary').execute()
        
        info = f"""✅ **Connected Account:**
        
📧 Email: {calendar.get('summary', 'Unknown')}
📅 Calendar: {calendar.get('id', 'primary')}
🕒 Timezone: {calendar.get('timeZone', 'Unknown')}

Everything is working correctly!"""
        
        await update.message.reply_text(info)
    except Exception as e:
        await update.message.reply_text(f"❌ Error checking account: {str(e)}")

async def add_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addevent command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide event details!\n\n"
            "Example: /addevent Dinner with Zahra tomorrow at 9 pm"
        )
        return
    
    user_message = ' '.join(context.args)
    
    try:
        event_date, event_time = bot.parse_datetime(user_message)
        title = bot.extract_title(user_message)
        
        result = bot.add_event(title, event_date, event_time)
        
        if event_time:
            dt = datetime.combine(event_date, datetime.strptime(event_time, '%H:%M').time())
            time_str = dt.strftime('%B %d at %I:%M %p')
        else:
            time_str = event_date.strftime('%B %d') + " (All day)"
        
        await update.message.reply_text(
            f"✅ **Event added!**\n\n"
            f"📅 {title}\n"
            f"🕒 {time_str}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error adding event: {str(e)}")

async def edit_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /editevent command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide event details!\n\n"
            "Example: /editevent Change graduation to next Friday at 3 PM"
        )
        return
    
    user_message = ' '.join(context.args)
    
    try:
        # Extract keywords from the message
        words = user_message.lower().split()
        keywords = [w for w in words if len(w) > 3 and w not in ['change', 'update', 'move', 'next', 'this', 'that', 'tomorrow', 'today']][:3]
        
        if not keywords:
            await update.message.reply_text("❌ Please specify which event to edit.")
            return
        
        event = bot.find_event_by_keywords(keywords)
        if not event:
            await update.message.reply_text(
                f"❌ Couldn't find an event matching your description.\n\n"
                f"Use /events to see your upcoming events."
            )
            return
        
        event_date, event_time = bot.parse_datetime(user_message)
        title = bot.extract_title(user_message)
        
        # If title is just "event", keep original title
        if title.lower() == "event":
            title = event['summary']
        
        bot.update_event(event['id'], title, event_date, event_time)
        
        if event_time:
            dt = datetime.combine(event_date, datetime.strptime(event_time, '%H:%M').time())
            time_str = dt.strftime('%B %d at %I:%M %p')
        else:
            time_str = event_date.strftime('%B %d') + " (All day)"
        
        await update.message.reply_text(
            f"✅ **Event updated!**\n\n"
            f"📅 {title}\n"
            f"🕒 {time_str}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error editing event: {str(e)}")

async def delete_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deleteevent command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please specify which event to delete!\n\n"
            "Example: /deleteevent graduation day"
        )
        return
    
    user_message = ' '.join(context.args)
    keywords = user_message.split()
    
    try:
        event = bot.find_event_by_keywords(keywords)
        if not event:
            await update.message.reply_text(
                f"❌ Couldn't find an event matching: {user_message}\n\n"
                f"Use /events to see your upcoming events."
            )
            return
        
        bot.delete_event(event['id'])
        await update.message.reply_text(f"✅ Deleted event: **{event['summary']}**")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error deleting event: {str(e)}")

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upcoming events for next 30 days"""
    try:
        events = bot.get_upcoming_events(days=30)
        
        # Filter out reminders
        events = [e for e in events if not e['summary'].startswith('🔔')]
        
        if not events:
            await update.message.reply_text("📭 No upcoming events in the next 30 days.")
            return
        
        response = "📅 **Your Upcoming Events (Next 30 Days):**\n\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            title = event['summary']
            
            if 'T' in start:
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                response += f"• **{title}**\n  📅 {dt.strftime('%B %d at %I:%M %p')}\n\n"
            else:
                dt = datetime.strptime(start, '%Y-%m-%d')
                response += f"• **{title}**\n  📅 {dt.strftime('%B %d')} (All day)\n\n"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting events: {str(e)}")

async def remind_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remindme command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide reminder details!\n\n"
            "Example: /remindme Call dentist on the 19th at 6:30 PM"
        )
        return
    
    user_message = ' '.join(context.args)
    
    try:
        event_date, event_time = bot.parse_datetime(user_message)
        
        if not event_time:
            await update.message.reply_text(
                "❌ Please specify a time for the reminder!\n\n"
                "Example: /remindme Call dentist on the 19th at 6:30 PM"
            )
            return
        
        title = bot.extract_title(user_message)
        
        result = bot.add_reminder(title, event_date, event_time)
        dt = datetime.combine(event_date, datetime.strptime(event_time, '%H:%M').time())
        
        await update.message.reply_text(
            f"✅ **Reminder set!**\n\n"
            f"🔔 {title}\n"
            f"📅 {dt.strftime('%B %d at %I:%M %p')}\n\n"
            f"You'll get a notification from Google Calendar!"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error setting reminder: {str(e)}")

async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listreminders command"""
    try:
        reminders = bot.get_reminders()
        
        if not reminders:
            await update.message.reply_text("📭 You have no upcoming reminders.")
            return
        
        response = "🔔 **Your Reminders:**\n\n"
        for r in reminders:
            title = r['summary'].replace('🔔 ', '')
            start = r['start'].get('dateTime', r['start'].get('date'))
            dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            response += f"• {title}\n  📅 {dt.strftime('%B %d at %I:%M %p')}\n\n"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting reminders: {str(e)}")

async def delete_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deletereminder command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please specify which reminder to delete!\n\n"
            "Example: /deletereminder dentist"
        )
        return
    
    user_message = ' '.join(context.args)
    keywords = user_message.split()
    
    try:
        reminder = bot.find_reminder_by_keywords(keywords)
        if not reminder:
            await update.message.reply_text(
                f"❌ Couldn't find a reminder matching: {user_message}\n\n"
                f"Use /listreminders to see your reminders."
            )
            return
        
        bot.delete_event(reminder['id'])
        title = reminder['summary'].replace('🔔 ', '')
        await update.message.reply_text(f"✅ Deleted reminder: **{title}**")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error deleting reminder: {str(e)}")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please ask a question!\n\n"
            "Example: /ask What's the weather in Hyderabad?"
        )
        return
    
    question = ' '.join(context.args)
    
    try:
        answer = bot.ask_question(question)
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands or plain text"""
    await update.message.reply_text(
        "🤔 I don't recognize that command.\n\n"
        "Use /help to see all available commands!"
    )

def main():
    """Start the bot"""
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found!")
        print("Please create a .env file with:")
        print("TELEGRAM_BOT_TOKEN=your_token_here")
        print("GEMINI_API_KEY=your_key_here")
        return
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file!")
        return
    
    # Initialize Google Calendar
    try:
        print("🔐 Checking Google Calendar authentication...")
        bot.get_calendar_service()
        print("✅ Google Calendar connected successfully!")
    except FileNotFoundError as e:
        print(f"❌ {str(e)}")
        return
    except Exception as e:
        print(f"❌ Error connecting to Google Calendar: {e}")
        return
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("hi", hi_command))
    application.add_handler(CommandHandler("account", account_info))
    
    # Event commands
    application.add_handler(CommandHandler("addevent", add_event_command))
    application.add_handler(CommandHandler("editevent", edit_event_command))
    application.add_handler(CommandHandler("deleteevent", delete_event_command))
    application.add_handler(CommandHandler("events", events_command))
    
    # Reminder commands
    application.add_handler(CommandHandler("remindme", remind_me_command))
    application.add_handler(CommandHandler("listreminders", list_reminders_command))
    application.add_handler(CommandHandler("deletereminder", delete_reminder_command))
    
    # Other commands
    application.add_handler(CommandHandler("ask", ask_command))
    
    # Handle unknown
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Start bot
    print("🤖 Bot is running! Press Ctrl+C to stop.")
    print("\n✅ All commands are working with REGEX parsing (no AI dependency for calendar operations)")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
