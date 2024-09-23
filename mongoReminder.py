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
disc = os.getenv("DISC")



# MongoDB Connection
uri = f"mongodb+srv://mshvorin:{mongopass}@reminders.up5mauj.mongodb.net/?retryWrites=true&w=majority&appName=reminders"
client = MongoClient(uri)

# Initialize OpenAI
openai.api_key = openaipass

# Access the 'activities' collection in the 'reminders' database
db = client.reminders.activities

# Initialize Discord Bot
bot = commands.Bot(command_prefix='~', intents=discord.Intents.all())

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
async def clear_assignments(ctx):
    user_id = ctx.author.id

    # Delete all assignments for the user from MongoDB
    result = db.delete_many({"user_id": user_id})

    await ctx.send('All your assignments have been cleared successfully!')

@bot.command(name='viewactive')
async def view_activities(ctx):
    user_id = ctx.author.id

    # Retrieve all activities for the user from MongoDB
    activities = db.find({"user_id": user_id})

    activities_info = "\n".join(
        [f"• {activity['activity']}: {'Completed' if activity['completed'] else 'Pending'}"
         for activity in activities]
    )

    if activities_info:
        await ctx.send(f"**Your Activities:**\n{activities_info}")
    else:
        await ctx.send('No activities found.')

@bot.command(name='helppls')
async def helpFunc(ctx):
    help_message = """
    **Available Commands:**
    - `~addactivity YYYY-MM-DD Activity Description`: Add a new activity with a due date.
    - `~complete Activity Description`: Mark a specific activity as completed.
    - `~clear`: Clear your completed assignments.
    - `~leaderboard`: View the leaderboard of completed activities.
    - `~helppls`: Show this help message.

    **Command Usage:**
    - To add an activity: `~addactivity 2023-12-31 homeworkAssignment.`
    - To complete an activity: `~complete homeworkAssignment.`
    - To clear your completed assignments: `~clear`
    - To view the leaderboard: `~leaderboard`
    - To view this help message: `~helppls`
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
disc = os.getenv("DISC")
bot.run(disc)