import os
import openai
from pymongo import MongoClient
from datetime import datetime
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
# Load environment variables
mongopass = os.getenv("MONGOPASS")
openaipass = os.getenv("OPENAI")

# MongoDB Connection
uri = f"mongodb+srv://mshvorin:{mongopass}@reminders.up5mauj.mongodb.net/?retryWrites=true&w=majority&appName=reminders"
client = MongoClient(uri)

# Initialize OpenAI
openai.api_key = openaipass

# Access the 'activities' collection in the 'reminders' database
db = client.reminders.activities

# Initialize Discord Bot
bot = commands.Bot(command_prefix='~', help_command=None, intents=discord.Intents.all())

print("v2")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command(name='addactivity')
async def add_activity(ctx, date_str: str, *, activity: str):
    user_id = ctx.author.id
    try:
        due_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        await ctx.send("Error: Date format should be YYYY-MM-DD.")
        return

    # Convert due_date to datetime.datetime
    due_date_datetime = datetime.combine(due_date, datetime.min.time())

    # Insert the activity document into the MongoDB collection
    activity_doc = {
        "user_id": user_id,
        "activity": activity,
        "completed": False,
        "due_date": due_date_datetime  # Insert as datetime.datetime
    }

    db.insert_one(activity_doc)
    await ctx.send(f'Activity "{activity}" added successfully with due date {due_date}!')

@bot.command(name='complete')
async def complete_activity(ctx, *, activity: str):
    user_id = ctx.author.id

    # Update the completed status of the activity document in MongoDB
    result = db.update_one(
        {"user_id": user_id, "activity": activity, "completed": False},
        {"$set": {"completed": True}}
    )

    if result.modified_count > 0:
        await ctx.send(f'Activity "{activity}" marked as completed!')
    else:
        await ctx.send(f'Error: Activity "{activity}" not found or already completed.')

@bot.command(name='clear')
async def clear_activities(ctx):
    user_id = ctx.author.id

    # Send warning message and await confirmation
    warning_message = (
        "**⚠️ Warning: This action will fully clear all your activities, both pending and completed.**\n"
        "This will also reset your position on the leaderboard, and **this action cannot be undone.**\n"
        "If you're sure you want to proceed, type `confirm` to continue, or `cancel` to stop."
    )
    await ctx.send(warning_message)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['confirm', 'cancel']

    # Wait for the user's response
    try:
        confirmation = await bot.wait_for('message', check=check, timeout=30.0)  # 30-second timeout
        if confirmation.content.lower() == 'confirm':
            # Delete all activities for the user from MongoDB
            result = db.delete_many({"user_id": user_id})
            await ctx.send('✅ All your activities have been fully cleared, and your leaderboard progress has been reset.')
        else:
            await ctx.send('❌ Activity clearing has been canceled.')
    except TimeoutError:
        await ctx.send('⏳ Time out! Activity clearing request has been canceled.')


@bot.command(name='viewactive')
async def view_active(ctx):
    user_id = ctx.author.id

    # Retrieve only active (pending) activities for the user from MongoDB
    activities = db.find({"user_id": user_id, "completed": False})

    activities_info = "\n".join(
        [f"• {activity['activity']} - Due on {activity['due_date'].strftime('%Y-%m-%d')}"
         for activity in activities]
    )

    if activities_info:
        await ctx.send(f"**Your Pending Activities:**\n{activities_info}")
    else:
        await ctx.send('No pending activities found.')


@bot.command(name='viewcompleted')
async def view_completed(ctx):
    user_id = ctx.author.id

    # Retrieve only completed activities for the user from MongoDB
    activities = db.find({"user_id": user_id, "completed": True})

    activities_info = "\n".join(
        [f"• {activity['activity']} - Completed on {activity['due_date'].strftime('%Y-%m-%d')}"
         for activity in activities]
    )

    if activities_info:
        await ctx.send(f"**Your Completed Activities:**\n{activities_info}")
    else:
        await ctx.send('No completed activities found.')


@bot.command(name='help')
async def help(ctx):
    help_message = """
    **📋 Available Commands:**

    **Activities Management:**
    - `~addactivity <YYYY-MM-DD> <Activity Description>`  
      ➡️ *Add a new activity with a specific due date.*  
      Example: `~addactivity 2024-10-01 Finish report.`

    - `~complete <Activity Description>`  
      ➡️ *Mark an activity as completed.*  
      Example: `~complete Finish report.`

    - `~viewactive`  
      ➡️ *View all your current pending activities.*

    - `~viewcompleted`  
      ➡️ *View all your completed activities.*

    - `~clear`  
      ➡️ *Clear all your activities (both pending and completed). This will also reset your leaderboard progress.*  
      **⚠️ Warning:** You will be asked to confirm this action, as it cannot be undone.

    **Fun and AI Features:**
    - `~ask <Your Question>`  
      ➡️ *Ask any question and get an AI-generated response powered by OpenAI.*  
      Example: `~ask What is the meaning of life?`

    **Leaderboard:**
    - `~leaderboard`  
      ➡️ *View the leaderboard of users with the most completed activities.*

    **Bot Assistance:**
    - `~help`  
      ➡️ *Show this help message.*

    **Command Usage Quick Reference:**
    - To add an activity: `~addactivity 2024-10-01 Finish report.`
    - To mark an activity as complete: `~complete Finish report.`
    - To view your pending tasks: `~viewactive`
    - To view your completed tasks: `~viewcompleted`
    - To clear all tasks: `~clear`
    - To ask an AI question: `~ask What's the weather like today?`
    - To see the leaderboard: `~leaderboard`
    - To see this help message: `~help`
    """
    await ctx.send(help_message)


@bot.command(name='ask')
async def ask_question(ctx, *, question: str):
    try:
        # Generate a response using the chat-based model
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question},
            ],
            max_tokens=500
        )

        # Extract and send the generated response
        generated_response = completion.choices[0].message.content  # Access message content as an attribute
        await ctx.send(generated_response)

    except Exception as e:
        # Handle any errors
        await ctx.send(f"An error occurred: {str(e)}")


# Background task to send daily reminders for pending tasks
@tasks.loop(seconds=86400)  # 86400 seconds = 24 hours
async def send_task_reminders():
    users_with_pending_tasks = db.find({"completed": False}).distinct("user_id")

    for user_id in users_with_pending_tasks:
        user = bot.get_user(user_id)
        if user:
            pending_tasks = db.find({"user_id": user_id, "completed": False})
            tasks_list = ", ".join(task["activity"] for task in pending_tasks)
            await user.send(f"Reminder: You have pending tasks: {tasks_list}")

@bot.command(name='leaderboard')
async def leaderboard(ctx):
    # Retrieve top 10 users with completed activities from MongoDB
    leaderboard = list(db.aggregate([
        {"$match": {"completed": True}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]))

    leaderboard_msg = "Leaderboard:\n"
    for index, entry in enumerate(leaderboard, start=1):
        user = bot.get_user(entry["_id"])
        leaderboard_msg += f'{index}. {user.name if user else "Unknown User"} - {entry["count"]} activities completed\n'

    await ctx.send(leaderboard_msg)

# Start the background task when the bot is ready
@bot.event
async def on_ready():
    if not send_task_reminders.is_running():
        send_task_reminders.start()

# Run the bot
disc = os.getenv("DISCORD_TOKEN").strip()
if not disc:
    raise ValueError("The DISCORD_TOKEN environment variable is not set or is empty.")
bot.run(disc)