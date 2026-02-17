"""
FastAPI service - HTTP API for the agent system
Provides endpoints for event parsing and queries
Never writes directly to master.log - only through Rust API
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import requests
import json
import re

from parser import EventParser
from query_engine import QueryEngine

app = FastAPI(title="Event Agent API", version="0.1.0")

# Initialize components
parser = EventParser()
query_engine = QueryEngine()

# Rust API endpoint (where master.log lives)
RUST_API_URL = "http://localhost:8080"

class EventInput(BaseModel):
    input: str
    use_llm: bool = False
    user_id: Optional[str] = "default"

class QueryInput(BaseModel):
    query: str
    timeframe: Optional[str] = "week"

class ConfirmationInput(BaseModel):
    parsed_event: Dict[str, Any]
    user_response: str  # "Yes" or "No, ..."
    original_input: str

@app.post("/parse")
async def parse_event(input_data: EventInput):
    """
    Parse natural language into structured event
    Returns suggestion - user must confirm before writing to log
    """
    try:
        # Parse the input
        result = parser.parse(input_data.input, use_llm=input_data.use_llm)
        
        # Store LLM decision for training
        decision = {
            'timestamp': datetime.now().isoformat(),
            'user_input': input_data.input,
            'llm_suggestion': result['formatted_event'],
            'user_response': 'pending',  # Will be updated on confirmation
            'confidence': result.get('confidence', 0.7),
            'model': 'qwen-2.5-3b' if input_data.use_llm else 'rule_based'
        }
        query_engine.store_llm_decision(decision)
        
        return {
            'status': 'parsed',
            'suggestion': result['formatted_event'],
            'details': result,
            'message': f"I understood: {result['formatted_event']}. Is this correct?"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/confirm")
async def confirm_event(confirmation: ConfirmationInput):
    """
    Handle user confirmation
    If 'Yes' -> forward to Rust API to append to master.log
    If 'No, ...' -> re-parse with correction
    """
    try:
        user_response = confirmation.user_response.lower().strip()
        
        if user_response.startswith('yes') or user_response == 'y':
            # User confirmed - forward to Rust API
            event_to_log = confirmation.parsed_event['formatted_event']
            
            # Call Rust API to append to master.log
            rust_response = requests.post(
                f"{RUST_API_URL}/events",
                json={'event': event_to_log},
                timeout=5
            )
            
            if rust_response.status_code == 200:
                # Update LLM decision as accepted
                # Store context in SQLite
                context_data = {
                    **confirmation.parsed_event,
                    'user_confirmed': True,
                    'timestamp': datetime.now().isoformat()
                }
                query_engine.store_context(context_data)
                
                # Get session info from Rust API
                session_info = rust_response.json()
                
                return {
                    'status': 'logged',
                    'event': event_to_log,
                    'session_info': session_info,
                    'message': f"✅ Logged: {event_to_log}"
                }
            else:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to write to master.log: {rust_response.text}"
                )
        
        else:
            # User rejected or provided correction
            # Store the correction for training
            correction = {
                'timestamp': datetime.now().isoformat(),
                'user_input': confirmation.original_input,
                'llm_suggestion': confirmation.parsed_event['formatted_event'],
                'user_response': confirmation.user_response,
                'confidence': 0.0,  # Mark as incorrect
                'model': 'user_correction'
            }
            query_engine.store_llm_decision(correction)
            
            # Try to parse the correction
            # Remove common prefixes like "No, it was", "Actually", etc.
            cleaned_input = re.sub(
                r'^(no|nope|actually|wrong|incorrect)[,\s]*', 
                '', 
                confirmation.user_response, 
                flags=re.IGNORECASE
            ).strip()
            
            # Re-parse
            new_result = parser.parse(cleaned_input)
            
            return {
                'status': 'corrected',
                'suggestion': new_result['formatted_event'],
                'details': new_result,
                'message': f"🔄 I understood: {new_result['formatted_event']}. Is this correct?"
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def process_query(query_input: QueryInput):
    """
    Handle complex queries
    Returns analytics and insights derived from event log
    """
    try:
        result = query_engine.answer_query(query_input.query)
        
        # For natural language response, we could use LLM
        # For now, return structured data
        return {
            'status': 'success',
            'query': query_input.query,
            'result': result,
            'message': format_query_response(result)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '0.1.0'
    }

def format_query_response(result: Dict[str, Any]) -> str:
    """Format query result as human-readable text"""
    if result['type'] == 'ratio':
        data = result['answer']
        return (
            f"Theory to Practice Ratio ({data['timeframe']}):\n"
            f"Total sessions: {data['total_sessions']}\n"
            f"Breakdown: {data['breakdown']}\n"
            f"Ratio: {data['theory_to_practice']:.2f}"
        )
    elif result['type'] == 'timeline':
        sessions = result['answer']['recent_sessions']
        if not sessions:
            return "No recent sessions found."
        return (
            f"Recent sessions ({len(sessions)} total):\n" +
            "\n".join([f"- {s['category']} {s['activity']}" for s in sessions])
        )
    elif result['type'] == 'summary':
        activities = result['answer']['activities']
        return (
            f"You've worked on {result['answer']['total_activities']} different activities:\n"
            + "\n".join([f"- {act}" for act in activities])
        )
    else:
        return result['answer']

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
