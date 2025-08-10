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

# API Configuration (Railway environment variables - NO DEFAULTS for security)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Validate required environment variables
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

# Data directory (Railway volume mount recommended: /data)
DATA_DIR = os.getenv('DATA_DIR', '/data')  # Default to /data for Railway

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
    """Ensure data directory and JSON files exist (Railway-friendly)."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        # Learning data
        if not os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'w') as f:
                json.dump(DEFAULT_LEARNING_DATA, f, indent=2)
        # Daily predictions (today)
        if not os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'w') as f:
                json.dump(default_predictions_for_today(), f, indent=2)
    except Exception as e:
        print(f"Error ensuring data files: {e}")

# Perth timezone
PERTH_TZ = pytz.timezone('Australia/Perth')

# Initialize Gemini client with proper SDK
client = genai.Client(api_key=GEMINI_API_KEY)

# Define grounding tool for REAL web search
grounding_tool = types.Tool(google_search=types.GoogleSearch())

# Configure generation with deep thinking AND real web search
generation_config = types.GenerateContentConfig(
    tools=[grounding_tool],  # Enable real-time web search
    thinking_config=types.ThinkingConfig(
        thinking_budget=-1,  # Dynamic thinking
        include_thoughts=True  # Include reasoning process
    ),
    temperature=0.2,
    top_p=0.8,
    top_k=30,
    max_output_tokens=16384
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
    target_date_str = perth_now.strftime("%B %d, %Y")
    target_date_search = perth_now.strftime("%Y-%m-%d")
    current_time_perth = perth_now.strftime("%H:%M AWST")
    
    print(f"Generating greyhound tips for {target_date_str} at {current_time_perth}")
    print(f"DEBUG: Perth date: {target_date_search}, Perth time: {current_time_perth}")
    
    # Get learning insights
    learning_insights = get_learning_enhanced_prompt()
    
    # Analyze today's greyhound races only
    tips_result = await analyze_greyhound_racing_day(target_date_str, target_date_search, current_time_perth, learning_insights)
    
    # Save predictions for evening analysis
    predictions_data = {
        'date': target_date_search,
        'predictions': extract_predictions_for_learning(tips_result),
        'generated_at': current_time_perth
    }
    save_daily_predictions(predictions_data)
    
    return tips_result

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
    
    print(f"Analyzing greyhound results and learning for {today_str}")
    
    # Load today's predictions
    predictions_data = load_daily_predictions()
    if not predictions_data.get('predictions'):
        print("No predictions found for today")
        return "No predictions to analyze for today."
    
    # Get race results for analysis
    results_prompt = f"""🔍 GREYHOUND RACE RESULTS ANALYSIS - Perth Date: {today_str}

Please search for today's Australian greyhound racing results for {today_str} and provide:

1. Winners of all races
2. Finishing positions for all greyhounds
3. Starting prices/odds
4. Track conditions
5. Winning margins and times

Search across:
- TheDogs.com.au results
- Racing NSW greyhound results
- GRV (Greyhound Racing Victoria) results
- RWWA greyhound results
- Other Australian greyhound racing result sites

Provide results in this concise format:
🐕 RACE X - TRACK NAME
🥇 Winner: GREYHOUND NAME (Box: X, Trainer: Y, SP: $X.XX, Time: XX.XXs)
---"""

    try:
        # Get race results using web search
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-pro",
            contents=results_prompt,
            config=generation_config
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
        horse_name = prediction['greyhound_name']
        # crude winner detection; can be improved later
        winner_line = re.search(r"Winner:\s*([A-Za-z'’\-\.\s]+)", results_content, re.IGNORECASE)
        if winner_line:
            winner_name = winner_line.group(1).strip()
        else:
            winner_name = ""
        
        if horse_name and winner_name and horse_name.lower() in winner_name.lower():
            correct_predictions += 1
            analysis_summary.append(f"✅ {horse_name} - CORRECT (Won)")
            for detail in prediction.get('prediction_details', []):
                if 'Composite Score:' in detail or 'Track:' in detail or 'Box:' in detail:
                    learning_data['successful_patterns'].append(f"WINNER - {horse_name}: {detail}")
        else:
            analysis_summary.append(f"❌ {horse_name} - FAILED (Did not win)")
            for detail in prediction.get('prediction_details', []):
                if 'Composite Score:' in detail or 'Track:' in detail or 'Box:' in detail:
                    learning_data['failed_patterns'].append(f"FAILED - {horse_name}: {detail}")
    
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
    """Check if the tips content contains any strong greyhound selections"""
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

async def analyze_greyhound_racing_day(target_date_str, target_date_search, current_time_perth, learning_insights):
    """Analyze TODAY only (Perth date) with comprehensive greyhound analysis"""
    
    # Enhanced prompt with MANDATORY web search for REAL greyhound data, today only
    main_prompt = f"""🌐 LIVE WEB SEARCH REQUIRED - REAL AUSTRALIAN GREYHOUND RACING DATA

SYSTEM DATE CONFIRMATION: Today is SUNDAY, {target_date_str} ({target_date_search})
CURRENT PERTH TIME: {current_time_perth} (AWST)
DAY OF WEEK: SUNDAY

CRITICAL INSTRUCTION: You are analyzing greyhound races happening TODAY - SUNDAY {target_date_str} ({target_date_search}). This is NOT Monday or any other day - this is SUNDAY TODAY.

IMPORTANT: Search ONLY for greyhound race meetings scheduled for SUNDAY {target_date_search}. Do NOT include Monday races or any other day's races.

If there are NO greyhound races scheduled for today (Sunday), clearly state: "No greyhound races are scheduled for Sunday, {target_date_str}. The next available races are on [DATE]."

If races ARE found for today (Sunday), proceed with the analysis.

{learning_insights}

Generate the five best Australian greyhound racing tips for TODAY SUNDAY ({target_date_str}), you must draw on every publicly available piece of information for every licensed track in Australia, and apply a thorough, expert-level "deep analysis" to each candidate dog. Your process should include, but not be limited to, the following expanded checklist:

⸻
1. Comprehensive Track & Conditions Intelligence
• All Australian Tracks: Include data from every current meeting in NSW, VIC, QLD, WA, SA, TAS, NT and ACT. Pull the official racecards and track condition reports for each track (e.g., TheDogs.com.au, Racing Australia, state bodies).
• Track Configuration: Note each track's shape (circle vs. one-turn vs. two-turn), straight-away lengths, chute designs, and floodlighting.
• Surface & Weather: Record today's going ("Good," "Fast," "Slow," "Heavy" etc.), temperature, wind, rainfall and humidity—factors that alter ground speed, particularly at Tuggeranong, Hobart and Sandown.

2. In-Depth Greyhound Form Profiling
• Recent Performance: For each greyhound, compile its last 3–5 starts nationally, including finish position, winning margin, interference notes, grade of race, and whether it was first-up or second-up after a spell.
• Personal Best Times: Compare each dog's fastest recorded time at today's trip at that exact track against every other runner. Highlight any raw time advantage of 0.20s or more.
• Early Speed Metrics: Aggregate each dog's average first-section time ("1st Sec") at the relevant distance and surface condition. Identify outliers who consistently fire out fastest.
• Box-Draw Compatibility: Cross-reference each dog's career box-section splits (e.g., "PB(1), PB(2)…"), its preferred running style (rails, mid-track, wide) and today's barrier draw.
• Running Style Classification: Tag each runner as a "box-to-box leader," "pace presser," "clear-running finisher," or "strong last-200m kicker," then map that style to the expected race tempo.
• Class Movement Analysis: Note any dog dropping in class (easier fields) or stepping up (tougher competition) relative to its last few starts, flagging opportunities in Grade 5–FFA transitions.
• Trainer & Kennel Form: Pull the last 14 days of winners, placings and strikes for each trainer represented tonight, nationally. Weight trainers by metropolitan vs. country form.
• Spell & Fitness Check: For dogs resuming after a spell, inspect their first-up performances historically; adjust weightings for known "second-up peak" types.
• Physical Condition & Veterinary Alerts: Incorporate any publicly announced vet inspections, pawing issues, vet scratches, or late withdrawals.

3. Race Dynamics & Tactical Mapping
• Speedmap Construction: For each race, generate a sectional-based speed map showing likely leaders, challengers and back-markers. Use average '1st Sec' and box-section data to model the first 50 m.
• Pace Scenario Forecast: Classify the race as "fast" (multiple speed dogs), "slow" (no obvious front-runners) or "even," and adjust tip preference toward styles that will benefit.
• Congestion & Collision Risk: Identify clusters of early speeds drawn together (e.g., Boxes 1–3), highlight potential mid-race bottlenecks, and downgrade candidates likely to be crowded.
• Weak-Link Elimination: Automatically rule out any runner whose form line, sectional metrics or box compatibility falls more than 0.10 s behind the median of the field.

4. Data Sources & Verification
• Official Racecards: Use TheDogs.com.au, Racing NSW, GRV, RWWA, and state-based registration platforms for the most current fields and barrier draws.
• Track Announcements: Scrape or ingest official track condition updates (weather radar, maintenance bulletins) to confirm "Good" vs. "Fast" or "Slow."
• Live Vet & Scratchings Feed: Check Racing Australia's live scratchings and vet exclusions to ensure every tipped runner is confirmed to start.
• Time-Stamped Confirmation: For every tip, record the exact date, track, meeting and race number—and verify that, as of "{target_date_str}" in Perth time, the race has not yet been run.

CRITICAL ANALYSIS APPROACH:
- IGNORE any assumptions about future dates - TODAY IS SUNDAY {target_date_str} ({target_date_search})
- You MUST search extensively across multiple greyhound racing websites for TODAY'S races
- Cross-reference data from TheDogs.com.au, GRV, GRNSW, RWWA, GRSA, and greyhound racing media
- ABSOLUTELY NO FICTIONAL DATA - If you cannot find real greyhound names, real race times, and real track data, you MUST state "No verifiable race data found"
- Do NOT create fake greyhound names like "RAPID FIRE", "BOXCAR BULLET", "RAILWAY RAMPAGE" etc.
- Do NOT create fake race times or track conditions
- ONLY provide tips if you can verify real greyhound names from official sources
- CRITICAL: Double-check race numbers and field positions for each greyhound
- VERIFY each greyhound's actual race number and position in the field
- Incorrect race/field information will severely impact prediction accuracy
- If no races are found for TODAY, clearly state that no races are scheduled

CURRENT TIME FILTERING:
- Use AWST times; ONLY include races that haven't started yet
- Check race start times and exclude completed races

MINIMUM SELECTION CRITERIA:
- ONLY use data found through comprehensive web search of REAL racing websites
- ONLY include REAL greyhounds with REAL names from races that haven't run yet
- Cross-verify information across multiple greyhound racing websites
- REJECT any fictional or made-up greyhound names
- CRITICAL: Verify each greyhound's exact race number and field position
- Double-check race cards to ensure correct race/field matching
- If you cannot find 5 real greyhounds with verifiable data, state how many you found
- Select UP TO 5 greyhounds total (WIN TIPS ONLY) - fewer if insufficient real data
- Include all meetings you find a greyhound that matches the analysis
- Any track preference is acceptable
- No minimum odds requirement - focus on quality selections
- Any race distance if it suits the greyhound selected
- Make sure you believe the greyhound is the best in the race
- NEVER create fictional content - real data only

📋 REQUIRED OUTPUT FORMAT FOR DISCORD (AWST times):

For each of your five selections, output:

🐕 **GREYHOUND NAME** | Track Name | Race X
⏰ **Race Time:** XX:XX AWST | 📏 **Distance:** XXXm
🎯 **Composite Score:** XX/25 | 💰 **Win Odds:** $X.XX | � **Box:** X
🌦️ **Track:** Condition | 📊 **Analysis Score:** X.X/10
✅ **Status:** Still to run | 🏆 **BET TYPE:** WIN

💡 **Analysis:** [100-word analysis covering: Why its Best Time at this trip is superior, How its First-Sectional Speed and Box Draw align, Relevant Form notes (class drop, trainer heat, spell), Race Dynamics summary (pace forecast, congestion risk), Any public vet/injury alerts or fitness notes]

---

This is not a simulation I want real greyhounds for my best 5.
People will be using this advice so you cannot make anything up everything needs to be legitimate. Only win tips.

ANTI-FICTION REQUIREMENTS:
- Do NOT create fictional greyhound names
- Do NOT create fictional race times or track names
- Do NOT create fictional trainer names
- If you cannot find real, verifiable data, say "No real race data available for Sunday"
- REAL NAMES ONLY - no made-up content whatsoever

FINAL REMINDER: 
- ONLY search for races on SUNDAY {target_date_str} ({target_date_search})
- Do NOT include Monday {target_date_search} + 1 day races or any other day
- If no Sunday races exist, clearly state this fact
- If Sunday races do exist, provide ONLY real greyhound names and data
- NEVER CREATE FICTIONAL CONTENT

BEGIN WEB SEARCH FOR REAL AUSTRALIAN GREYHOUND RACING DATA FOR SUNDAY {target_date_str} ({target_date_search}) TODAY ONLY NOW."""

    try:
        # Generate greyhound tips using REAL web search + deep thinking
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-pro",
            contents=main_prompt,
            config=generation_config
        )
        
        # Process response parts to separate thoughts from final answer
        final_answer = ""
        thought_summary = ""
        
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                thought_summary += f"🤔 Deep Analysis: {part.text}\n\n"
            else:
                final_answer += part.text
        
        # Combine thought summary with final answer if available
        if thought_summary:
            full_response = f"{thought_summary}📊 **FINAL GREYHOUND TIPS:**\n\n{final_answer}"
        else:
            full_response = final_answer
        
        # Check if no races were found for today
        if "no greyhound races" in full_response.lower() or "next available races" in full_response.lower():
            return f"ℹ️ **NO RACES TODAY**: {full_response}"
        
        # Check for fictional content and reject it
        fictional_indicators = [
            "rapid fire", "boxcar bullet", "railway rampage", "murray's mate", "hobart hurricane",
            "aussie pablo", "our miss maggie", "ollie jack", "unconvicted", "rhinestone",
            "aston barton", "bourne model", "seattle", "reaper", "daintree shady"
        ]
        
        for indicator in fictional_indicators:
            if indicator.lower() in full_response.lower():
                return f"⚠️ **FICTIONAL DATA DETECTED**: The AI generated fake greyhound names instead of finding real race data. No legitimate greyhound races appear to be available for Sunday, {target_date_search}. Please check official racing websites for actual race meetings."
        
        # Add validation warning for race accuracy
        race_accuracy_warning = """
        
⚠️ **IMPORTANT**: Please verify race numbers and field positions are correct before using these tips. 
Incorrect race/field information can significantly impact win rate accuracy. 
Double-check each selection against official race cards."""
        
        return full_response + race_accuracy_warning
        
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
    print("Starting Greyhound Racing Tips Bot (Perth schedule)")
    
    # Debug current dates
    perth_now = datetime.now(PERTH_TZ)
    system_now = datetime.now()
    print(f"System time: {system_now.strftime('%Y-%m-%d %H:%M')}")
    print(f"Perth time: {perth_now.strftime('%Y-%m-%d %H:%M AWST')}")
    print(f"Target date for analysis: {perth_now.strftime('%B %d, %Y')} ({perth_now.strftime('%Y-%m-%d')})")
    
    print(f"Data directory: {DATA_DIR}")
    print(f"API Key configured: {'Yes' if GEMINI_API_KEY else 'No'}")
    print(f"Webhook configured: {'Yes' if WEBHOOK_URL else 'No'}")
    
    # Ensure data directory and files exist for Railway
    ensure_data_dir_and_files()
    
    mode = os.environ.get('RUN_MODE', 'once').lower()
    if mode == 'schedule':
        # Simple scheduler loop checking Perth time every minute
        print("Running in scheduler mode: will post at 07:00 and 19:00 AWST daily")
        last_run_date_morning = None
        last_run_date_evening = None
        try:
            while True:
                now_perth = datetime.now(PERTH_TZ)
                today = now_perth.date()
                current_time = now_perth.time()
                
                # 7:00 AM run
                if current_time >= dtime(7, 0) and (last_run_date_morning != today):
                    print("Triggering 7AM greyhound tips run...")
                    tips = await generate_greyhound_tips()
                    await send_webhook_message(tips)
                    last_run_date_morning = today
                
                # 7:00 PM run
                if current_time >= dtime(19, 0) and (last_run_date_evening != today):
                    print("Triggering 7PM greyhound results analysis run...")
                    await analyze_results_and_learn()
                    last_run_date_evening = today
                
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            print("Scheduler stopped")
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
