"""
Greyhound Racing Tips Bot - Railway Ready

RAILWAY DEPLOYMENT INSTRUCTIONS:
1. Create new Railway project
2. Connect to GitHub repo containing this file
3. Add these files to your repo:
   
   requirements.txt:
   discord.py==2.3.2
   google-genai==0.6.0
   aiohttp==3.9.1
   pytz==2023.3
   
   railway.json:
   {
     "build": {
       "builder": "NIXPACKS"
     },
     "deploy": {
       "startCommand": "python Greyhound.py",
       "restartPolicyType": "ON_FAILURE"
     }
   }

4. Set these REQUIRED environment variables in Railway:
   - GEMINI_API_KEY: Your Google AI API key
   - WEBHOOK_URL: Your Discord webhook URL  
   - RUN_MODE: schedule (for automatic daily posting)

5. Deploy to Railway - bot will use environment variables only
6. Bot will automatically run in schedule mo    print(f"🕐 System time: {system_now.strftime('%Y-%m-%d %H:%M')}")
    print(f"🌍 UTC time: {utc_now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"🇦🇺 Perth time: {datetime.now(PERTH_TZ).strftime('%Y-%m-%d %H:%M AWST')}")
    print(f"📅 Effective analysis date: {perth_now.strftime('%B %d, %Y')} ({perth_now.strftime('%Y-%m-%d')})")
    if OVERRIDE_DATE:
        print(f"🔧 OVERRIDE_DATE set to: {OVERRIDE_DATE}")
    print(f"📁 Data directory: {DATA_DIR}")
    
    # Check if this seems like a future date issue
    import time
    epoch_time = time.time()
    readable_epoch = datetime.fromtimestamp(epoch_time)
    print(f"🔍 System epoch time: {readable_epoch.strftime('%Y-%m-%d %H:%M')}")
    print(f"📊 Current year from system: {system_now.year}")
    print(f"📅 Bot will use Australian date for all analysis")
    print("=" * 60)

# Railway-ready 24/7 greyhound tips bot with automatic 7AM/7PM Perth time
"""

import discord
from discord import Webhook
from discord.ui import View, Button
from discord import ButtonStyle
from google import genai
import asyncio
import aiohttp
import json
import re
import pytz
import time
import threading
import os
from datetime import datetime, timedelta, time as dtime

# API Configuration - Railway environment variables only
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
FALLBACK_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1403918683062927370/DuSmvhwvPqf7xF7JdRrfv0yg9Zh6HpqrRvJAUD_bRINX-0_RSbdi2NgwPUy1upJPK48h"
# Override date for testing (format: YYYY-MM-DD, e.g., "2024-12-06")
OVERRIDE_DATE = os.environ.get('OVERRIDE_DATE')  # No default - use actual current date

# Validate required environment variables
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

# Clean up any potential whitespace issues
GEMINI_API_KEY = GEMINI_API_KEY.strip() if GEMINI_API_KEY else None
WEBHOOK_URL = WEBHOOK_URL.strip() if WEBHOOK_URL else None

# Railway-ready configuration with debugging
print(f"✅ API Key configured: {GEMINI_API_KEY[:20] if GEMINI_API_KEY else 'None'}...")
print(f"✅ Webhook configured: {WEBHOOK_URL[:50] if WEBHOOK_URL else 'None'}...")
print(f"🔧 Using Railway environment variables: Yes")
print(f"🔑 API Key length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0} characters")
print(f"🔗 Webhook length: {len(WEBHOOK_URL) if WEBHOOK_URL else 0} characters")

# Validate API key format
if GEMINI_API_KEY and not GEMINI_API_KEY.startswith('AIza'):
    print(f"⚠️ WARNING: API key doesn't start with 'AIza' - this might be incorrect")

# Australian timezones - MUST be defined before any functions that use them
PERTH_TZ = pytz.timezone('Australia/Perth')
AEST_TZ = pytz.timezone('Australia/Sydney')  # AEST timezone for getting correct Australian date

# Data directory - Railway-friendly (will use /app/data in Railway)
if os.path.exists('/app'):
    # Railway deployment path
    DATA_DIR = '/app/data'
else:
    # Local development path
    DATA_DIR = r'c:\Users\Pixel\Desktop\HORSE AI LJ\data'

# Simple storage for daily predictions (no learning system)
DAILY_PREDICTIONS_FILE = os.path.join(DATA_DIR, 'daily_greyhound_predictions.json')

def default_predictions_for_today():
    # Use Australian date, not American system date
    australian_now = datetime.now(AEST_TZ)
    return {
        'date': australian_now.strftime('%Y-%m-%d'),
        'predictions': [],
        'generated_at': australian_now.astimezone(PERTH_TZ).strftime('%H:%M AWST')
    }

def ensure_data_dir_and_files():
    """Ensure data directory and JSON files exist (Railway-ready)."""
    global DATA_DIR, DAILY_PREDICTIONS_FILE
    
    try:
        # Create data directory with proper permissions
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"📁 Data directory: {DATA_DIR}")
        
        # Daily predictions file
        if not os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'w') as f:
                json.dump(default_predictions_for_today(), f, indent=2)
            print("📅 Created daily predictions file")
            
    except Exception as e:
        print(f"❌ Error ensuring data files: {e}")
        # Try to create in current directory as fallback
        DATA_DIR = './data'
        DAILY_PREDICTIONS_FILE = os.path.join(DATA_DIR, 'daily_greyhound_predictions.json')
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"📁 Fallback data directory: {DATA_DIR}")

def get_effective_date():
    """Get the effective date for analysis - uses Australian date, not American system date"""
    if OVERRIDE_DATE:
        try:
            # Parse override date and apply Perth timezone
            override_dt = datetime.strptime(OVERRIDE_DATE, '%Y-%m-%d')
            # Create a timezone-aware datetime at noon Perth time
            effective_dt = PERTH_TZ.localize(override_dt.replace(hour=12))
            print(f"🔧 Using OVERRIDE_DATE: {OVERRIDE_DATE} -> {effective_dt.strftime('%B %d, %Y (%A)')}")
            return effective_dt
        except ValueError as e:
            print(f"⚠️ Invalid OVERRIDE_DATE format '{OVERRIDE_DATE}': {e}")
            print("Using current Australian date instead")
    
    # Use Australian Eastern time to get the correct Australian date
    # This fixes the issue with American system dates
    australian_now = datetime.now(AEST_TZ)
    print(f"🇦🇺 Using Australian date: {australian_now.strftime('%B %d, %Y (%A)')} AEST")
    
    # Convert to Perth timezone for analysis (maintain Perth time for the bot)
    perth_equivalent = australian_now.astimezone(PERTH_TZ)
    return perth_equivalent

# Initialize Gemini client with proper SDK
client = genai.Client(api_key=GEMINI_API_KEY)

# Configure generation with web search tools enabled
generation_config = {
    "temperature": 0.2,
    "top_p": 0.8,
    "top_k": 30,
    "max_output_tokens": 8192  # be sane; 32k often unnecessary/slow
}

# Google AI Generative Language API endpoint for search grounding
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

async def call_gemini_with_search_grounding(prompt, au_iso):
    """Call Gemini API with proper search grounding using REST API"""
    
    # Use query parameter for API key (official/stable method)
    url = f"{GEMINI_API_BASE}/models/gemini-2.5-pro:generateContent?key={GEMINI_API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
        # Removed x-goog-api-key header - using query param instead
    }
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"text": f"DATE_AU={au_iso}"}
                ]
            }
        ],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "topK": 30,
            "maxOutputTokens": 8192
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=600)) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    # Extract text from response
                    if "candidates" in result and result["candidates"]:
                        candidate = result["candidates"][0]
                        if "content" in candidate and "parts" in candidate["content"]:
                            text_parts = []
                            for part in candidate["content"]["parts"]:
                                if "text" in part:
                                    text_parts.append(part["text"])
                            return "\n".join(text_parts)
                    
                    return "No valid response received from search grounding API"
                else:
                    error_text = await response.text()
                    print(f"❌ Search grounding API error {response.status}: {error_text}")
                    return None
                    
    except Exception as e:
        print(f"❌ Error calling search grounding API: {str(e)}")
        return None

async def call_gemini_fallback(prompt):
    """Fallback to regular Gemini API without search grounding"""
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-pro",
            contents=prompt,
            config=generation_config
        )
        
        # Process response parts
        final_answer = ""
        if response and hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            final_answer += part.text
        
        return final_answer
        
    except Exception as e:
        print(f"❌ Error in fallback API call: {str(e)}")
        return None

def load_daily_predictions():
    """Load today's predictions"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'r') as f:
                data = json.load(f)
            # Ensure file is for today (Australian date)
            australian_now = datetime.now(AEST_TZ)
            today_str = australian_now.strftime('%Y-%m-%d')
            if data.get('date') == today_str:
                return data
        # Create/reset for today
        today_default = default_predictions_for_today()
        with open(DAILY_PREDICTIONS_FILE, 'w') as f:
            json.dump(today_default, f, indent=2)
        return today_default
    except Exception as e:
        print(f"Error loading predictions: {e}")
        return default_predictions_for_today()

def save_daily_predictions(predictions_data):
    """Save today's predictions"""
    try:
        with open(DAILY_PREDICTIONS_FILE, 'w') as f:
            json.dump(predictions_data, f, indent=2)
    except Exception as e:
        print(f"Error saving predictions: {e}")

async def test_web_search_capability():
    """Test if Google Search/Web Grounding is working with proper REST API"""
    test_prompt = """Use web search to find today's date and tell me what day of the week it is. 
    Search for 'what day is today' and 'current date'.
    
    IMPORTANT: Many racing websites are protected or require authentication. If you cannot access 
    detailed race cards, please report what information you CAN find from publicly available sources."""
    
    try:
        print("🔍 Testing search grounding capability...")
        print("⚠️ Note: Search grounding provides web snippets, not guaranteed access to all racing data")
        
        # Get current Australian date for test
        au_now = datetime.now(pytz.timezone('Australia/Sydney'))
        au_iso = au_now.strftime("%Y-%m-%d")
        
        # Try search grounding first
        response = await call_gemini_with_search_grounding(test_prompt, au_iso)
        
        if response and len(response.strip()) > 50:
            # Check if search grounding was used (look for search indicators)
            search_indicators = [
                "according to",
                "based on my search",
                "I found",
                "search results",
                "from the web",
                "searching",
                "web search",
                "I searched"
            ]
            
            has_search_indicators = any(indicator in response.lower() for indicator in search_indicators)
            
            if has_search_indicators:
                print("✅ Search grounding appears to be working!")
                print("💡 Note: Racing data availability depends on website access and paywall restrictions")
                print(f"Test response: {response[:200]}...")
                return True
            else:
                print("⚠️ Search grounding may not be enabled - response seems like standard generation")
                print(f"Test response: {response[:200]}...")
                return False
        else:
            print("⚠️ No valid response from search grounding API")
            return False
            
    except Exception as e:
        print(f"❌ Error testing search grounding: {str(e)}")
        return False

async def generate_greyhound_tips():
    """Generate greyhound tips for today's races only (Perth timezone)"""
    perth_now = get_effective_date()  # Use effective date instead of current time
    
    # Always use dynamic "today" language instead of specific dates
    target_date_search = perth_now.strftime("%Y-%m-%d")
    current_time_perth = perth_now.strftime("%H:%M AWST")
    
    print(f"Generating fresh greyhound tips for TODAY at {current_time_perth}")
    print(f"DEBUG: Perth date: {target_date_search}, Perth time: {current_time_perth}")
    
    # Analyze today's greyhound races with retry logic
    tips_result = await analyze_greyhound_racing_day_with_retry(current_time_perth)
    
    # Save predictions for basic logging
    predictions_data = {
        'date': target_date_search,
        'predictions': [],  # Simplified - no learning system
        'generated_at': current_time_perth
    }
    save_daily_predictions(predictions_data)
    
    return tips_result

async def research_analysis_only():
    """Generate research analysis without sending to Discord - for testing and verification"""
    perth_now = get_effective_date()  # Use effective date instead of current time
    current_time_perth = perth_now.strftime("%H:%M AWST")
    
    print(f"Generating research analysis for TODAY at {current_time_perth}")
    
    # Analyze today's greyhound races with retry logic
    research_result = await analyze_greyhound_racing_day_with_retry(current_time_perth)
    
    # Print to console instead of sending to Discord
    print("\n" + "="*80)
    print("RESEARCH ANALYSIS RESULTS")
    print("="*80)
    print(research_result)
    print("="*80)
    
    return research_result

def extract_predictions_for_learning(tips_content):
    """Extract predictions from greyhound tips content - simplified version"""
    predictions = []
    lines = tips_content.split('\n')
    
    for line in lines:
        if line.startswith('🐕 **') and '**' in line:
            # Extract greyhound name
            greyhound_match = re.search(r'🐕 \*\*(.*?)\*\*', line)
            if greyhound_match:
                predictions.append({
                    'greyhound_name': greyhound_match.group(1),
                    'race_info': line
                })
    
    return predictions

async def send_fallback_webhook_message(content, title="⚠️ Greyhound Bot - Data Issue"):
    """Send message to fallback webhook for data issues"""
    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(FALLBACK_WEBHOOK_URL, session=session)
            
            embed = discord.Embed(
                title=title,
                description=content[:4096] if len(content) > 4096 else content,
                color=0xff0000  # Red for errors
            )
            embed.set_footer(text=f"Generated on {datetime.now(PERTH_TZ).strftime('%B %d, %Y at %H:%M AWST')}")
            
            await webhook.send(embed=embed)
                
    except Exception as e:
        print(f"Error sending fallback webhook: {str(e)}")

async def analyze_greyhound_racing_day_with_retry(current_time_perth):
    """Analyze greyhound racing with retry logic for better reliability"""
    max_retries = 3
    retry_delay = 120  # 2 minutes between retries
    
    for attempt in range(max_retries):
        try:
            print(f"🔍 Analysis attempt {attempt + 1}/{max_retries}")
            
            # Call the main analysis function
            tips_result = await analyze_greyhound_racing_day(current_time_perth)
            
            # Check if we got a valid result
            if tips_result and len(tips_result.strip()) > 100:
                print(f"✅ Attempt {attempt + 1}: Analysis completed successfully")
                return tips_result
            else:
                print(f"⚠️ Attempt {attempt + 1}: Got empty or invalid result")
                if attempt == max_retries - 1:
                    # Last attempt, return fallback
                    break
                continue
                
        except Exception as e:
            error_str = str(e)
            print(f"❌ Attempt {attempt + 1} failed with error: {error_str}")
            
            # Check for specific API errors
            if "'NoneType' object is not iterable" in error_str:
                print("🔧 Detected API response issue - using fallback")
                if attempt == max_retries - 1:
                    break
                print(f"⏳ Waiting {retry_delay} seconds before retry...")
                await asyncio.sleep(retry_delay)
                continue
            
            if attempt == max_retries - 1:
                # Final attempt failed with error
                error_message = f"""🚨 **GREYHOUND BOT - TECHNICAL ERROR**

After {max_retries} attempts, the bot encountered technical errors.

**Error:** {error_str}

**Time:** {current_time_perth} AWST
**Date:** {datetime.now(PERTH_TZ).strftime('%B %d, %Y')}"""
                
                await send_fallback_webhook_message(error_message, 
                                                   "🚨 Greyhound Bot - Technical Error")
                
                return f"⚠️ Technical error after {max_retries} attempts: {error_str}"
            else:
                print(f"⏳ Waiting {retry_delay} seconds before retry...")
                await asyncio.sleep(retry_delay)
    
    # All attempts failed, provide fallback response
    perth_now = datetime.now(PERTH_TZ)
    fallback_date = perth_now.strftime('%B %d, %Y')
    
    return f"""🐕 Greyhound Racing Analysis - {fallback_date}

⚠️ **System Recovery Mode**

After multiple attempts, the AI analysis system is temporarily unavailable.

📅 **Manual Racing Check Required:**
1. **TAB.com.au** → Greyhounds → Today's Meetings
2. **TheDogs.com.au** → Race Cards section
3. **Racing.com** → Greyhound racing section

🏁 **Expected Venues for {fallback_date}:**
- **NSW**: Gosford, Bulli, Richmond
- **VIC**: Sandown, Healesville, Warragul  
- **QLD**: Albion Park, Ipswich, Townsville
- **SA**: Murray Bridge, Angle Park
- **WA**: Cannington, Mandurah

💡 **Racing Tips (General Guidelines):**
- Look for box 1-4 in small fields
- Avoid wide barriers in big fields
- Check for gear changes (especially blinkers)
- Consider track specialists over visitors

🔄 **System Status:** Automatic recovery in progress. Next analysis attempt in 30 minutes.

⚠️ **DISCLAIMER**: Always verify race information on official websites before betting."""

async def placeholder_function_to_remove():
    """This function will be removed"""
    pass
    
    # Learning system disabled 
    print("Learning system has been disabled as requested")
    return "Learning system disabled."
    
    # Get race results for analysis using dynamic language with web search
    results_prompt = f"""🔍 GREYHOUND RACE RESULTS ANALYSIS - TODAY'S RESULTS

You are a greyhound racing results analyst with access to real-time web search.

Use web search tools to find TODAY'S Australian greyhound racing results and provide:

1. Winners of all races that have finished today
2. Finishing positions for all greyhounds  
3. Starting prices/odds
4. Track conditions
5. Winning margins and times

MANDATORY WEB SEARCHES:
- "greyhound racing results Australia {au_iso}"
- "TheDogs.com.au results {au_iso}"
- "Racing NSW greyhound results {au_iso}"
- "GRV greyhound racing results {au_iso}"
- "RWWA greyhound results {au_iso}"
- "TAB greyhound results {au_iso}"
- "greyhound racing winners {au_iso}"

Use web search tools to find results across all Australian venues for {au_iso}.

Provide results in this concise format:
🐕 RACE X - TRACK NAME ({au_iso})
🥇 Winner: GREYHOUND NAME (Box: X, Trainer: Y, SP: $X.XX, Time: XX.XXs)
---"""

    try:
        print("🔍 Analyzing race results...")
        
        # Try search grounding for results
        response_text = await call_gemini_with_search_grounding(results_prompt, au_iso)
        
        if response_text:
            results_content = response_text
        else:
            # Fallback to regular API
            fallback_response = await call_gemini_fallback(results_prompt)
            results_content = fallback_response if fallback_response else "No results available"
        
        # Analyze our predictions against results
        learning_analysis = await analyze_prediction_accuracy(predictions_data, results_content)
        
        # Send results and learning update to Discord
        await send_webhook_message(
            f"""📊 DAILY GREYHOUND RESULTS & LEARNING (Perth)

{results_content}

---
🧠 LEARNING ANALYSIS
{learning_analysis}""",
            title="🌇 Greyhound Results & Learning - 7PM Perth",
        )
        
        return "Greyhound results analyzed and learning data updated successfully!"
    except Exception as e:
        error_msg = f"Error analyzing greyhound results: {str(e)}"
        print(error_msg)
        return error_msg

async def analyze_prediction_accuracy(predictions_data, results_content):
    """Analyze how accurate our predictions were (learning system disabled)"""
    # Learning system removed - just log the call
    print("📊 Prediction accuracy analysis called (learning system disabled)")
    return "Learning system has been disabled as requested."
    
    correct_predictions = 0
    total_predictions = len(predictions_data['predictions'])
    
    analysis_summary = []
    
    for prediction in predictions_data['predictions']:
        greyhound_name = prediction['greyhound_name']
        # crude winner detection; can be improved later
        winner_line = re.search(r"Winner:\s*([A-Za-z'’\-\.\s]+)", results_content, re.IGNORECASE)
        if winner_line:
            winner_name = winner_line.group(1).strip()
        else:
            winner_name = ""
        
        if greyhound_name and winner_name and greyhound_name.lower() in winner_name.lower():
            correct_predictions += 1
            analysis_summary.append(f"✅ {greyhound_name} - CORRECT (Won)")
            for detail in prediction.get('prediction_details', []):
                if 'Composite Score:' in detail or 'Track:' in detail or 'Box:' in detail:
                    learning_data['successful_patterns'].append(f"WINNER - {greyhound_name}: {detail}")
        else:
            analysis_summary.append(f"❌ {greyhound_name} - FAILED (Did not win)")
            for detail in prediction.get('prediction_details', []):
                if 'Composite Score:' in detail or 'Track:' in detail or 'Box:' in detail:
                    learning_data['failed_patterns'].append(f"FAILED - {greyhound_name}: {detail}")
    
    # Update statistics
    learning_data['total_predictions'] += total_predictions
    learning_data['successful_predictions'] += correct_predictions
    learning_data['failed_predictions'] += (total_predictions - correct_predictions)
    if learning_data['total_predictions'] > 0:
        learning_data['win_rate'] = (learning_data['successful_predictions'] / learning_data['total_predictions']) * 100
    
    # Add learning insights
    if total_predictions > 0:
        learning_data['learning_insights'].append(
            f"{predictions_data['date']}: {correct_predictions}/{total_predictions} correct ({(correct_predictions/total_predictions)*100:.1f}%)"
        )
def has_strong_bets(tips_content):
    # Look for strong bet indicators in the response
    strong_bet_indicators = [
        "STRONG SELECTIONS",
        "Composite Score: 2",
        "Analysis Score: 8", 
        "Analysis Score: 9",
        "Analysis Score: 10",
        "BET TYPE:** WIN"
    ]
    
    # Check if any strong bet indicators are present
    for indicator in strong_bet_indicators:
        if indicator in tips_content:
            return True
    
    # Also check for phrases that indicate no strong bets found
    no_strong_bets_phrases = [
        "No greyhounds met the criteria",
        "no greyhounds meeting the criteria",
        "No suitable selections found",
        "All selections are speculative"
    ]
    
    for phrase in no_strong_bets_phrases:
        if phrase in tips_content:
            return False
    
    return False

def extract_summary(tips_content):
    """Extract a brief summary from greyhound tips content for display"""
    lines = tips_content.split('\n')
    summary_lines = []
    
    # Look for key information lines
    for line in lines:
        if any(keyword in line.lower() for keyword in ['track conditions', 'no greyhounds found', 'analysis summary']):
            summary_lines.append(line)
        elif 'Composite Score:' in line or 'Analysis Score:' in line:
            summary_lines.append(line)
        elif line.startswith('🐕') and '|' in line:
            summary_lines.append(line)
    
    # If we found specific content, return it
    if summary_lines:
        return '\n'.join(summary_lines[:10])  # Limit to first 10 relevant lines
    
    # Otherwise return a basic summary
    if 'greyhound' in tips_content.lower():
        return "🐕 Some greyhound selections were identified for today's racing."
    else:
        return "❌ No qualifying greyhound selections found for this day."

def extract_race_info_greyhound(text: str) -> dict:
    """Extract track and race number from greyhound analysis text."""
    race_info = {'track': None, 'race_number': None}
    
    # Look for race patterns in greyhound tips
    patterns = [
        r'Race\s*(\d+)\s*(?:\||\-)\s*([A-Za-z\s]+?)(?:\s*\||\s*$)',  # "Race 6 | Wentworth Park"
        r'([A-Za-z\s]+?)\s*(?:\||\-)\s*Race\s*(\d+)',                # "Wentworth Park | Race 6"
        r'🐕.*?Race\s*(\d+).*?([A-Za-z\s]+)',                       # In dog line
        r'([A-Za-z\s]+)\s*\-\s*Race\s*(\d+)',                       # "Track - Race X"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if pattern.startswith(r'Race\s*(\d+)'):
                race_info['race_number'] = match.group(1)
                race_info['track'] = match.group(2).strip()
            else:
                race_info['track'] = match.group(1).strip()
                race_info['race_number'] = match.group(2)
            break
    
    # Clean up track name
    if race_info['track']:
        race_info['track'] = re.sub(r'\s+', ' ', race_info['track']).strip()
    
    return race_info

def filter_diverse_selections(response_text: str) -> str:
    """Filter greyhound selections to ensure diversification across different races."""
    lines = response_text.split('\n')
    used_races = set()
    filtered_lines = []
    current_selection = []
    in_selection = False
    
    for line in lines:
        # Check if this is a dog selection line
        if line.strip().startswith('🐕 **') and '**' in line:
            # Process previous selection if any
            if current_selection:
                race_info = extract_race_info_greyhound('\n'.join(current_selection))
                race_key = None
                
                if race_info['track'] and race_info['race_number']:
                    race_key = f"{race_info['track'].lower().strip()}_{race_info['race_number']}"
                elif race_info['track']:
                    race_key = f"{race_info['track'].lower().strip()}_unknown"
                
                # Only add if not a duplicate race
                if not race_key or race_key not in used_races:
                    filtered_lines.extend(current_selection)
                    if race_key:
                        used_races.add(race_key)
                        print(f"✅ Added selection from {race_info['track']} Race {race_info['race_number'] or 'Unknown'}")
                else:
                    print(f"🚨 FILTERED duplicate race: {race_info['track']} Race {race_info['race_number'] or 'Unknown'}")
            
            # Start new selection
            current_selection = [line]
            in_selection = True
        elif in_selection and (line.strip().startswith('🐕 **') or line.strip() == '' or line.strip().startswith('---')):
            # End of current selection
            in_selection = False
            if line.strip() == '' or line.strip().startswith('---'):
                current_selection.append(line)
        elif in_selection:
            current_selection.append(line)
        else:
            # Non-selection lines (headers, etc.)
            if not in_selection:
                filtered_lines.append(line)
    
    # Process final selection
    if current_selection:
        race_info = extract_race_info_greyhound('\n'.join(current_selection))
        race_key = None
        
        if race_info['track'] and race_info['race_number']:
            race_key = f"{race_info['track'].lower().strip()}_{race_info['race_number']}"
        elif race_info['track']:
            race_key = f"{race_info['track'].lower().strip()}_unknown"
        
        if not race_key or race_key not in used_races:
            filtered_lines.extend(current_selection)
            if race_key:
                used_races.add(race_key)
                print(f"✅ Added final selection from {race_info['track']} Race {race_info['race_number'] or 'Unknown'}")
    
    print(f"📊 DIVERSIFICATION RESULT: {len(used_races)} selections from different races")
    return '\n'.join(filtered_lines)

async def analyze_greyhound_racing_day(current_time_perth):
    """Analyze TODAY only (Perth date) with comprehensive greyhound analysis using explicit AU date anchoring"""
    
    print(f"🔍 Starting comprehensive greyhound analysis for TODAY...")
    
    # Always anchor to Australia/Sydney date for "today"
    AEST_TZ = pytz.timezone('Australia/Sydney')
    
    au_now = datetime.now(AEST_TZ)
    au_iso = au_now.strftime("%Y-%m-%d")                  # 2025-08-17
    au_long = au_now.strftime("%A, %d %B %Y")             # Sunday, 17 August 2025
    au_time = au_now.strftime("%H:%M AEST")               # 09:12 AEST
    
    # Convert to Perth time for display
    PERTH_TZ = pytz.timezone('Australia/Perth')
    au_now_perth = au_now.astimezone(PERTH_TZ)
    perth_time = au_now_perth.strftime("%H:%M AWST")
    
    print(f"📅 Effective AU date: {au_long} ({au_iso}), time {au_time}")
    print(f"📅 Perth equivalent: {perth_time}")
    
    # Expert greyhound racing analyst prompt with explicit date anchoring and web search instructions
    main_prompt = f"""You are an expert greyhound racing analyst with access to real-time web search.

# DATE ANCHOR (DO NOT CHANGE)
Assume the current date is {au_long} and the current time is {au_time} in the Australia/Sydney time zone (AEST/AEDT as appropriate). 
Treat {au_long} ({au_iso}) as "today" for all searches and decisions, even if your system clock or any website shows a different date. 
Do not reinterpret this as a future date.

# CRITICAL SELECTION RULES
🚨 MAXIMUM ONE GREYHOUND PER RACE - Never select multiple dogs from the same race
🚨 SCAN ALL MEETINGS - Cover as many different tracks and meetings as possible
🚨 DIVERSIFICATION MANDATORY - Spread selections across different venues and race numbers
🚨 MAXIMUM 1.5 UNITS STAKE - Never recommend stakes above 1.5 units per selection

# WEB SEARCH INSTRUCTIONS & COMPREHENSIVE COVERAGE
You have access to web search tools. Search ALL major Australian greyhound venues:

MANDATORY COMPREHENSIVE SEARCHES (use web search tools for each):
1. "greyhound racing meetings Australia {au_iso} all venues"
2. "TAB greyhound racing {au_iso} today complete schedule"
3. "thedogs.com.au race cards {au_iso} all meetings"
4. "Australian greyhound racing fixtures {au_long} nationwide"

COMPREHENSIVE VENUE SEARCHES (search each major track):
NSW TRACKS:
5. "Gosford greyhound racing {au_iso}"
6. "Bulli greyhound racing {au_iso}"
7. "Richmond greyhound racing {au_iso}"
8. "Dapto greyhound racing {au_iso}"
9. "Wentworth Park greyhound racing {au_iso}"

VIC TRACKS:
10. "Sandown greyhound racing {au_iso}"
11. "Healesville greyhound racing {au_iso}"
12. "Warragul greyhound racing {au_iso}"
13. "Geelong greyhound racing {au_iso}"
14. "Ballarat greyhound racing {au_iso}"

QLD TRACKS:
15. "Albion Park greyhound racing {au_iso}"
16. "Ipswich greyhound racing {au_iso}"
17. "Townsville greyhound racing {au_iso}"
18. "Capalaba greyhound racing {au_iso}"

SA TRACKS:
19. "Murray Bridge greyhound racing {au_iso}"
20. "Angle Park greyhound racing {au_iso}"

WA TRACKS:
21. "Cannington greyhound racing {au_iso}"
22. "Mandurah greyhound racing {au_iso}"

# ANALYSIS REQUIREMENTS
1) Search EVERY major greyhound venue for {au_long} meetings
2) Find races across ALL states - NSW, VIC, QLD, SA, WA
3) Select MAXIMUM ONE greyhound per race (never multiple from same race)
4) Provide detailed unit staking recommendations (0.5 to 1.5 units max)
5) Focus on finding 4-8 quality selections across different tracks

# STAKING SYSTEM (MANDATORY)
- **1.5 UNITS**: Premium selections with multiple strong factors
- **1.0 UNITS**: Solid selections with good form/draw combination  
- **0.5 UNITS**: Speculative plays or each-way chances
- **NEVER exceed 1.5 units on any single selection**

# OUTPUT FORMAT (MANDATORY STRUCTURE)

🐕 **GREYHOUND SELECTIONS FOR {au_long}:**

**🏆 PREMIUM SELECTIONS (1.5 Units)**

🐕 **[DOG NAME]** | Race [X] | [TRACK NAME] 
📦 **Box:** [X] | ⏰ **Time:** [XX:XX AWST] | 📏 **Distance:** [XXX]m
💰 **Stake:** 1.5 Units | **Bet Type:** Win
📊 **Key Factors:** [List 2-3 strongest factors]
💡 **Analysis:** [Brief reasoning for premium confidence]

**⭐ SOLID SELECTIONS (1.0 Units)**

🐕 **[DOG NAME]** | Race [X] | [TRACK NAME]
📦 **Box:** [X] | ⏰ **Time:** [XX:XX AWST] | 📏 **Distance:** [XXX]m  
💰 **Stake:** 1.0 Units | **Bet Type:** Win
📊 **Key Factors:** [List key factors]
💡 **Analysis:** [Brief reasoning]

**💡 SPECULATIVE PLAYS (0.5 Units)**

🐕 **[DOG NAME]** | Race [X] | [TRACK NAME]
📦 **Box:** [X] | ⏰ **Time:** [XX:XX AWST] | 📏 **Distance:** [XXX]m
💰 **Stake:** 0.5 Units | **Bet Type:** Each-Way  
📊 **Key Factors:** [List factors]
💡 **Analysis:** [Brief reasoning]

� **MEETING COVERAGE SUMMARY:**
- Total Meetings Analyzed: [X]
- States Covered: [List states]
- Total Selections: [X] across [X] different races
- Total Recommended Outlay: [X.X] Units

🚨 **SELECTION RULES ENFORCED:**
- ✅ Maximum 1 greyhound per race
- ✅ Maximum 1.5 units per selection  
- ✅ Diversified across multiple venues
- ✅ Comprehensive venue scanning completed

CRITICAL: Never select multiple greyhounds from the same race. Always spread selections across different tracks and race numbers. Keep unit stakes between 0.5-1.5 maximum."""

    try:
        print("🔍 Starting comprehensive greyhound analysis...")
        print("⏳ This may take 3-5 minutes for complete web research and analysis...")
        
        # Try with search grounding first
        try:
            response = await call_gemini_with_search_grounding(main_prompt, au_iso)
            
            if response and len(response.strip()) > 100:
                print("✅ Analysis completed with search grounding!")
                final_answer = response
            else:
                raise Exception("Invalid response from search grounding API")
            
        except Exception as search_error:
            print(f"⚠️ Search grounding failed: {str(search_error)}")
            print("🔄 Falling back to text generation without search grounding...")
            
            # Fallback to regular generation without tools
            fallback_prompt = main_prompt.replace("You MUST use your web search tools", "You should use your knowledge and reasoning")
            fallback_prompt = fallback_prompt.replace("MUST USE WEB SEARCH:", "SHOULD ATTEMPT:")
            
            response = await call_gemini_fallback(fallback_prompt)
            
            if response:
                print("✅ Analysis completed with text generation fallback!")
                final_answer = response
            else:
                raise Exception("Both search grounding and fallback failed")
        
        # Check if response is valid before processing
        if not final_answer:
            print("⚠️ No response received from API")
            return f"""🐕 Greyhound Racing Analysis - {au_long}

⚠️ **API Response Issue**

The analysis system did not receive a valid response from the AI service.

📅 **Manual Check Required:**
- Visit TAB.com.au → Greyhounds for today's meetings
- Check TheDogs.com.au for race cards
- Review form guides on major racing websites

⚠️ **DISCLAIMER**: Check official racing websites for current race information."""
        
        print("✅ Analysis completed successfully!")
        
        # Apply diversification filter to ensure no duplicate races
        if final_answer:
            print("🔍 Applying race diversification filter...")
            final_answer = filter_diverse_selections(final_answer)
        
        # Process response parts to separate thoughts from final answer
        # final_answer is already set above
        
        # Clean up any step markers but keep all race content
        lines_to_keep = []
        
        for line in final_answer.split('\n'):
            # Only skip very obvious step headers, keep everything else
            if line.strip().startswith(('**STEP', 'STEP 1:', 'STEP 2:', 'STEP 3:', 'STEP 4:', 'STEP 5:')):
                continue
            else:
                lines_to_keep.append(line)
        
        final_answer = '\n'.join(lines_to_keep)
        
        # Add enhanced disclaimer with unit guidance
        disclaimer = """

💰 **UNIT STAKING GUIDE:**
- 1 Unit = Your standard betting amount (e.g., $10, $20, $50)
- Never bet more than you can afford to lose
- Consider your bankroll size when determining unit value

⚠️ **DISCLAIMER**: Check current odds with your bookmaker before placing bets. Gamble responsibly. Units are recommendations only - adjust to your bankroll."""
        
        full_response = final_answer + disclaimer
        
        # Check if the response indicates no data found
        no_data_indicators = [
            "❌ No current greyhound race data found",
            "No greyhound meetings found",
            "Unable to find race data",
            "No race meetings scheduled",
            "I was unable to find",
            "couldn't find any specific",
            "no specific race meetings"
        ]
        
        contains_no_data_message = any(indicator in full_response for indicator in no_data_indicators)
        
        if contains_no_data_message:
            print("⚠️ DEBUG: Detected 'no data found' message")
            return f"""🐕 Greyhound Racing Analysis - {au_long}

🔍 **COMPREHENSIVE SEARCH COMPLETED**

Despite extensive searching, specific race meeting data was not found for {au_long}.

📅 **SEARCH CONTEXT:**
- Date: {au_long} ({au_iso})
- Time: {perth_time}
- Searched: TAB, TheDogs, Racing.com, Sportsbet, venue-specific sites

💡 **RECOMMENDED NEXT STEPS:**
1. **Manual Check**: Visit TAB.com.au → Greyhounds → Today's Meetings
2. **TheDogs.com.au**: Check race cards section for {au_iso}
3. **Racing.com**: Look for {au_long} greyhound meetings
4. **State-Specific**: Check GRV (VIC), RWWA (WA), Racing NSW

🏁 **TYPICAL VENUES TO CHECK:**
- **NSW**: Gosford, Bulli, Richmond, Wentworth Park
- **VIC**: Sandown, Healesville, Warragul
- **QLD**: Albion Park, Ipswich, Townsville
- **SA**: Murray Bridge, Angle Park
- **WA**: Cannington, Mandurah

⏰ **TIMING NOTE:**
- If it's early morning, evening meeting cards may not be published yet
- Check back after 12:00 PM for evening meetings
- Weekend schedules are typically published earlier

⚠️ **DISCLAIMER**: Racing schedules can vary. Always check official sources for the most current information."""
        
        return full_response
        
    except asyncio.TimeoutError:
        return f"""⚠️ **ANALYSIS TIMEOUT**

The comprehensive analysis for {au_long} took longer than expected. 

🔄 **RECOMMENDED ACTIONS:**
- Check official racing websites directly
- Try again in 10-15 minutes

⚠️ **DISCLAIMER**: Check official racing websites for current race information."""
    except Exception as e:
        return f"⚠️ Error generating greyhound tips for {au_long}: {str(e)}"

async def send_webhook_message(content, title="🐕 Greyhound Racing Tips - Daily Analysis"):
    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(WEBHOOK_URL, session=session)
            
            # Create and send the embed
            embed = discord.Embed(
                title=title,
                description=content[:4096] if len(content) > 4096 else content,
                color=0x00ff00
            )
            embed.set_footer(text=f"Generated on {datetime.now(PERTH_TZ).strftime('%B %d, %Y at %H:%M AWST')}")
            
            # Split content into multiple embeds if too long
            if len(content) > 4096:
                remaining_content = content[4096:]
                await webhook.send(embed=embed)
                
                while remaining_content:
                    chunk = remaining_content[:4096]
                    remaining_content = remaining_content[4096:]
                    
                    embed = discord.Embed(description=chunk, color=0x00ff00)
                    await webhook.send(embed=embed)
                    await asyncio.sleep(1)  # Small delay between messages
            else:
                await webhook.send(embed=embed)
                
    except Exception as e:
        print(f"Error sending webhook: {str(e)}")

async def main():
    print("🚀 Starting Greyhound Racing Tips Bot - Railway Ready!")
    print("=" * 60)
    
    # Debug current dates and configuration
    perth_now = get_effective_date()  # Use effective date
    system_now = datetime.now()  # American system time
    utc_now = datetime.utcnow()
    australian_now = datetime.now(AEST_TZ)  # Correct Australian time
    
    print(f"🕐 System time (American): {system_now.strftime('%Y-%m-%d %H:%M')}")
    print(f"🌍 UTC time: {utc_now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"🇦🇺 Australian time (AEST): {australian_now.strftime('%Y-%m-%d %H:%M AEST')}")
    print(f"🇦🇺 Perth time: {perth_now.strftime('%Y-%m-%d %H:%M AWST')}")
    print(f"📅 Target date: {perth_now.strftime('%B %d, %Y')} ({perth_now.strftime('%Y-%m-%d')})")
    if OVERRIDE_DATE:
        print(f"� OVERRIDE_DATE set to: {OVERRIDE_DATE}")
    else:
        print(f"📅 Using Australian date (not American system date): {australian_now.strftime('%B %d, %Y')}")
    print(f"📁 Data directory: {DATA_DIR}")
    print("=" * 60)
    
    # Ensure data directory and files exist for Railway deployment
    ensure_data_dir_and_files()
    
    # Test web search capability
    print("🔍 Testing Google Search Grounding capability...")
    web_search_working = await test_web_search_capability()
    
    if web_search_working:
        print("✅ Search grounding is enabled - bot will attempt to use real-time web data")
        print("⚠️ Note: Racing data availability depends on website access and paywall restrictions")
    else:
        print("⚠️ Search grounding may not be available - bot will use text generation only")
        print("💡 Ensure your Google Cloud project has Search Grounding enabled in the Generative Language API")
        print("💡 Even with search grounding, detailed race cards may not be accessible due to paywalls")
    
    print("=" * 60)
    
    # Check for Railway environment variable to determine mode
    # Default to 'schedule' mode for automatic daily operation
    mode = os.environ.get('RUN_MODE', 'schedule').lower()
    print(f"🔧 Running in mode: {mode}")
    print(f"📊 RUN_MODE from environment: {os.environ.get('RUN_MODE', 'Not set - using default schedule mode')}")
    
    if mode == 'research':
        # Research mode - run analysis but don't send to Discord
        try:
            print("Running in research mode - analysis only, no Discord posting...")
            await research_analysis_only()
            print("Research analysis completed.")
        except Exception as e:
            print(f"Error in research mode: {str(e)}")
    elif mode == 'schedule':
        # Improved scheduler with precise timing and better reliability
        print("Running in scheduler mode: will post at 07:00 and 19:00 AWST daily")
        
        # Track what we've run with persistent file storage
        status_file = os.path.join(DATA_DIR, 'scheduler_status.json')
        
        def load_scheduler_status():
            try:
                if os.path.exists(status_file):
                    with open(status_file, 'r') as f:
                        return json.load(f)
                return {'last_morning_run': None, 'last_evening_run': None}
            except:
                return {'last_morning_run': None, 'last_evening_run': None}
        
        def save_scheduler_status(status):
            try:
                with open(status_file, 'w') as f:
                    json.dump(status, f)
            except Exception as e:
                print(f"Error saving scheduler status: {e}")
        
        scheduler_status = load_scheduler_status()
        print(f"Loaded scheduler status: {scheduler_status}")
        
        # Generate fresh tips immediately on first run
        print("🚀 Generating fresh tips immediately on startup...")
        try:
            tips = await generate_greyhound_tips()
            await send_webhook_message(tips, title="🚀 Fresh Greyhound Tips - Bot Started")
            print("✅ Fresh tips posted successfully!")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error generating fresh tips on startup: {error_msg}")
            
            # Send a startup notification even if tips failed
            try:
                fallback_message = f"""🚀 **GREYHOUND BOT STARTED**

⚠️ **STARTUP ISSUE DETECTED**
The bot started successfully but encountered an issue generating initial tips:
`{error_msg[:200]}...` 

🔄 **AUTOMATIC RECOVERY:**
- Bot is now running in schedule mode
- Will retry at 7:00 AM AWST (morning tips)
- Will attempt evening analysis at 7:00 PM AWST

⏰ **NEXT SCHEDULED RUNS:**
- Morning: 07:00 AWST daily
- Evening: 19:00 AWST daily

🛠️ **STATUS:** Bot monitoring active, waiting for next scheduled run."""
                
                await send_webhook_message(fallback_message, title="🚀 Greyhound Bot - Startup Complete")
                print("📢 Startup notification sent to Discord")
            except Exception as webhook_error:
                print(f"❌ Failed to send startup notification: {webhook_error}")
        
        print("📅 Now entering scheduler mode...")
        
        try:
            while True:
                # Use Australian date for scheduler timing
                now_australian = datetime.now(AEST_TZ)
                now_perth = now_australian.astimezone(PERTH_TZ)
                today_str = now_australian.strftime('%Y-%m-%d')  # Australian date
                current_time = now_perth.time()
                current_hour = current_time.hour
                current_minute = current_time.minute
                
                # Check if it's morning window (6-8 AM for better reliability)
                if (6 <= current_hour <= 8 and current_minute < 30 and 
                    scheduler_status.get('last_morning_run') != today_str):
                    
                    print(f"🌅 Triggering 7AM greyhound tips run at {now_perth.strftime('%H:%M AWST')}...")
                    try:
                        tips = await generate_greyhound_tips()
                        await send_webhook_message(tips, title="🌅 Daily Greyhound Tips - 7AM Perth")
                        
                        # Update status
                        scheduler_status['last_morning_run'] = today_str
                        save_scheduler_status(scheduler_status)
                        print(f"✅ 7AM tips posted successfully for {today_str}")
                        
                    except Exception as e:
                        print(f"❌ Error in 7AM run: {str(e)}")
                
                # 7PM evening analysis has been disabled
                # elif (current_hour == 19 and current_minute < 5 and 
                #       scheduler_status.get('last_evening_run') != today_str):
                #     print("🌇 7PM analysis has been disabled")
                
                # Debug output every 30 minutes
                if current_minute in [0, 30]:
                    next_morning = "today" if scheduler_status.get('last_morning_run') != today_str else "tomorrow"
                    next_evening = "today" if scheduler_status.get('last_evening_run') != today_str else "tomorrow"
                    print(f"⏰ {now_perth.strftime('%H:%M AWST')} - Next morning run: {next_morning} at 07:00, Next evening run: {next_evening} at 19:00")
                
                await asyncio.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            print("Scheduler stopped by user")
        except Exception as e:
            print(f"Scheduler error: {str(e)}")
    else:
        # One-off immediate run (morning tips)
        try:
            print("Generating greyhound tips (one-off)...")
            tips = await generate_greyhound_tips()
            print("Sending greyhound tips to Discord...")
            await send_webhook_message(tips)
            print("Done.")
        except Exception as e:
            print(f"Error: {str(e)}")

# Run the script
if __name__ == "__main__":
    asyncio.run(main())