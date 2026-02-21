"""
Telegram Bot - User interface for the event-driven agent
Emits events and renders projections, never owns state
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")

        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        self.http: aiohttp.ClientSession | None = None

        self.pending_suggestion: Dict[int, Dict[str, Any]] = {}
        self.original_input: Dict[int, str] = {}
        self.awaiting_correction: set[int] = set()

        self.game_state: Dict[int, Dict[str, Any]] = {}
        self.game_tasks: Dict[str, asyncio.Task] = {}

    @staticmethod
    def _today_key() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _confirm_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✓ Yes, log it", callback_data="confirm_yes"
                    ),
                    InlineKeyboardButton(
                        text="✗ No, correct", callback_data="confirm_no"
                    ),
                ]
            ]
        )

    @staticmethod
    def _is_game_event(parsed_event: Dict[str, Any]) -> bool:
        return (parsed_event.get("category") or "").upper() == "GAME"

    def _is_game_start(self, parsed_event: Dict[str, Any]) -> bool:
        return (
            parsed_event.get("action") or ""
        ).lower() == "start" and self._is_game_event(parsed_event)

    def _is_non_game_start(self, parsed_event: Dict[str, Any]) -> bool:
        return (
            parsed_event.get("action") or ""
        ).lower() == "start" and not self._is_game_event(parsed_event)

    def _is_game_end(self, parsed_event: Dict[str, Any]) -> bool:
        return (
            parsed_event.get("action") or ""
        ).lower() == "done" and self._is_game_event(parsed_event)

    def _get_game_state(self, chat_id: int) -> Dict[str, Any]:
        if chat_id not in self.game_state:
            self.game_state[chat_id] = {}
        return self.game_state[chat_id]

    @staticmethod
    def _session_started_at(game_state: Dict[str, Any]) -> datetime | None:
        raw = game_state.get("game_session_started_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    @staticmethod
    def _primary_job_name(chat_id: int) -> str:
        return f"game_nudge_primary:{chat_id}"

    @staticmethod
    def _followup_job_name(chat_id: int) -> str:
        return f"game_nudge_followup:{chat_id}"

    def _cancel_game_jobs(self, chat_id: int) -> None:
        for name in (self._primary_job_name(chat_id), self._followup_job_name(chat_id)):
            task = self.game_tasks.pop(name, None)
            if task and not task.done():
                task.cancel()

    def _schedule_task(
        self, name: str, delay: timedelta, callback, chat_id: int
    ) -> None:
        async def runner() -> None:
            try:
                await asyncio.sleep(delay.total_seconds())
                await callback(chat_id)
            except asyncio.CancelledError:
                return

        self._cancel_named_task(name)
        self.game_tasks[name] = asyncio.create_task(runner(), name=name)

    def _cancel_named_task(self, name: str) -> None:
        task = self.game_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()

    async def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.http is None:
            raise RuntimeError("HTTP session not initialized")

        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with self.http.post(
            f"{AGENT_SERVICE_URL}{path}", json=payload, timeout=timeout
        ) as response:
            text = await response.text()
            if response.status != 200:
                raise HTTPError(text)
            try:
                return await response.json(content_type=None)
            except Exception:
                raise HTTPError(text)

    async def _handle_post_log_hooks(
        self, parsed_event: Dict[str, Any], chat_id: int
    ) -> None:
        game_state = self._get_game_state(chat_id)
        action = (parsed_event.get("action") or "").lower()

        if self._is_game_start(parsed_event):
            self._cancel_game_jobs(chat_id)
            game_state["game_session_started_at"] = datetime.now().isoformat()
            game_state["game_nudge_waiting_response"] = False
            game_state["game_nudge_flow_stopped"] = False
            game_state["game_nudge_followup_used"] = False

            if game_state.get("game_nudge_last_sent_day") == self._today_key():
                return

            self._schedule_task(
                self._primary_job_name(chat_id),
                GAME_NUDGE_PRIMARY_DELAY,
                self._send_primary_game_nudge,
                chat_id,
            )
            return

        if self._is_non_game_start(parsed_event) or self._is_game_end(parsed_event):
            started_at = self._session_started_at(game_state)
            if started_at and datetime.now() - started_at < GAME_NUDGE_MIN_SESSION:
                game_state["game_nudge_flow_stopped"] = True

            self._cancel_game_jobs(chat_id)
            game_state["game_session_started_at"] = None
            game_state["game_nudge_waiting_response"] = False
            if action == "done":
                game_state["game_nudge_flow_stopped"] = True

    async def _send_primary_game_nudge(self, chat_id: int) -> None:
        game_state = self._get_game_state(chat_id)
        if game_state.get("game_nudge_flow_stopped"):
            return

        started_at = self._session_started_at(game_state)
        if not started_at:
            return

        if datetime.now() - started_at < GAME_NUDGE_PRIMARY_DELAY:
            return

        await self.bot.send_message(
            chat_id=chat_id,
            text=(
                "Quick check-in - you've been gaming for a while. "
                "Want to `resume`, `still`, or `done` for today?"
            ),
        )
        game_state["game_nudge_waiting_response"] = True
        game_state["game_nudge_followup_used"] = False
        game_state["game_nudge_last_sent_day"] = self._today_key()

    async def _send_followup_game_nudge(self, chat_id: int) -> None:
        game_state = self._get_game_state(chat_id)
        if game_state.get("game_nudge_flow_stopped"):
            return

        started_at = self._session_started_at(game_state)
        if not started_at:
            return

        await self.bot.send_message(
            chat_id=chat_id,
            text=(
                "All good. Want to switch now (`resume`) or call it (`done`)? "
                "No pressure."
            ),
        )
        game_state["game_nudge_waiting_response"] = True
        game_state["game_nudge_followup_used"] = True

    async def _handle_game_nudge_response(
        self, message: Message, user_input: str
    ) -> bool:
        chat_id = message.chat.id
        game_state = self._get_game_state(chat_id)
        if not game_state.get("game_nudge_waiting_response"):
            return False

        reply = user_input.lower().strip()
        if reply in {"done", "no", "skip", "not now", "nah"}:
            self._cancel_game_jobs(chat_id)
            game_state["game_nudge_flow_stopped"] = True
            game_state["game_nudge_waiting_response"] = False
            game_state["game_session_started_at"] = None
            await message.answer("Got it. No more reminders today.")
            return True

        if reply == "resume":
            self._cancel_game_jobs(chat_id)
            game_state["game_nudge_flow_stopped"] = True
            game_state["game_nudge_waiting_response"] = False
            game_state["game_session_started_at"] = None
            await message.answer(
                "Nice. Log your next start when you're ready, and we'll continue from there."
            )
            return True

        if reply == "still":
            if game_state.get("game_nudge_followup_used"):
                game_state["game_nudge_waiting_response"] = False
                await message.answer("All good. I won't ping again today.")
                return True

            game_state["game_nudge_waiting_response"] = False
            self._schedule_task(
                self._followup_job_name(chat_id),
                GAME_NUDGE_FOLLOWUP_DELAY,
                self._send_followup_game_nudge,
                chat_id,
            )
            await message.answer("Got it. I'll check once more in about an hour.")
            return True

        return False

    async def _request_confirm_result(
        self, chat_id: int, parsed_event: Dict[str, Any], user_response: str
    ) -> Dict[str, Any]:
        return await self._post_json(
            "/confirm",
            {
                "parsed_event": parsed_event,
                "user_response": user_response,
                "original_input": self.original_input.get(chat_id, ""),
            },
        )

    async def _handle_confirm_result(
        self,
        *,
        result: Dict[str, Any],
        chat_id: int,
        parsed_event: Dict[str, Any],
        send_message: Callable[[str, InlineKeyboardMarkup | None], Awaitable[None]],
        include_session_info: bool,
    ) -> bool:
        status = result.get("status")

        if status == "corrected":
            self.pending_suggestion[chat_id] = result["details"]
            await send_message(
                f"🔄 Corrected:\n➤ {result['suggestion']}\n\nIs this correct now?",
                self._confirm_keyboard(),
            )
            return False

        if status == "logged":
            msg = result["message"]
            if include_session_info and "session_info" in result:
                msg += f"\n\n📊 Session info: {result['session_info']}"
            if result.get("motivation"):
                msg += f"\n\n🔥 {result['motivation']}"
            await send_message(msg, None)
            await self._handle_post_log_hooks(parsed_event, chat_id)
            return True

        await send_message(result.get("message", "Could not log this event."), None)
        return True

    def _clear_pending(self, chat_id: int) -> None:
        self.pending_suggestion.pop(chat_id, None)
        self.original_input.pop(chat_id, None)
        self.awaiting_correction.discard(chat_id)

    async def start_command(self, message: Message) -> None:
        await message.answer(
            "👋 Welcome to your Event Agent!\n\n"
            "I help you track your activities and learning.\n\n"
            "Just tell me what you're doing:\n"
            "• 'Starting pandas theory'\n"
            "• 'Done with database refactor'\n"
            "• 'What did I work on yesterday?'\n\n"
            "I'll suggest the structured event, you confirm with 'Yes' or correct me."
        )

    async def help_command(self, message: Message) -> None:
        await message.answer(
            "📚 Commands:\n\n"
            "/start - Welcome message\n"
            "/help - This help message\n"
            "/ratio - Show theory to practice ratio\n"
            "/today - Today's summary\n\n"
            "Just type what you're doing naturally!"
        )

    async def ratio_command(self, message: Message) -> None:
        await self._handle_query(message, "What is my theory to practice ratio?")

    async def today_command(self, message: Message) -> None:
        await self._handle_query(message, "What did I work on today?")

    async def handle_message(self, message: Message) -> None:
        if not message.text:
            return

        chat_id = message.chat.id
        user_input = message.text
        logger.info("Received from chat %s: %s", chat_id, user_input)

        if await self._handle_confirmation(message, user_input):
            return
        if await self._handle_game_nudge_response(message, user_input):
            return

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
            await self._handle_query(message, user_input)
            return

        await self._parse_and_suggest(message, user_input)

    async def _parse_and_suggest(self, message: Message, user_input: str) -> None:
        chat_id = message.chat.id
        try:
            result = await self._post_json(
                "/parse",
                {"input": user_input, "use_llm": False, "user_id": str(chat_id)},
            )

            if result.get("status") == "needs_clarification":
                await message.answer(
                    f"📝 {result.get('message', 'Please clarify your goal.')}"
                )
                return

            self.pending_suggestion[chat_id] = result["details"]
            self.original_input[chat_id] = user_input

            await message.answer(
                f"🤔 I understood:\n➤ {result['suggestion']}\n\nIs this correct?",
                reply_markup=self._confirm_keyboard(),
            )
        except aiohttp.ClientError as e:
            logger.error("Error parsing via agent service: %s", e)
            await message.answer(
                "❌ Sorry, I couldn't parse that right now. Try again."
            )
        except HTTPError as e:
            await message.answer(
                f"❌ Sorry, I couldn't parse that. Error: {e.error_text}"
            )

    async def _handle_confirmation(self, message: Message, user_input: str) -> bool:
        chat_id = message.chat.id
        pending = self.pending_suggestion.get(chat_id)
        if not pending:
            return False

        user_lower = user_input.lower().strip()
        if user_lower in {"yes", "y", "yeah", "yep", "correct", "right"}:
            await self._confirm_event(message, pending, "Yes")
            return True

        if user_lower in {"no", "n", "nope", "wrong", "incorrect"}:
            self.awaiting_correction.add(chat_id)
            await message.answer(
                "📝 What should I have understood?\n"
                "(e.g., 'It was practice, not theory' or 'The activity is pandas-dataframes')"
            )
            return True

        if chat_id in self.awaiting_correction:
            await self._confirm_event(message, pending, user_input)
            self.awaiting_correction.discard(chat_id)
            return True

        return False

    async def _confirm_event(
        self, message: Message, parsed_event: Dict[str, Any], user_response: str
    ) -> None:
        chat_id = message.chat.id
        should_clear_pending = True
        try:
            result = await self._request_confirm_result(
                chat_id, parsed_event, user_response
            )

            async def sender(text: str, markup: InlineKeyboardMarkup | None) -> None:
                await message.answer(text, reply_markup=markup)

            should_clear_pending = await self._handle_confirm_result(
                result=result,
                chat_id=chat_id,
                parsed_event=parsed_event,
                send_message=sender,
                include_session_info=True,
            )
        except HTTPError as e:
            await message.answer(f"❌ Failed to log event. Error: {e.error_text}")
        except aiohttp.ClientError as e:
            logger.error("Error confirming event: %s", e)
            await message.answer("❌ Failed to log event. Please try again.")
        finally:
            if should_clear_pending:
                self._clear_pending(chat_id)

    async def _handle_query(self, message: Message, query_text: str) -> None:
        try:
            result = await self._post_json("/query", {"query": query_text})
            await message.answer(result.get("message", "No response"))
        except HTTPError:
            await message.answer("❌ Sorry, I couldn't process that query.")
        except aiohttp.ClientError as e:
            logger.error("Error querying: %s", e)
            await message.answer(
                "⏱️ Query timed out. Try again, or check that the agent service is running."
            )

    async def button_callback(self, callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message is None:
            return

        chat_id = callback.message.chat.id
        pending = self.pending_suggestion.get(chat_id)
        if not pending:
            await callback.message.edit_text("❌ Session expired. Please try again.")
            return

        if callback.data == "confirm_yes":
            await self._confirm_event_from_callback(callback, pending, "Yes")
            return

        if callback.data == "confirm_no":
            self.awaiting_correction.add(chat_id)
            await callback.message.edit_text(
                "📝 What should I have understood?\n"
                "(Reply with the correct description)"
            )

    async def _confirm_event_from_callback(
        self, callback: CallbackQuery, parsed_event: Dict[str, Any], user_response: str
    ) -> None:
        if callback.message is None:
            return

        chat_id = callback.message.chat.id
        should_clear_pending = True
        try:
            result = await self._request_confirm_result(
                chat_id, parsed_event, user_response
            )

            async def sender(text: str, markup: InlineKeyboardMarkup | None) -> None:
                await callback.message.edit_text(text, reply_markup=markup)

            should_clear_pending = await self._handle_confirm_result(
                result=result,
                chat_id=chat_id,
                parsed_event=parsed_event,
                send_message=sender,
                include_session_info=False,
            )
        except HTTPError as e:
            await callback.message.edit_text(f"❌ Error: {e.error_text}")
        except aiohttp.ClientError as e:
            logger.error("Error in callback confirm: %s", e)
            await callback.message.edit_text("❌ Failed to log event.")
        finally:
            if should_clear_pending:
                self._clear_pending(chat_id)

    async def _run(self) -> None:
        self.http = aiohttp.ClientSession()

        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.help_command, Command("help"))
        self.dp.message.register(self.ratio_command, Command("ratio"))
        self.dp.message.register(self.today_command, Command("today"))
        self.dp.callback_query.register(
            self.button_callback, F.data.in_({"confirm_yes", "confirm_no"})
        )
        self.dp.message.register(self.handle_message, F.text)

        logger.info("Starting aiogram bot...")
        try:
            await self.dp.start_polling(self.bot)
        finally:
            for task in self.game_tasks.values():
                if not task.done():
                    task.cancel()
            self.game_tasks.clear()
            if self.http is not None:
                await self.http.close()
            await self.bot.session.close()

    def run(self) -> None:
        asyncio.run(self._run())


if __name__ == "__main__":
    AgentBot().run()
