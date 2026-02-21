"""
Telegram Bot - User interface for the event-driven agent
Emits events and renders projections, never owns state
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# API endpoints
AGENT_SERVICE_URL = "http://localhost:8000"
REQUEST_TIMEOUT_SECONDS = 30
GAME_NUDGE_PRIMARY_DELAY = timedelta(hours=2)
GAME_NUDGE_FOLLOWUP_DELAY = timedelta(hours=1)
GAME_NUDGE_MIN_SESSION = timedelta(hours=1)


class HTTPError(Exception):
    def __init__(self, error_text: str):
        super().__init__(error_text)
        self.error_text = error_text


class AgentBot:
    """
    Telegram bot interface
    Narrow role: emits events, renders projections
    Never edits state directly
    """

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")

    @staticmethod
    def _game_primary_job_name(chat_id: int) -> str:
        return f"game_nudge_primary:{chat_id}"

    @staticmethod
    def _game_followup_job_name(chat_id: int) -> str:
        return f"game_nudge_followup:{chat_id}"

    @staticmethod
    def _today_key() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _is_game_event(parsed_event: Dict[str, Any]) -> bool:
        return (parsed_event.get("category") or "").upper() == "GAME"

    @staticmethod
    def _is_game_start(parsed_event: Dict[str, Any]) -> bool:
        return (
            parsed_event.get("action") or ""
        ).lower() == "start" and AgentBot._is_game_event(parsed_event)

    @staticmethod
    def _is_non_game_start(parsed_event: Dict[str, Any]) -> bool:
        return (
            parsed_event.get("action") or ""
        ).lower() == "start" and not AgentBot._is_game_event(parsed_event)

    @staticmethod
    def _is_game_end(parsed_event: Dict[str, Any]) -> bool:
        return (
            parsed_event.get("action") or ""
        ).lower() == "done" and AgentBot._is_game_event(parsed_event)

    @staticmethod
    def _session_started_at_from_user_data(
        user_data: Dict[str, Any],
    ) -> datetime | None:
        raw = user_data.get("game_session_started_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    @staticmethod
    def _get_game_state(
        context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> Dict[str, Any]:
        all_state = context.application.bot_data.setdefault("game_nudge_state", {})
        if chat_id not in all_state:
            all_state[chat_id] = {}
        return all_state[chat_id]

    def _cancel_game_jobs(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> None:
        if not context.job_queue:
            return

        for job in context.job_queue.get_jobs_by_name(
            self._game_primary_job_name(chat_id)
        ):
            job.schedule_removal()
        for job in context.job_queue.get_jobs_by_name(
            self._game_followup_job_name(chat_id)
        ):
            job.schedule_removal()

    async def _handle_post_log_hooks(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        parsed_event: Dict[str, Any],
        chat_id: int,
    ) -> None:
        game_state = self._get_game_state(context, chat_id)
        action = (parsed_event.get("action") or "").lower()

        if self._is_game_start(parsed_event):
            self._cancel_game_jobs(context, chat_id)
            game_state["game_session_started_at"] = datetime.now().isoformat()
            game_state["game_nudge_waiting_response"] = False
            game_state["game_nudge_flow_stopped"] = False
            game_state["game_nudge_followup_used"] = False

            if game_state.get("game_nudge_last_sent_day") == self._today_key():
                return

            if context.job_queue:
                context.job_queue.run_once(
                    self._send_primary_game_nudge,
                    when=GAME_NUDGE_PRIMARY_DELAY,
                    chat_id=chat_id,
                    name=self._game_primary_job_name(chat_id),
                )
            return

        if self._is_non_game_start(parsed_event) or self._is_game_end(parsed_event):
            started_at = self._session_started_at_from_user_data(game_state)
            if started_at and datetime.now() - started_at < GAME_NUDGE_MIN_SESSION:
                game_state["game_nudge_flow_stopped"] = True

            self._cancel_game_jobs(context, chat_id)
            game_state["game_session_started_at"] = None
            game_state["game_nudge_waiting_response"] = False
            if action == "done":
                game_state["game_nudge_flow_stopped"] = True

    async def _send_primary_game_nudge(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not context.job or context.job.chat_id is None:
            return

        chat_id = context.job.chat_id
        game_state = self._get_game_state(context, chat_id)
        if game_state.get("game_nudge_flow_stopped"):
            return

        started_at = self._session_started_at_from_user_data(game_state)
        if not started_at:
            return

        if datetime.now() - started_at < GAME_NUDGE_PRIMARY_DELAY:
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Quick check-in - you've been gaming for a while. "
                "Want to `resume`, `still`, or `done` for today?"
            ),
        )
        game_state["game_nudge_waiting_response"] = True
        game_state["game_nudge_followup_used"] = False
        game_state["game_nudge_last_sent_day"] = self._today_key()

    async def _send_followup_game_nudge(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not context.job or context.job.chat_id is None:
            return

        chat_id = context.job.chat_id
        game_state = self._get_game_state(context, chat_id)
        if game_state.get("game_nudge_flow_stopped"):
            return

        started_at = self._session_started_at_from_user_data(game_state)
        if not started_at:
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "All good. Want to switch now (`resume`) or call it (`done`)? "
                "No pressure."
            ),
        )
        game_state["game_nudge_waiting_response"] = True
        game_state["game_nudge_followup_used"] = True

    async def _handle_game_nudge_response(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str
    ) -> bool:
        if update.effective_chat is None:
            return False

        if update.message is None:
            return False

        chat_id = update.effective_chat.id
        game_state = self._get_game_state(context, chat_id)
        if not game_state.get("game_nudge_waiting_response"):
            return False

        reply = user_input.lower().strip()

        if reply in {"done", "no", "skip", "not now", "nah"}:
            self._cancel_game_jobs(context, chat_id)
            game_state["game_nudge_flow_stopped"] = True
            game_state["game_nudge_waiting_response"] = False
            game_state["game_session_started_at"] = None
            await update.message.reply_text("Got it. No more reminders today.")
            return True

        if reply == "resume":
            self._cancel_game_jobs(context, chat_id)
            game_state["game_nudge_flow_stopped"] = True
            game_state["game_nudge_waiting_response"] = False
            game_state["game_session_started_at"] = None
            await update.message.reply_text(
                "Nice. Log your next start when you're ready, and we'll continue from there."
            )
            return True

        if reply == "still":
            if game_state.get("game_nudge_followup_used"):
                game_state["game_nudge_waiting_response"] = False
                await update.message.reply_text("All good. I won't ping again today.")
                return True

            game_state["game_nudge_waiting_response"] = False
            if context.job_queue:
                self._cancel_game_jobs(context, chat_id)
                context.job_queue.run_once(
                    self._send_followup_game_nudge,
                    when=GAME_NUDGE_FOLLOWUP_DELAY,
                    chat_id=chat_id,
                    name=self._game_followup_job_name(chat_id),
                )
            await update.message.reply_text(
                "Got it. I'll check once more in about an hour."
            )
            return True

        return False

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
        if (
            update.message is None
            or update.message.text is None
            or update.effective_user is None
        ):
            return

        user_input = update.message.text
        user_id = str(update.effective_user.id)

        logger.info(f"Received from user {user_id}: {user_input}")

        # Check if this is a confirmation response
        if await self._handle_confirmation(update, context, user_input):
            return

        # Check if this is a response to a game recovery nudge
        if await self._handle_game_nudge_response(update, context, user_input):
            return

        # Check if this is a query
        query_prefixes = (
            "what",
            "how",
            "show",
            "tell",
            "today",
            "yesterday",
            "ratio",
            "summary",
            "sessions",
            "timeline",
        )
        if user_input.lower().strip().startswith(query_prefixes):
            await self._handle_query(update, context, user_input)
            return

        # Parse as event
        await self._parse_and_suggest(update, context, user_input)

    async def _parse_and_suggest(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str
    ):
        """Parse input and show suggestion for confirmation"""
        if update.message is None:
            return

        try:
            # Call agent service to parse
            response = requests.post(
                f"{AGENT_SERVICE_URL}/parse",
                json={"input": user_input, "use_llm": False},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("status") == "needs_clarification":
                    await update.message.reply_text(
                        f"📝 {result.get('message', 'Please clarify your goal.')}"
                    )
                    return

                # Store suggestion in context for later confirmation
                context.user_data["pending_suggestion"] = result["details"]
                context.user_data["original_input"] = user_input

                # Show suggestion with inline keyboard
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "✓ Yes, log it", callback_data="confirm_yes"
                        ),
                        InlineKeyboardButton(
                            "✗ No, correct", callback_data="confirm_no"
                        ),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"🤔 I understood:\n➤ {result['suggestion']}\n\nIs this correct?",
                    reply_markup=reply_markup,
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

    async def _handle_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str
    ) -> bool:
        """
        Check if user is responding to a pending suggestion
        Returns True if handled
        """
        if update.message is None:
            return False

        pending = context.user_data.get("pending_suggestion")
        if not pending:
            return False

        # Check for natural confirmation patterns
        user_lower = user_input.lower().strip()

        if user_lower in ["yes", "y", "yeah", "yep", "correct", "right"]:
            # User confirmed
            await self._confirm_event(update, context, pending, "Yes")
            return True

        elif user_lower in ["no", "n", "nope", "wrong", "incorrect"]:
            # User rejected - ask for correction
            await update.message.reply_text(
                "📝 What should I have understood?\n"
                "(e.g., 'It was practice, not theory' or 'The activity is pandas-dataframes')"
            )
            context.user_data["awaiting_correction"] = True
            return True

        elif context.user_data.get("awaiting_correction"):
            # This is the correction
            await self._confirm_event(update, context, pending, user_input)
            context.user_data["awaiting_correction"] = False
            return True

        return False

    def _request_confirm_result(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        parsed_event: Dict[str, Any],
        user_response: str,
    ) -> Dict[str, Any]:
        response = requests.post(
            f"{AGENT_SERVICE_URL}/confirm",
            json={
                "parsed_event": parsed_event,
                "user_response": user_response,
                "original_input": context.user_data.get("original_input", ""),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise HTTPError(response.text)
        return response.json()

    @staticmethod
    def _confirm_keyboard() -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("✓ Yes", callback_data="confirm_yes"),
                InlineKeyboardButton("✗ No", callback_data="confirm_no"),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _handle_confirm_result(
        self,
        *,
        result: Dict[str, Any],
        context: ContextTypes.DEFAULT_TYPE,
        parsed_event: Dict[str, Any],
        send_message,
        chat_id: int | None,
        include_session_info: bool,
    ) -> bool:
        status = result.get("status")

        if status == "corrected":
            context.user_data["pending_suggestion"] = result["details"]
            await send_message(
                f"🔄 Corrected:\n➤ {result['suggestion']}\n\nIs this correct now?",
                reply_markup=self._confirm_keyboard(),
            )
            return False

        if status == "logged":
            msg = result["message"]
            if include_session_info and "session_info" in result:
                msg += f"\n\n📊 Session info: {result['session_info']}"
            if result.get("motivation"):
                msg += f"\n\n🔥 {result['motivation']}"
            await send_message(msg)

            if chat_id is not None:
                await self._handle_post_log_hooks(context, parsed_event, chat_id)
            return True

        await send_message(result.get("message", "Could not log this event."))
        return True

    async def _confirm_event(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        parsed_event: Dict[str, Any],
        user_response: str,
    ):
        """Send confirmation to agent service to log event"""
        if update.message is None:
            return

        should_clear_pending = True
        try:
            result = self._request_confirm_result(context, parsed_event, user_response)

            async def send_message(text: str, reply_markup=None):
                await update.message.reply_text(text, reply_markup=reply_markup)

            chat_id = update.effective_chat.id if update.effective_chat else None
            should_clear_pending = await self._handle_confirm_result(
                result=result,
                context=context,
                parsed_event=parsed_event,
                send_message=send_message,
                chat_id=chat_id,
                include_session_info=True,
            )

        except HTTPError as http_error:
            await update.message.reply_text(
                f"❌ Failed to log event. Error: {http_error.error_text}"
            )

        except requests.exceptions.Timeout:
            logger.error("Error confirming: timed out waiting for agent service")
            await update.message.reply_text(
                "⏱️ Confirm request timed out. Try again in a moment."
            )
        except Exception as e:
            logger.error(f"Error confirming: {e}")
            await update.message.reply_text("❌ Failed to log event. Please try again.")

        finally:
            # Keep pending suggestion when we are in corrected loop
            if should_clear_pending:
                context.user_data.pop("pending_suggestion", None)
                context.user_data.pop("original_input", None)

    async def _handle_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str
    ):
        """Handle query messages"""
        if update.message is None:
            return

        try:
            response = requests.post(
                f"{AGENT_SERVICE_URL}/query",
                json={"query": user_input},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 200:
                result = response.json()
                await update.message.reply_text(result["message"])
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
        if query is None:
            return
        await query.answer()

        pending = context.user_data.get("pending_suggestion")
        if not pending:
            await query.edit_message_text("❌ Session expired. Please try again.")
            return

        if query.data == "confirm_yes":
            await self._confirm_event_from_callback(query, context, pending, "Yes")

        elif query.data == "confirm_no":
            await query.edit_message_text(
                "📝 What should I have understood?\n"
                "(Reply with the correct description)"
            )
            context.user_data["awaiting_correction"] = True

    async def _confirm_event_from_callback(
        self, query, context, parsed_event, user_response
    ):
        """Confirm event from callback query"""
        should_clear_pending = True
        try:
            result = self._request_confirm_result(context, parsed_event, user_response)

            async def send_message(text: str, reply_markup=None):
                await query.edit_message_text(text, reply_markup=reply_markup)

            chat_id = query.message.chat_id if query.message is not None else None
            should_clear_pending = await self._handle_confirm_result(
                result=result,
                context=context,
                parsed_event=parsed_event,
                send_message=send_message,
                chat_id=chat_id,
                include_session_info=False,
            )

        except HTTPError as http_error:
            await query.edit_message_text(f"❌ Error: {http_error.error_text}")

        except requests.exceptions.Timeout:
            logger.error("Error in callback: timed out waiting for agent service")
            await query.edit_message_text(
                "⏱️ Timed out while confirming. Please try again."
            )
        except Exception as e:
            logger.error(f"Error in callback: {e}")
            await query.edit_message_text("❌ Failed to log event.")

        finally:
            if should_clear_pending:
                context.user_data.pop("pending_suggestion", None)
                context.user_data.pop("original_input", None)

    async def ratio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ratio command"""
        await self._handle_query(
            update, context, "What is my theory to practice ratio?"
        )

    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /today command"""
        await self._handle_query(update, context, "What did I work on today?")

    def run(self):
        """Start the bot"""
        application = Application.builder().token(self.token).build()

        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("ratio", self.ratio_command))
        application.add_handler(CommandHandler("today", self.today_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        # Start bot
        logger.info("Starting bot...")
        application.run_polling()


if __name__ == "__main__":
    bot = AgentBot()
    bot.run()
