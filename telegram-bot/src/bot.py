"""
Telegram Bot - User interface for the event-driven agent
Emits events and renders projections, never owns state
"""
import os
import logging
import requests
from datetime import datetime
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API endpoints
AGENT_SERVICE_URL = "http://localhost:8000"
REQUEST_TIMEOUT_SECONDS = 30

class AgentBot:
    """
    Telegram bot interface
    Narrow role: emits events, renders projections
    Never edits state directly
    """
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "👋 Welcome to your Event Agent!\n\n"
            "I help you track your activities and learning.\n\n"
            "Just tell me what you're doing:\n"
            "• 'Starting pandas theory'\n"
            "• 'Done with database refactor'\n"
            "• 'What did I work on yesterday?'\n\n"
            "I'll suggest the structured event, you confirm with 'Yes' or correct me."
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "📚 Commands:\n\n"
            "/start - Welcome message\n"
            "/help - This help message\n"
            "/query <question> - Ask about your activities\n"
            "/ratio - Show theory to practice ratio\n"
            "/today - Today's summary\n\n"
            "Just type what you're doing naturally!"
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle natural language messages
        Parse input, show suggestion, wait for confirmation
        """
        user_input = update.message.text
        user_id = str(update.effective_user.id)
        
        logger.info(f"Received from user {user_id}: {user_input}")
        
        # Check if this is a confirmation response
        if await self._handle_confirmation(update, context, user_input):
            return
        
        # Check if this is a query
        query_prefixes = ('what', 'how', 'show', 'tell', 'today', 'yesterday', 'ratio', 'summary', 'sessions', 'timeline')
        if user_input.lower().strip().startswith(query_prefixes):
            await self._handle_query(update, context, user_input)
            return
        
        # Parse as event
        await self._parse_and_suggest(update, context, user_input)
    
    async def _parse_and_suggest(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Parse input and show suggestion for confirmation"""
        try:
            # Call agent service to parse
            response = requests.post(
                f"{AGENT_SERVICE_URL}/parse",
                json={'input': user_input, 'use_llm': False},
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Store suggestion in context for later confirmation
                context.user_data['pending_suggestion'] = result['details']
                context.user_data['original_input'] = user_input
                
                # Show suggestion with inline keyboard
                keyboard = [
                    [
                        InlineKeyboardButton("✓ Yes, log it", callback_data='confirm_yes'),
                        InlineKeyboardButton("✗ No, correct", callback_data='confirm_no')
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"🤔 I understood:\n"
                    f"➤ {result['suggestion']}\n\n"
                    f"Is this correct?",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    f"❌ Sorry, I couldn't parse that. Error: {response.text}"
                )
        
        except requests.exceptions.Timeout:
            logger.error("Error parsing: timed out waiting for agent service")
            await update.message.reply_text(
                "⏱️ Agent service timed out. Make sure it is running, then try again."
            )
        except Exception as e:
            logger.error(f"Error parsing: {e}")
            await update.message.reply_text(
                "❌ Sorry, something went wrong. Please try again."
            )
    
    async def _handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str) -> bool:
        """
        Check if user is responding to a pending suggestion
        Returns True if handled
        """
        pending = context.user_data.get('pending_suggestion')
        if not pending:
            return False
        
        # Check for natural confirmation patterns
        user_lower = user_input.lower().strip()
        
        if user_lower in ['yes', 'y', 'yeah', 'yep', 'correct', 'right']:
            # User confirmed
            await self._confirm_event(update, context, pending, 'Yes')
            return True
        
        elif user_lower in ['no', 'n', 'nope', 'wrong', 'incorrect']:
            # User rejected - ask for correction
            await update.message.reply_text(
                "📝 What should I have understood?\n"
                "(e.g., 'It was practice, not theory' or 'The activity is pandas-dataframes')"
            )
            context.user_data['awaiting_correction'] = True
            return True
        
        elif context.user_data.get('awaiting_correction'):
            # This is the correction
            await self._confirm_event(update, context, pending, user_input)
            context.user_data['awaiting_correction'] = False
            return True
        
        return False
    
    async def _confirm_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           parsed_event: Dict[str, Any], user_response: str):
        """Send confirmation to agent service to log event"""
        should_clear_pending = True
        try:
            response = requests.post(
                f"{AGENT_SERVICE_URL}/confirm",
                json={
                    'parsed_event': parsed_event,
                    'user_response': user_response,
                    'original_input': context.user_data.get('original_input', '')
                },
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result['status'] == 'logged':
                    msg = result['message']
                    if 'session_info' in result:
                        info = result['session_info']
                        msg += f"\n\n📊 Session info: {info}"
                    if result.get('motivation'):
                        msg += f"\n\n🔥 {result['motivation']}"
                    await update.message.reply_text(msg)
                
                elif result['status'] == 'corrected':
                    should_clear_pending = False
                    # Show new suggestion
                    keyboard = [
                        [
                            InlineKeyboardButton("✓ Yes", callback_data='confirm_yes'),
                            InlineKeyboardButton("✗ No", callback_data='confirm_no')
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # Update pending suggestion
                    context.user_data['pending_suggestion'] = result['details']
                    
                    await update.message.reply_text(
                        f"🔄 Corrected:\n"
                        f"➤ {result['suggestion']}\n\n"
                        f"Is this correct now?",
                        reply_markup=reply_markup
                    )
            else:
                await update.message.reply_text(
                    f"❌ Failed to log event. Error: {response.text}"
                )
        
        except requests.exceptions.Timeout:
            logger.error("Error confirming: timed out waiting for agent service")
            await update.message.reply_text(
                "⏱️ Confirm request timed out. Try again in a moment."
            )
        except Exception as e:
            logger.error(f"Error confirming: {e}")
            await update.message.reply_text(
                "❌ Failed to log event. Please try again."
            )
        
        finally:
            # Keep pending suggestion when we are in corrected loop
            if should_clear_pending:
                context.user_data.pop('pending_suggestion', None)
                context.user_data.pop('original_input', None)
    
    async def _handle_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Handle query messages"""
        try:
            response = requests.post(
                f"{AGENT_SERVICE_URL}/query",
                json={'query': user_input},
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                result = response.json()
                await update.message.reply_text(result['message'])
            else:
                await update.message.reply_text(
                    "❌ Sorry, I couldn't process that query."
                )
        
        except requests.exceptions.Timeout:
            logger.error("Error querying: timed out waiting for agent service")
            await update.message.reply_text(
                "⏱️ Query timed out. Try again, or check that the agent service is running."
            )
        except Exception as e:
            logger.error(f"Error querying: {e}")
            await update.message.reply_text(
                "❌ Error processing query. Please try again."
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses"""
        query = update.callback_query
        await query.answer()
        
        pending = context.user_data.get('pending_suggestion')
        if not pending:
            await query.edit_message_text("❌ Session expired. Please try again.")
            return
        
        if query.data == 'confirm_yes':
            await self._confirm_event_from_callback(query, context, pending, 'Yes')
        
        elif query.data == 'confirm_no':
            await query.edit_message_text(
                "📝 What should I have understood?\n"
                "(Reply with the correct description)"
            )
            context.user_data['awaiting_correction'] = True
    
    async def _confirm_event_from_callback(self, query, context, parsed_event, user_response):
        """Confirm event from callback query"""
        should_clear_pending = True
        try:
            response = requests.post(
                f"{AGENT_SERVICE_URL}/confirm",
                json={
                    'parsed_event': parsed_event,
                    'user_response': user_response,
                    'original_input': context.user_data.get('original_input', '')
                },
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'corrected':
                    should_clear_pending = False
                    context.user_data['pending_suggestion'] = result['details']
                    keyboard = [
                        [
                            InlineKeyboardButton("✓ Yes", callback_data='confirm_yes'),
                            InlineKeyboardButton("✗ No", callback_data='confirm_no')
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(
                        f"🔄 Corrected:\n"
                        f"➤ {result['suggestion']}\n\n"
                        f"Is this correct now?",
                        reply_markup=reply_markup
                    )
                else:
                    msg = result['message']
                    if result.get('motivation'):
                        msg += f"\n\n🔥 {result['motivation']}"
                    await query.edit_message_text(msg)
            else:
                await query.edit_message_text(f"❌ Error: {response.text}")
        
        except requests.exceptions.Timeout:
            logger.error("Error in callback: timed out waiting for agent service")
            await query.edit_message_text("⏱️ Timed out while confirming. Please try again.")
        except Exception as e:
            logger.error(f"Error in callback: {e}")
            await query.edit_message_text("❌ Failed to log event.")
        
        finally:
            if should_clear_pending:
                context.user_data.pop('pending_suggestion', None)
                context.user_data.pop('original_input', None)
    
    async def ratio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ratio command"""
        await self._handle_query(update, context, "What is my theory to practice ratio?")
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /today command"""
        await self._handle_query(update, context, "What did I work on today?")
    
    def run(self):
        """Start the bot"""
        application = Application.builder().token(self.token).build()
        
        # Add handlers
        application.add_handler(CommandHandler('start', self.start))
        application.add_handler(CommandHandler('help', self.help))
        application.add_handler(CommandHandler('ratio', self.ratio_command))
        application.add_handler(CommandHandler('today', self.today_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start bot
        logger.info("Starting bot...")
        application.run_polling()

if __name__ == '__main__':
    bot = AgentBot()
    bot.run()
