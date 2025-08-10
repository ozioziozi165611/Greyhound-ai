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
DATA_DIR = os.getenv('DATA_DIR', '/tmp/data')  # Default to /tmp/data for Railway

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

# Configure generation with deep thinking AND real web search (like working horse bot)
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
    
    print(f"Generating fresh greyhound tips for {target_date_str} at {current_time_perth}")
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
    """Analyze TODAY only (Perth date) with comprehensive greyhound analysis - using successful horse bot approach"""
    
    # Enhanced prompt with MANDATORY web search for REAL greyhound data, today only - based on working horse bot
    main_prompt = f"""🌐 LIVE WEB SEARCH REQUIRED - REAL AUSTRALIAN GREYHOUND RACING DATA (TODAY ONLY)

Current Time: {current_time_perth} (Perth/AWST)
Target Analysis: today's greyhound races for {target_date_str} ONLY

{learning_insights}

You MUST use your web search capabilities to find REAL greyhound racing information for TODAY ({target_date_str}).

MANDATORY COMPREHENSIVE WEB SEARCHES TO PERFORM:

📊 GREYHOUND RACE CARDS & BASIC DATA:
1. Search: "Australian greyhound racing {target_date_search} race cards TheDogs.com.au"
2. Search: "Wentworth Park Sandown Cannington Angle Park {target_date_str} greyhound meetings"
3. Search: "NSW VIC QLD SA WA greyhound racing {target_date_str} full cards"
4. Search: "TheDogs.com.au {target_date_search} complete greyhound race cards"
5. Search: "TAB greyhound racing Australia {target_date_str} all meetings times boxes"

⚡ GREYHOUND FORM & SECTIONALS DATA:
6. Search: "Australian greyhound form guide {target_date_search} sectional times"
7. Search: "greyhound racing sectionals Australia {target_date_str} first split times"
8. Search: "fasttrack.grv.org.au form guide {target_date_search}"
9. Search: "punters.com.au greyhound form guide {target_date_str}"
10. Search: "greyhound racing form Australia {target_date_search}"

🐕 TRAINER & KENNEL STATS:
11. Search: "Australian greyhound trainer statistics {target_date_str} win rates last 30 days"
12. Search: "greyhound trainer statistics Australia racing {target_date_search} strike rates"
13. Search: "greyhound racing Australia trainer form current season"

💬 COMMENTS & TRIALS:
14. Search: "greyhound racing trials Australia recent {target_date_search} results"
15. Search: "Australian greyhound racing media tips {target_date_str} trainer comments"
16. Search: "greyhound racing stable comments Australia {target_date_search}"
17. Search: "greyhound racing analysts tips Australia {target_date_str}"

🌦️ TRACK CONDITIONS & BREEDING:
18. Search: "Australian greyhound race track conditions {target_date_str} fast good slow"
19. Search: "greyhound breeding sire dam track conditions Australia"
20. Search: "greyhound track bias Australia racing {target_date_str} patterns"

📈 ODDS & MARKET DATA:
21. Search: "TAB greyhound odds Australia {target_date_str} current betting markets"
22. Search: "sportsbet greyhound racing odds Australia {target_date_search}"
23. Search: "bet365 greyhound racing Australia {target_date_str}"

🔍 SCRATCHINGS & LATE MAIL:
24. Search: "greyhound racing scratchings Australia {target_date_search} late withdrawals"
25. Search: "Australian greyhound racing late mail {target_date_str} insider tips"

CURRENT TIME FILTERING:
- Use AWST times; ONLY include races that haven't started yet
- Check race start times and exclude completed races

🧠 ULTIMATE GREYHOUND RACING AI TASK PROMPT
"GREYHOUND PUNTING MODEL – AUSTRALIAN WIN-ONLY GREYHOUND RACING TIPS ENGINE"

🎯 OBJECTIVE:
Use COMPREHENSIVE web search across multiple data sources to find Australian greyhound races for {target_date_str}, then apply enhanced greyhound analysis to identify strong win opportunities.

🚨 PRIORITY MANDATE: Focus on finding greyhounds that show strong form indicators, trainer/kennel combinations, or market confidence. Use AVAILABLE data effectively - race cards, form guides, and basic information are sufficient for analysis. The goal is to identify genuine betting opportunities from publicly available racing information.

CRITICAL ANALYSIS APPROACH:
- You MUST search extensively across multiple greyhound racing websites
- Cross-reference data from TheDogs.com.au, fasttrack.grv.org.au, TAB, punters.com.au, and greyhound racing media
- Use race cards, form guides, and available statistical data for analysis
- ACCEPT standard racing information as valid for analysis (race cards, form, trainer stats, etc.)
- Leverage trainer/kennel strike rates and historical performance data
- Consider available market information and form patterns
- Apply breeding analysis and track condition factors where available
- Do NOT require "real-time" or "live" data - standard race cards and form guides are sufficient
- ABSOLUTELY NO FICTIONAL GREYHOUND NAMES - only real greyhounds from official sources

✅ GREYHOUND ANALYSIS CRITERIA:

🔥 Speed & Sectionals (Key Factors)
- Recent sectional times and first split performance
- Best time at distance vs field
- Track record and personal bests
- Recent trial performance

🗣️ Comments & Kennel Signals
- Trainer/kennel comments about readiness
- Media tips and stable confidence
- Recent work reports

🌦️ Track & Surface Factors
- Performance on today's track condition
- Track bias and running patterns
- Box draw advantages/disadvantages

🏃 Form & Class
- Recent race performance
- Grade progression
- Wins against similar opposition
- Consistency factors

⚖️ Box Draw & Running Style
- Box draw suitability for running style
- Track position preferences
- Early speed vs finishing kick

🧪 Trainer & Kennel Form
- Trainer strike rate and recent form
- Kennel performance statistics
- Historical venue performance

MINIMUM SELECTION CRITERIA:
- USE available race cards, form guides, and statistical data from official greyhound racing websites
- INCLUDE real greyhounds with real names from official race cards for races that haven't run yet
- Cross-verify greyhound names and basic information across racing websites  
- STANDARD race card information and form guides are SUFFICIENT for analysis
- Do NOT require "real-time" or "live" data - published race cards and form data are adequate
- Maximum 5 selections total (WIN TIPS ONLY)
- Each selection must be backed by available data from official racing sources
- PROCEED with analysis if you find legitimate race cards and greyhound names, even if detailed sectionals unavailable

📋 REQUIRED OUTPUT FORMAT FOR DISCORD (AWST times):

**WEB SEARCH RESULTS:**
[List what REAL greyhound racing data you found from your web searches]
[Specify which races are still to run vs completed]

**REAL SELECTIONS:**
For each qualifying REAL greyhound from races yet to run:

🐕 **GREYHOUND NAME** | Track Name | Race X
⏰ **Race Time:** XX:XX AWST | 📏 **Distance:** XXXm
🎯 **Composite Score:** XX/25 | 💰 **Win Odds:** $X.XX | 📦 **Box:** X
🌦️ **Track:** Condition | 📊 **Analysis Score:** X.X/10
✅ **Status:** Still to run | 🏆 **BET TYPE:** WIN

💡 **Analysis:** [100-word analysis covering: Why its Best Time at this trip is superior, How its First-Sectional Speed and Box Draw align, Relevant Form notes (class drop, trainer heat, spell), Race Dynamics summary (pace forecast, congestion risk), Any public vet/injury alerts or fitness notes. Remove all links from analysis make it easy for people to understand.]
🔍 **Sources:** [Official websites where data was verified]

---

ANTI-FICTION REQUIREMENTS:
- Do NOT create fictional greyhound names like "RAPID FIRE", "BOXCAR BULLET", "RAILWAY RAMPAGE"
- Do NOT create fictional race times or track names
- Do NOT create fictional trainer names
- If you find race cards with real greyhound names, PROCEED with analysis using available data
- If you cannot find any race cards or greyhound names, then state "No race card data found for {target_date_str}"
- REAL NAMES ONLY - but use standard race card and form guide information for analysis
- ACCEPTABLE DATA: Official race cards, published form guides, trainer statistics, track information
- NOT REQUIRED: Live odds, real-time sectionals, minute-by-minute updates

BEGIN COMPREHENSIVE WEB SEARCH FOR AUSTRALIAN GREYHOUND RACING DATA FOR {target_date_str} (TODAY ONLY) - USE AVAILABLE RACE CARDS AND FORM GUIDES FOR ANALYSIS NOW."""

    try:
        # Generate greyhound tips using REAL web search + deep thinking (like working horse bot)
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
                # Skip thoughts - don't include them in output
                continue
            else:
                final_answer += part.text
        
        # Clean up any remaining thought markers in the final answer
        lines = final_answer.split('\n')
        cleaned_lines = []
        skip_line = False
        
        for line in lines:
            # Skip lines that start with thought markers
            if line.strip().startswith('🤔 Deep Analysis:'):
                skip_line = True
                continue
            # Skip empty lines after thoughts
            elif skip_line and line.strip() == '':
                continue
            # Found content after thoughts, stop skipping
            elif skip_line and line.strip():
                skip_line = False
                cleaned_lines.append(line)
            # Normal content line
            elif not skip_line:
                cleaned_lines.append(line)
        
        final_answer = '\n'.join(cleaned_lines)
        
        # Add disclaimer at the bottom
        disclaimer = """

⚠️ **DISCLAIMER**: Prices shown are opening prices and may be inaccurate. Please check current odds with your bookmaker before placing any bets. Gamble responsibly and within your means."""
        
        full_response = final_answer + disclaimer
        
        # Check if no races were found for today
        if "no greyhound race" in full_response.lower() or "no verifiable greyhound race data" in full_response.lower():
            return f"ℹ️ **NO RACES TODAY**: {full_response}"
        
        # Check for common fictional indicators (but be less restrictive than before)
        suspicious_patterns = [
            "rapid fire", "boxcar bullet", "railway rampage"
        ]
        
        suspicious_count = sum(1 for pattern in suspicious_patterns if pattern.lower() in full_response.lower())
        
        # Only reject if multiple suspicious patterns detected
        if suspicious_count >= 2:
            return f"⚠️ **FICTIONAL DATA DETECTED**: The AI may have generated fake greyhound names. Please verify selections against official greyhound racing websites before using."
        
        return full_response
        
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
        
        # Check if we're starting in schedule mode - don't generate tips immediately
        perth_now = datetime.now(PERTH_TZ)
        current_time = perth_now.time()
        
        if current_time < dtime(7, 0):
            print(f"Schedule mode started before 7AM ({current_time.strftime('%H:%M')}). Waiting until 7AM for first tips generation.")
        elif current_time < dtime(19, 0):
            print(f"Schedule mode started after 7AM but before 7PM ({current_time.strftime('%H:%M')}). Tips already generated today. Waiting until 7PM for results analysis, then 7AM tomorrow for next tips.")
            # Set today as already run for morning to prevent duplicate tips
            last_run_date_morning = perth_now.date()
        else:
            print(f"Schedule mode started after 7PM ({current_time.strftime('%H:%M')}). Both runs already completed today. Waiting until 7AM tomorrow for next tips.")
            # Set today as already run for both morning and evening
            last_run_date_morning = perth_now.date()
            last_run_date_evening = perth_now.date()
        
        try:
            while True:
                now_perth = datetime.now(PERTH_TZ)
                today = now_perth.date()
                current_time = now_perth.time()
                
                # 7:00 AM run (only if we haven't run today)
                if current_time >= dtime(7, 0) and (last_run_date_morning != today):
                    print("Triggering 7AM greyhound tips run...")
                    tips = await generate_greyhound_tips()
                    await send_webhook_message(tips)
                    last_run_date_morning = today
                
                # 7:00 PM run (only if we haven't run today)
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
