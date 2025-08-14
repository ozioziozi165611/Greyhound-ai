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

async def research_analysis_only():
    """Generate research analysis without sending to Discord - for testing and verification"""
    perth_now = datetime.now(PERTH_TZ)
    target_date_str = perth_now.strftime("%B %d, %Y")
    target_date_search = perth_now.strftime("%Y-%m-%d")
    current_time_perth = perth_now.strftime("%H:%M AWST")
    
    print(f"Generating research analysis for {target_date_str} at {current_time_perth}")
    print(f"DEBUG: Perth date: {target_date_search}, Perth time: {current_time_perth}")
    
    # Get learning insights
    learning_insights = get_learning_enhanced_prompt()
    
    # Analyze today's greyhound races only - research mode
    research_result = await analyze_greyhound_racing_day(target_date_str, target_date_search, current_time_perth, learning_insights)
    
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

async def analyze_greyhound_racing_day(target_date_str, target_date_search, current_time_perth, learning_insights):
    """Analyze TODAY only (Perth date) with comprehensive greyhound analysis"""
    
    # Expert greyhound racing analyst prompt with strict data source requirements
    main_prompt = f"""You are an expert greyhound racing analyst and betting strategist. I will provide, or you will source, official race form data for all races scheduled for {target_date_str}.

Current Time: {current_time_perth} (Perth/AWST)
Target Analysis: greyhound races for {target_date_str} ONLY - RACES THAT HAVEN'T RUN YET

{learning_insights}

COMPREHENSIVE ANALYSIS PROCESS (MANDATORY):

DEEP RESEARCH PLAN FOR GREYHOUND RACING ANALYSIS:

**Step 1: Identify All Australian Greyhound Meetings**
MUST COMPLETE: Get a complete list of all greyhound meetings scheduled across every state in Australia for {target_date_str}. This ensures no race is missed. USE THESE EXACT SEARCH TERMS:
- Search: "TAB greyhound racing today Wednesday"
- Search: "greyhound racing today Australia live"  
- Search: "thedogs.com.au race cards today"
- Search: "greyhound race meetings tonight Australia"
- Search: "live greyhound racing Wednesday Australia"
- Search: "greyhound racing August 14 Australia"
- Search: "Australian greyhound meetings Wednesday night"
- Search: "tab.com.au greyhound racing Wednesday"
- Search: "sportsbet greyhound racing today"
- Search: "racing.com greyhound meetings today"

CRITICAL: Wednesday is a major greyhound racing day in Australia. If initial searches don't find meetings, try these backup searches:
- Search: "greyhound racing venues Australia Wednesday evening"
- Search: "Gosford Murray Bridge Townsville greyhound racing Wednesday"
- Search: "Australian greyhound tracks racing tonight"

**Step 2: Gather Comprehensive Race Form Data**
MUST COMPLETE: For each meeting identified in Step 1, perform targeted searches to collect detailed form data for ALL runners:
- Search: "[Track Name] greyhound race card and form guide {target_date_str}"
- Search: "greyhound form guide for all races [Track Name] {target_date_search}"
- Search: "TheDogs.com.au race cards {target_date_search}"
- Search: "greyhound sectional times and form {target_date_search}"
- Repeat this process for EVERY track identified (e.g., Gosford, Murray Bridge, Townsville, Bulli, etc.)

**Step 3: Check for Real-Time Updates and Track Conditions**
MUST COMPLETE: Critical step to get the most up-to-date information that can influence race outcomes:
- Search: "[Track Name] greyhound scratchings and track report {target_date_str}"
- Search: "weather forecast for [Track Name] on {target_date_str}"
- Search: "track bias report [Track Name] greyhound racing"
- Search: "greyhound racing scratchings Australia {target_date_search}"
- Repeat for EVERY track from Step 1

**Step 4: Fetch Current Market Odds**
MUST COMPLETE: To evaluate betting value, collect the latest market odds and track fluctuations:
- Search: "live greyhound racing odds Australia {target_date_str}"
- Search: "greyhound betting odds comparison {target_date_str}"
- Search: "TAB greyhound odds {target_date_str}"
- Search: "Sportsbet greyhound racing odds {target_date_search}"

**Step 5: Perform Data-Driven Analysis and Simulation**
MUST COMPLETE: After gathering all data, perform internal analysis using:

(1) Weighted Model Application with specified percentages:
- Early speed & acceleration (30%)
- Consistency in recent form (20%)
- Win/place strike rate (15%)
- Track & distance suitability (15%)
- Box draw advantage/disadvantage (10%)
- Trainer performance (5%)
- Market value (5%)

(2) Monte Carlo Simulations: Run at least 1,000 simulations per race to estimate win and place probabilities for each runner.

(3) Tip Identification: Based on model and simulations, identify top 5 betting opportunities with:
- Strong winning probabilities (>35%) OR high place probabilities (>65%)
- Minimum market odds of $2.00 (avoid short-priced favorites)
- Excellent value compared to current market odds (minimum 20% edge)
- Focus on value selections, not just form favorites

For each race, collect and synthesize all available data points, including: runner statistics (career, track & distance records), trainer and runner strike rates, early speed and sectional times, run styles, recent form (last 4-6 starts), historical head-to-head matchups, and race grade changes.

Identify and incorporate any late scratchings, changes in weather, or track conditions and note how these may influence race outcomes, particularly regarding track bias.

For each of the top 5 tips, provide a detailed breakdown including: the race number and track, the dog's name and box number, the estimated win and place probabilities, current market odds and calculated fair odds, the recommended bet type (Win, Each-Way, or Place), and a detailed justification based on the analyzed data.

Format the final output as a report that includes a summary table of the top 5 tips and a detailed, data-driven rationale for each selection.

APPROVED DATA SOURCES (MANDATORY):

✅ TheDogs.com.au — Sectionals, early speed, box stats, career/track/distance performance, trainer stats, comments.
✅ Watchdog.grv.org.au — VIC form, box draw records, odds, historical results.
✅ TAB.com.au / Sportsbet.com.au — Market odds, fluctuations, tote vs fixed prices.
✅ Racing.com / Racing Queensland / RWWA — Track bias, scratchings, weather conditions.
✅ Punters.com.au (Form Guide) — Cross-check of stats and form.

❌ DO NOT USE:
- Betting forums, Facebook groups, "hot tip" chats
- Generic sports betting aggregator sites (Oddschecker-style)
- YouTube or casual race preview channels without data
- Non-official blogs or scraper sites
- AI tip bots without transparent metrics

CRITICAL TIMING REQUIREMENTS:
- Current time is {current_time_perth} AWST
- ONLY analyze races that start AFTER this time
- Exclude any races that have already run or are currently running
- Cross-check race start times against current Perth time

SELECTION CRITERIA FOR TOP 5 TIPS:
- Win probability >35% OR place probability >65%
- Minimum odds of $2.00 (no short-priced favorites under $2.00)
- Strong value compared to market odds (minimum 20% edge)
- Low variance in performance unless value is extreme (>30% edge)
- Races must not have started yet
- Focus on genuine value bets, not short-priced favorites

OUTPUT FORMAT:

**🐕 TOP GREYHOUND SELECTIONS FOR {target_date_str}:**

| **Race (Track)** | **Greyhound (Box)** | **Est. Win%** | **Est. Place%** | **Market Odds** | **Fair Odds** | **Potential Value** | **Bet Type** | **Units** |
|------------------|---------------------|---------------|-----------------|-----------------|---------------|-------------------|--------------|-----------|
| Race X (Track)   | **Dog Name** (Box X) | XX%          | XX%             | $X.XX           | $X.XX         | +XX%              | Win/EW       | 0.5-1.5   |

**DETAILED SELECTIONS:**

🐕 **DOG NAME** | Race X | Track Name
📦 **Box:** X | ⏰ **Time:** XX:XX AWST | 📏 **Distance:** XXXm
🎯 **Win:** XX% | 🎲 **Place:** XX% | 💰 **Odds:** $X.XX | 💎 **Fair:** $X.XX | 📈 **Edge:** +XX%
🏆 **Bet:** Win/Each-Way | 💵 **Stake:** X.X units
💡 **Why:** [Brief analysis - early speed, form, value reason]

---

IMPORTANT: ONLY PROVIDE THE FINAL TIPS IN THIS FORMAT. DO NOT include any analysis steps, research process, data sources mentioned, or methodology explanations. Users only want to see the clean tip selections.

**STEP 4: CURRENT MARKET ODDS ASSESSMENT**
[Market odds collected from approved sources]
[Odds fluctuation patterns noted]

**STEP 5: DATA-DRIVEN ANALYSIS RESULTS**

**SUMMARY TABLE - TOP 5 BETTING OPPORTUNITIES:**

| Race | Track | Dog Name | Box | Win% | Place% | Market | Fair | Potential Value | Bet Type | Units |
|------|-------|----------|-----|------|--------|--------|------|-------|----------|-------|
| R1   | XXXX  | DOG NAME | X   | XX%  | XX%    | $X.XX  | $X.XX| +XX%  | Win/EW   | 0.5-1.5 |

**DETAILED ANALYSIS:**

🐕 **DOG NAME** | Track Name | Race X
⏰ **Race Time:** XX:XX AWST | 📏 **Distance:** XXXm | 📦 **Box:** X
🎯 **Win Probability:** XX% | 🎲 **Place Probability:** XX%
💰 **Market Odds:** $X.XX | � **Fair Odds:** $X.XX | � **Potential Value:** XX%
🏆 **Bet Type:** [Win/Each-Way/Place] | 💵 **Stake:** [0.5-1.5 units]

� **Monte Carlo Results:** [Win %: XX%, Place %: XX%, Variance: XX]
📈 **Key Metrics:**
- Early Speed Rank: X/X (sectional: XX.XX)
- Form Rating: XX/100 (last 5 starts)
- Track/Distance: XX% strike rate (XX starts)
- Box Draw: +XX% advantage
- Trainer Form: XX% last 30 days

� **Analysis:** [Detailed reasoning covering early speed advantage, form trends, track suitability, market value, risk factors]

🔍 **Data Verification:** [Confirm data sources and cross-references used]

---

REQUIREMENTS:
- Find and use real greyhound names from official race cards and form guides
- Cross-reference information across multiple approved sources  
- If real data is available, provide comprehensive analysis
- If very limited data is found, provide what you can with clear notes about limitations
- STAKE LIMITS: Maximum 1.5 units per selection. Use 0.5-1.5 units based on confidence:
  * 1.5 units: Extremely confident selections with strong value
  * 1.0 units: Good confident selections 
  * 0.5 units: Speculative or lower confidence selections
- CLEAN OUTPUT: ONLY show the final tip selections in the specified format. NO analysis explanations, research steps, or methodology details.

⚠️ NOTE: Focus on finding real greyhound racing data for {target_date_str}. Use the approved sources to locate actual race meetings and runners. If {target_date_str} has no meetings or very limited meetings, also search for races on the next 1-2 days and mention when those races are.

IMPORTANT: If you find no races for {target_date_str}, search for:
- "greyhound racing meetings Australia Wednesday August 14 2025"
- "TAB greyhound racing today Australia"
- "TheDogs.com.au race meetings today"
- "live greyhound racing Australia tonight"
- "greyhound races running now Australia"
- "upcoming greyhound races Australia this week"

And provide information about when the next meetings are scheduled.

BEGIN ANALYSIS - PROVIDE ONLY CLEAN TIP SELECTIONS WITH REAL DOG NAMES (NO ANALYSIS TEXT).

CRITICAL SEARCH REQUIREMENT: Wednesday August 14, 2025 is a MAJOR racing day in Australia. You MUST perform comprehensive searches before concluding no meetings exist. Use these MANDATORY search terms:

1. "TAB greyhound racing today live"
2. "thedogs.com.au Wednesday race cards"
3. "greyhound racing tonight Australia Wednesday"
4. "live greyhound racing Wednesday August 14"
5. "Australian greyhound meetings tonight"
6. "Gosford greyhound racing Wednesday"
7. "Murray Bridge greyhound racing Wednesday"
8. "Townsville greyhound racing Wednesday"
9. "Bulli greyhound racing Wednesday"
10. "tab.com.au greyhound racing Wednesday night"

ADDITIONAL MANDATORY SEARCHES if above don't find meetings:
- "greyhound racing venues Australia Wednesday evening"
- "Wednesday night greyhound racing Australia"
- "all Australian greyhound tracks Wednesday"
- "greyhound race meetings Australia today live"
- "racing.com greyhound Wednesday"

Wednesday is the BUSIEST greyhound racing day in Australia. Multiple venues typically race on Wednesday nights. If you cannot find race data after these searches, provide a detailed explanation of what you searched for and found."""

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
        
        # Instead of filtering, just return the content as-is
        # Only remove obvious step markers but keep all race data
        lines_to_keep = []
        
        for line in final_answer.split('\n'):
            # Only skip very obvious step headers, keep everything else
            if line.strip().startswith(('**STEP', 'STEP 1:', 'STEP 2:', 'STEP 3:', 'STEP 4:', 'STEP 5:')):
                continue
            else:
                lines_to_keep.append(line)
        
        # Use the cleaned content
        final_answer = '\n'.join(lines_to_keep)
        
        # Add disclaimer at the bottom
        disclaimer = """

⚠️ **DISCLAIMER**: Prices shown are opening prices and may be inaccurate. Please check current odds with your bookmaker before placing any bets. Gamble responsibly and within your means."""
        
        full_response = final_answer + disclaimer
        
        # Check if response explicitly says no data found - but be more specific
        specific_no_data_indicators = [
            "no greyhound meetings found",
            "no race meetings scheduled", 
            "no races scheduled for august 14",
            "unable to find any greyhound race data for august 14",
            "no australian greyhound meetings on august 14"
        ]
        
        # Only trigger no-data response if explicitly stated AND content is very short
        explicit_no_data = any(indicator.lower() in full_response.lower() for indicator in specific_no_data_indicators)
        
        # Check if response is mostly just the disclaimer (indicating no real content)
        content_without_disclaimer = full_response.replace(disclaimer, "").strip()
        is_mostly_empty = len(content_without_disclaimer) < 50  # Much lower threshold
        
        # Be more conservative - only show no data message if content is truly empty
        if is_mostly_empty:
            return f"""🐕 Greyhound Racing Tips - Daily Analysis

SEARCH ISSUE DETECTED FOR {target_date_str.upper()}

The analysis system was unable to locate definitive greyhound race data for {target_date_str}. However, since Wednesday is typically a major racing day in Australia, this may be a temporary search issue.

🔍 **POSSIBLE CAUSES:**
- Website access limitations
- Race data not yet published 
- Search timing issues

� **RECOMMENDED ACTION:**
- Check TAB.com.au or TheDogs.com.au directly
- Verify if races are running tonight
- Try running the analysis again in 30 minutes

I will continue monitoring for race meetings and provide analysis when data becomes available.

⚠️ **DISCLAIMER**: Please check with official racing websites for the most current meeting schedules. Gamble responsibly and within your means."""
        
        # If we have any substantial content, return it even if it seems incomplete
        return full_response
        
    except asyncio.TimeoutError:
        return f"""⚠️ **ANALYSIS TIMEOUT**

The comprehensive analysis took longer than expected (10+ minutes). This can happen during peak times or when conducting extensive web research.

🔄 **RECOMMENDED ACTIONS:**
- Wait 10-15 minutes and try again
- Check if there are fewer race meetings today
- The bot will retry automatically at the next scheduled time

⏰ **NEXT SCHEDULED RUN:** 7:00 PM AWST for evening analysis

⚠️ **DISCLAIMER**: Please check with official racing websites for current race information. Gamble responsibly and within your means."""
    except Exception as e:
        error_details = str(e)
        if "timeout" in error_details.lower():
            return f"""⚠️ **ANALYSIS TIMEOUT**

The analysis exceeded the time limit while gathering comprehensive race data.

🔄 **RECOMMENDED ACTIONS:**
- The analysis will retry automatically
- Check back in 30 minutes for fresh tips

Error details: {error_details[:100]}...

⚠️ **DISCLAIMER**: Please check with official racing websites for current race information."""
        else:
            return f"⚠️ Error generating greyhound tips: {error_details}"

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
    print(f"🕐 System time: {system_now.strftime('%Y-%m-%d %H:%M')}")
    print(f"🇦🇺 Perth time: {perth_now.strftime('%Y-%m-%d %H:%M AWST')}")
    print(f"📅 Target date: {perth_now.strftime('%B %d, %Y')} ({perth_now.strftime('%Y-%m-%d')})")
    print(f"📁 Data directory: {DATA_DIR}")
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