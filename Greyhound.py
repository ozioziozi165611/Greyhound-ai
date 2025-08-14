"""
Greyhound Racing Tips Bot - Railway Ready

RAILWAY DEPLOYMENT INSTRUCTIONS:
1. Create new Railway project
2. Connect to GitHub repo containing this file
3. Add these files to your repo:
   
   requirements.txt:
   discord.py==2.3.2
   google-generativeai==0.8.3
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
6. Bot will automatically run in schedule mode and post at 7AM/7PM Perth time
"""

import discord
from discord import Webhook
from google import genai
from google.genai import types # type: ignore
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

# Data directory - Railway-friendly (will use /app/data in Railway)
if os.path.exists('/app'):
    # Railway deployment path
    DATA_DIR = '/app/data'
else:
    # Local development path
    DATA_DIR = r'c:\Users\Pixel\Desktop\HORSE AI LJ\data'

# Learning system files (within DATA_DIR)
LEARNING_DATA_FILE = os.path.join(DATA_DIR, 'greyhound_learning_data.json')
DAILY_PREDICTIONS_FILE = os.path.join(DATA_DIR, 'daily_greyhound_predictions.json')

DEFAULT_LEARNING_DATA = {
    'total_predictions': 0,
    'successful_predictions': 0,
    'failed_predictions': 0,
    'win_rate': 0.0,
    'successful_patterns': [],
    'failed_patterns': [],
    'trainer_performance': {},
    'track_performance': {},
    'distance_performance': {},
    'box_performance': {},
    'grade_performance': {},
    'learning_insights': []
}

def default_predictions_for_today():
    perth_now = datetime.now(PERTH_TZ)
    return {
        'date': perth_now.strftime('%Y-%m-%d'),
        'predictions': [],
        'generated_at': perth_now.strftime('%H:%M AWST')
    }

def ensure_data_dir_and_files():
    """Ensure data directory and JSON files exist (Railway-ready)."""
    global DATA_DIR, LEARNING_DATA_FILE, DAILY_PREDICTIONS_FILE
    
    try:
        # Create data directory with proper permissions
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"📁 Data directory: {DATA_DIR}")
        
        # Learning data file
        if not os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'w') as f:
                json.dump(DEFAULT_LEARNING_DATA, f, indent=2)
            print("📊 Created learning data file")
        
        # Daily predictions file
        if not os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'w') as f:
                json.dump(default_predictions_for_today(), f, indent=2)
            print("📅 Created daily predictions file")
            
    except Exception as e:
        print(f"❌ Error ensuring data files: {e}")
        # Try to create in current directory as fallback
        DATA_DIR = './data'
        LEARNING_DATA_FILE = os.path.join(DATA_DIR, 'greyhound_learning_data.json')
        DAILY_PREDICTIONS_FILE = os.path.join(DATA_DIR, 'daily_greyhound_predictions.json')
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"📁 Fallback data directory: {DATA_DIR}")

# Perth timezone
PERTH_TZ = pytz.timezone('Australia/Perth')

# Initialize Gemini client with proper SDK
client = genai.Client(api_key=GEMINI_API_KEY)

# Define grounding tool for REAL web search
grounding_tool = types.Tool(google_search=types.GoogleSearch())

# Configure generation with deep thinking AND real web search with extended budget
generation_config = types.GenerateContentConfig(
    tools=[grounding_tool],  # Enable real-time web search
    thinking_config=types.ThinkingConfig(
        thinking_budget=30000,  # Set to 30k tokens for extended analysis (max allowed: 32768)
        include_thoughts=True  # Include reasoning process
    ),
    temperature=0.2,
    top_p=0.8,
    top_k=30,
    max_output_tokens=32768  # Doubled output tokens for comprehensive analysis
)

def load_learning_data():
    """Load learning data from file"""
    try:
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r') as f:
                return json.load(f)
        # Create default if missing
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LEARNING_DATA_FILE, 'w') as f:
            json.dump(DEFAULT_LEARNING_DATA, f, indent=2)
        return DEFAULT_LEARNING_DATA.copy()
    except Exception as e:
        print(f"Error loading learning data: {e}")
        return DEFAULT_LEARNING_DATA.copy()

def save_learning_data(data):
    """Save learning data to file"""
    try:
        with open(LEARNING_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving learning data: {e}")

def load_daily_predictions():
    """Load today's predictions"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'r') as f:
                data = json.load(f)
            # Ensure file is for today
            perth_now = datetime.now(PERTH_TZ)
            today_str = perth_now.strftime('%Y-%m-%d')
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

def get_learning_enhanced_prompt():
    """Generate enhanced prompt based on learning data"""
    learning_data = load_learning_data()
    
    base_insights = ""
    if learning_data['total_predictions'] > 0:
        win_rate = learning_data['win_rate']
        base_insights = f"""
🧠 LEARNING SYSTEM INSIGHTS (Win Rate: {win_rate:.1f}%):

SUCCESSFUL PATTERNS IDENTIFIED:
{chr(10).join(learning_data['successful_patterns'][-10:])}

FAILED PATTERNS TO AVOID:
{chr(10).join(learning_data['failed_patterns'][-10:])}

TOP PERFORMING INSIGHTS:
{chr(10).join(learning_data['learning_insights'][-5:])}

ADJUST YOUR ANALYSIS BASED ON THESE PROVEN PATTERNS."""
    
    return base_insights

async def generate_greyhound_tips():
    """Generate greyhound tips for today's races only (Perth timezone)"""
    perth_now = datetime.now(PERTH_TZ)
    
    # Always use dynamic "today" language instead of specific dates
    target_date_search = perth_now.strftime("%Y-%m-%d")
    current_time_perth = perth_now.strftime("%H:%M AWST")
    
    print(f"Generating fresh greyhound tips for TODAY at {current_time_perth}")
    print(f"DEBUG: Perth date: {target_date_search}, Perth time: {current_time_perth}")
    
    # Get learning insights
    learning_insights = get_learning_enhanced_prompt()
    
    # Analyze today's greyhound races only - using dynamic language
    tips_result = await analyze_greyhound_racing_day(current_time_perth, learning_insights)
    
    # Save predictions for evening analysis
    predictions_data = {
        'date': target_date_search,
        'predictions': extract_predictions_for_learning(tips_result),
        'generated_at': current_time_perth
    }
    save_daily_predictions(predictions_data)
    
    return tips_result

async def research_analysis_only():
    """Generate research analysis without sending to Discord - for testing and verification"""
    perth_now = datetime.now(PERTH_TZ)
    current_time_perth = perth_now.strftime("%H:%M AWST")
    
    print(f"Generating research analysis for TODAY at {current_time_perth}")
    
    # Get learning insights
    learning_insights = get_learning_enhanced_prompt()
    
    # Analyze today's greyhound races only - research mode
    research_result = await analyze_greyhound_racing_day(current_time_perth, learning_insights)
    
    # Print to console instead of sending to Discord
    print("\n" + "="*80)
    print("RESEARCH ANALYSIS RESULTS")
    print("="*80)
    print(research_result)
    print("="*80)
    
    return research_result

def extract_predictions_for_learning(tips_content):
    """Extract predictions from greyhound tips content for later learning analysis"""
    predictions = []
    lines = tips_content.split('\n')
    
    current_greyhound = {}
    for line in lines:
        if line.startswith('🐕 **') and '**' in line:
            if current_greyhound:
                predictions.append(current_greyhound)
            # Extract greyhound name
            greyhound_match = re.search(r'🐕 \*\*(.*?)\*\*', line)
            if greyhound_match:
                current_greyhound = {
                    'greyhound_name': greyhound_match.group(1),
                    'race_info': line,
                    'prediction_details': []
                }
        elif current_greyhound and any(keyword in line for keyword in ['Composite Score:', 'Race Time:', 'Track:', 'Box:', 'Distance:']):
            current_greyhound['prediction_details'].append(line)
        elif current_greyhound and line.startswith('💡 **Analysis:**'):
            current_greyhound['analysis'] = line
    
    if current_greyhound:
        predictions.append(current_greyhound)
    
    return predictions

async def analyze_results_and_learn():
    """Analyze today's greyhound race results (Perth date) and learn from predictions"""
    perth_now = datetime.now(PERTH_TZ)
    today_str = perth_now.strftime('%Y-%m-%d')
    
    print(f"Analyzing greyhound results and learning for TODAY")
    
    # Load today's predictions
    predictions_data = load_daily_predictions()
    if not predictions_data.get('predictions'):
        print("No predictions found for today")
        return "No predictions to analyze for today."
    
    # Get race results for analysis using dynamic language
    results_prompt = f"""🔍 GREYHOUND RACE RESULTS ANALYSIS - TODAY'S RESULTS

Please search for TODAY'S Australian greyhound racing results and provide:

1. Winners of all races that have finished today
2. Finishing positions for all greyhounds
3. Starting prices/odds
4. Track conditions
5. Winning margins and times

Search across:
- TheDogs.com.au results for today
- Racing NSW greyhound results today
- GRV (Greyhound Racing Victoria) results today
- RWWA greyhound results today
- TAB greyhound results today
- Other Australian greyhound racing result sites

Provide results in this concise format:
🐕 RACE X - TRACK NAME (TODAY)
🥇 Winner: GREYHOUND NAME (Box: X, Trainer: Y, SP: $X.XX, Time: XX.XXs)
---"""

    try:
        print("🔍 Analyzing race results...")
        # Get race results using web search with timeout
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-pro",
                contents=results_prompt,
                config=generation_config
            ),
            timeout=300.0  # 5 minute timeout for results analysis
        )
        
        results_content = ""
        for part in response.candidates[0].content.parts:
            if not hasattr(part, 'thought') or not part.thought:
                results_content += part.text
        
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
    """Analyze how accurate our predictions were and update learning data"""
    learning_data = load_learning_data()
    
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
    
    # Trim lists
    learning_data['successful_patterns'] = learning_data['successful_patterns'][-50:]
    learning_data['failed_patterns'] = learning_data['failed_patterns'][-50:]
    learning_data['learning_insights'] = learning_data['learning_insights'][-20:]
    
    save_learning_data(learning_data)
    
    pct = (correct_predictions/total_predictions)*100 if total_predictions else 0
    return f"📈 Accuracy: {correct_predictions}/{total_predictions} ({pct:.1f}%) | Overall win rate: {learning_data['win_rate']:.1f}%\n" + "\n".join(analysis_summary)

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

async def analyze_greyhound_racing_day(current_time_perth, learning_insights):
    """Analyze TODAY only (Perth date) with comprehensive greyhound analysis using dynamic language"""
    
    print(f"🔍 Starting comprehensive greyhound analysis for TODAY...")
    
    # Expert greyhound racing analyst prompt with dynamic language
    main_prompt = f"""You are an expert greyhound racing analyst and betting strategist. I need you to analyze ALL greyhound races scheduled for TODAY across Australia.

Current Time: {current_time_perth} (Perth/AWST)
Target Analysis: ALL greyhound races for TODAY that haven't started yet

{learning_insights}

CRITICAL: Use REAL-TIME web search to find TODAY'S actual greyhound race meetings and runners. Do NOT generate fake or placeholder data.

COMPREHENSIVE ANALYSIS PROCESS (MANDATORY):

**Step 1: Find ALL Australian Greyhound Meetings for TODAY**
MUST COMPLETE: Search for ALL greyhound meetings scheduled across Australia for TODAY. USE THESE EXACT SEARCH TERMS:
- Search: "greyhound racing today Australia"
- Search: "TAB greyhound racing today live"  
- Search: "thedogs.com.au race cards today"
- Search: "greyhound race meetings tonight Australia"
- Search: "live greyhound racing today Australia"
- Search: "Australian greyhound meetings today"
- Search: "tab.com.au greyhound racing today"
- Search: "sportsbet greyhound racing today"
- Search: "racing.com greyhound meetings today"
- Search: "greyhound racing venues Australia today"

**Step 2: Get REAL Race Form Data for TODAY'S Meetings**
MUST COMPLETE: For each meeting found, search for actual race data:
- Search: "[Track Name] greyhound race card today"
- Search: "greyhound form guide today [Track Name]"
- Search: "TheDogs.com.au race cards today"
- Search: "greyhound runners and form today"

**Step 3: Check Current Track Conditions and Scratchings**
MUST COMPLETE: Get up-to-date information:
- Search: "greyhound track conditions today Australia"
- Search: "greyhound scratchings today"
- Search: "track reports greyhound racing today"

**Step 4: Get Current Market Odds**
MUST COMPLETE: Find current betting markets:
- Search: "live greyhound racing odds today Australia"
- Search: "greyhound betting odds today"
- Search: "TAB greyhound odds today"

**CRITICAL REQUIREMENTS:**
- Current time is {current_time_perth} AWST
- ONLY analyze races that start AFTER this time
- Use REAL dog names from actual race cards
- NO fake, placeholder, or example data
- If you cannot find real race data for today, clearly state this

**SELECTION CRITERIA FOR TIPS:**
- Win probability >35% OR place probability >65%
- Minimum odds of $2.00 (no short-priced favorites)
- Strong value compared to market odds (minimum 20% edge)
- Races must not have started yet

**OUTPUT FORMAT - ONLY if you find REAL race data:**

🐕 **TOP GREYHOUND SELECTIONS FOR TODAY:**

For each REAL selection found:
🐕 **[REAL DOG NAME]** | Race [X] | [REAL TRACK NAME]
📦 **Box:** [X] | ⏰ **Time:** [XX:XX AWST] | 📏 **Distance:** [XXX]m
🎯 **Win:** [XX]% | 🎲 **Place:** [XX]% | 💰 **Odds:** $[X.XX]
🏆 **Bet:** [Win/Each-Way] | 💵 **Stake:** [0.5-1.5] units
💡 **Analysis:** [Brief reasoning based on real form data]

**If you cannot find real race data for today, respond with:**
"❌ No current greyhound race data found for today. Please check TAB.com.au or TheDogs.com.au for today's meetings."

IMPORTANT: Today is a normal day - there should be greyhound meetings across Australia. If you're not finding meetings, it may be because:
1. Meetings are published closer to race time
2. It's early in the day and evening meetings aren't published yet
3. Search access limitations

Try multiple search approaches and clearly state what you found vs what you couldn't access.

BEGIN ANALYSIS - PROVIDE ONLY REAL DATA OR CLEAR "NO DATA FOUND" MESSAGE."""

    try:
        print("🔍 Starting comprehensive greyhound analysis...")
        print("⏳ This may take 3-5 minutes for complete web research and analysis...")
        
        # Generate greyhound tips using REAL web search + deep thinking with extended timeout
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-pro",
                contents=main_prompt,
                config=generation_config
            ),
            timeout=600.0  # 10 minute timeout to allow for comprehensive analysis
        )
        
        print("✅ Analysis completed successfully!")
        
        # Process response parts to separate thoughts from final answer
        final_answer = ""
        
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                # Skip thoughts - don't include them in output
                continue
            else:
                final_answer += part.text
        
        # Clean up any step markers but keep all race content
        lines_to_keep = []
        
        for line in final_answer.split('\n'):
            # Only skip very obvious step headers, keep everything else
            if line.strip().startswith(('**STEP', 'STEP 1:', 'STEP 2:', 'STEP 3:', 'STEP 4:', 'STEP 5:')):
                continue
            else:
                lines_to_keep.append(line)
        
        final_answer = '\n'.join(lines_to_keep)
        
        # Add disclaimer
        disclaimer = """

⚠️ **DISCLAIMER**: Check current odds with your bookmaker before placing bets. Gamble responsibly."""
        
        full_response = final_answer + disclaimer
        
        print(f"📊 DEBUG: Response length: {len(full_response)} characters")
        
        # Check for fake data indicators
        fake_data_indicators = [
            "Example Dog Name",
            "SAMPLE GREYHOUND", 
            "Demo Track",
            "Sample Race",
            "XX:XX AWST",
            "X.XX",
            "XXX%",
            "Box X",
            "Track Name"
        ]
        
        contains_fake_data = any(indicator in full_response for indicator in fake_data_indicators)
        
        if contains_fake_data:
            print("⚠️ DEBUG: Detected fake/template data in response")
            return """🐕 Greyhound Racing Analysis - TODAY

❌ **REAL DATA SEARCH ISSUE**

The analysis system was unable to locate real greyhound race data for today. This typically means:

🔍 **POSSIBLE CAUSES:**
- Race meetings not yet published for today
- Website access limitations during analysis
- Races may be scheduled for later publication

💡 **RECOMMENDED ACTIONS:**
- Check TAB.com.au directly for today's greyhound meetings
- Visit TheDogs.com.au for current race cards
- Racing schedules are often published closer to race times

⏰ **TYPICAL SCHEDULE:**
- Weekday evening meetings usually published by midday
- Weekend meetings published 1-2 days ahead
- Check back in a few hours if no meetings found

⚠️ **DISCLAIMER**: Please verify all information with official racing websites before placing any bets."""
        
        return full_response
        
    except asyncio.TimeoutError:
        return """⚠️ **ANALYSIS TIMEOUT**

The comprehensive analysis took longer than expected. Please try again in a few minutes.

⚠️ **DISCLAIMER**: Check official racing websites for current race information."""
    except Exception as e:
        return f"⚠️ Error generating greyhound tips: {str(e)}"

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
    perth_now = datetime.now(PERTH_TZ)
    system_now = datetime.now()
    utc_now = datetime.utcnow()
    
    print(f"🕐 System time: {system_now.strftime('%Y-%m-%d %H:%M')}")
    print(f"� UTC time: {utc_now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"�🇦🇺 Perth time: {perth_now.strftime('%Y-%m-%d %H:%M AWST')}")
    print(f"📅 Target date: {perth_now.strftime('%B %d, %Y')} ({perth_now.strftime('%Y-%m-%d')})")
    print(f"📁 Data directory: {DATA_DIR}")
    
    # Check if this seems like a future date issue
    import time
    epoch_time = time.time()
    readable_epoch = datetime.fromtimestamp(epoch_time)
    print(f"🔍 System epoch time: {readable_epoch.strftime('%Y-%m-%d %H:%M')}")
    print(f"📊 Current year from system: {system_now.year}")
    
    if system_now.year >= 2025:
        print("⚠️ WARNING: System date appears to be in the future!")
        print("This is likely why the bot thinks there's no race data available.")
        print("Local vs Railway environments may have different system dates.")
    print("=" * 60)
    
    # Ensure data directory and files exist for Railway deployment
    ensure_data_dir_and_files()
    
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
                now_perth = datetime.now(PERTH_TZ)
                today_str = now_perth.strftime('%Y-%m-%d')
                current_time = now_perth.time()
                current_hour = current_time.hour
                current_minute = current_time.minute
                
                # Check if it's 7:00 AM (07:00-07:05 window for reliability)
                if (current_hour == 7 and current_minute < 5 and 
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
                
                # Check if it's 7:00 PM (19:00-19:05 window for reliability)
                elif (current_hour == 19 and current_minute < 5 and 
                      scheduler_status.get('last_evening_run') != today_str):
                    
                    print(f"🌇 Triggering 7PM greyhound results analysis at {now_perth.strftime('%H:%M AWST')}...")
                    try:
                        await analyze_results_and_learn()
                        
                        # Update status
                        scheduler_status['last_evening_run'] = today_str
                        save_scheduler_status(scheduler_status)
                        print(f"✅ 7PM analysis completed successfully for {today_str}")
                        
                    except Exception as e:
                        print(f"❌ Error in 7PM run: {str(e)}")
                
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