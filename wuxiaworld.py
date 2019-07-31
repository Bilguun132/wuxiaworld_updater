

import requests
from bs4 import BeautifulSoup
import json
import pymongo
import threading
import time
import logging
import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters, RegexHandler
from uuid import uuid4
from datetime import datetime
import os


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

client = pymongo.MongoClient("mongodb://localhost:27019/")
wuxiaworlddb = client["wuxiaworldDB"]
novels_collection = wuxiaworlddb.novels
users_collection = wuxiaworlddb.users
users_collection.create_index("chat_id", unique=True)

BASE_URL = "https://www.wuxiaworld.com"
UPDATES_URL = "https://www.wuxiaworld.com/updates"
UPDATE_INTERVAL = 60
TELEGRAM_TOKEN = os.getenv('WUXIAWORLD_BOT_TOKEN')
print('telegram token is ', TELEGRAM_TOKEN)
CHOOSING, TYPING_REPLY, TYPING_CHOICE = range(3)
bot = telegram.Bot(token=TELEGRAM_TOKEN)

LAST_CHECKED = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

class WuxiaUpdateThread(object):
    """ Threading example class
    The run() method will be started and it will run in the background
    until the application exits.
    """

    def __init__(self, interval=UPDATE_INTERVAL):
        """ Constructor
        :type interval: int
        :param interval: Check interval, in seconds
        """
        self.interval = interval

        thread = threading.Thread(target=self.run, args=())
        thread.daemon = True                            # Daemonize thread
        thread.start()                                  # Start the execution

    def run(self):
        """ Method that runs forever """
        while True:
            new_novels = populate_novels()
            for novel in new_novels:
                existing_record = novels_collection.find_one(
                    {'name': novel['name']})
                if novel['chapterUrl'] == existing_record['chapterUrl']:
                    print('No need to update subscribers for ', novel['name'])
                else:
                    print('New chapter found for {}'.format(
                        novel))
                    novels_collection.find_one_and_update({'name':novel["name"]}, {'$set': {'latestChapter': novel["latestChapter"], 'chapterUrl': novel["chapterUrl"]}})
                    novel = novels_collection.find_one({'name':novel["name"], 'subscribers': {'$exists': True}})
                    if novel is not None:
                        print(novel)
                        for subscriber in novel["subscribers"]:
                            print("Found a subscriber: {}".format(subscriber))
                            bot.send_message(chat_id=subscriber, 
                 text="*{}-{}({})*\n ".format(novel["name"], novel["latestChapter"], novel["chapterUrl"]), 
                 parse_mode=telegram.ParseMode.MARKDOWN)
            logging.info('Updating again in %s seconds.', self.interval)
            time.sleep(self.interval)


def populate_novels():
    global LAST_CHECKED
    LAST_CHECKED = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    page = requests.get(UPDATES_URL)
    soup = BeautifulSoup(page.text, 'html.parser')
    novel_list = soup.find(class_='table table-novels').findAll('tr')
    # test = novel_list[1]
    # print(test.findChildren('td')[0].select('span > a')[0].text)
    # print(test.findChildren('td')[0].select('div > a')[0].get('href'))
    novels = []
    for i in range(1, len(novel_list)-1):
        novel_info = novel_list[i]
        novel_name = novel_info.findChildren(
            'td')[0].select('span > a')[0].text
        novel_chapter = novel_info.findChildren(
            'td')[0].select('div > a')[0].text
        novel_url = BASE_URL + \
            novel_info.findChildren('td')[0].select('div > a')[0].get('href')
        novels.append({
            'name': novel_name,
            'latestChapter': novel_chapter,
            'chapterUrl': novel_url
        })
    return novels


"""
TELEGRAM
"""
# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.


def user_subscription(user_data):
    facts = []

    for key, value in user_data.items():
        facts.append(value)

    return ",".join(facts)

def start(update, context):
    """Send a message when the command /start is issued."""
    chat_id = update.message.chat_id
    logger.info('Chat id "%s" joined the chat. Adding it into the database.', chat_id);
    user = users_collection.find({'chat_id':chat_id})
    print(user)
    reply_text = ''
    if user.count() == 0:
        users_collection.insert_one({'chat_id':chat_id})
        reply_text += 'You have successfully registered. Only your Chat ID will be used.\n'
    else:
        logger.info('User already registered')
        reply_text += 'Welcome back.\n'
    novels = novels_collection.find()
    reply_text += "There are *{} available novels* \n".format((novels.count()))
    # for novel in novels:
    #     reply_text += "{}\n".format(novel["name"])
    # print(reply_text)
    menu_keyboard = [['List All']]
    menu_markup = telegram.ReplyKeyboardMarkup(menu_keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(text=reply_text, 
                 parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=menu_markup)


def get_all_updates(update, context):
    """Send a message when the command /get_all_updates is issued."""
    chat_id = update.message.chat_id
    logger.info('Retrieving all updates');
    novels = novels_collection.find()
    reply_text = "*Latest Chapters as of {}:* \n".format(LAST_CHECKED)
    for novel in novels:
        reply_text += "{}\n{}\n".format(novel["name"], novel["chapterUrl"])
    print(reply_text)
    update.message.reply_text(text=reply_text, 
                 parse_mode=telegram.ParseMode.MARKDOWN)

def list_all_novels(update, context):
    logger.info('Listing all novels')
    novels = novels_collection.find()
    reply_text = ''
    reply_text += "*Available novels: * \n"
    for novel in novels:
        reply_text += "{}\n".format(novel["name"])
    print(reply_text)
    update.message.reply_text(text=reply_text, 
                 parse_mode=telegram.ParseMode.MARKDOWN)

def profile(update, context):
    """Send profile info."""
    logger.info("Profile info requested from: {}\n".format(update.message.chat_id))
    user_novels = users_collection.find_one({'chat_id': update.message.chat_id, 'subscribed_novels': {'$exists': True}})
    if user_novels is None:
        update.message.reply_text(text='Please register or subscribe to novels first',
                 parse_mode=telegram.ParseMode.MARKDOWN)
        return
    update.message.reply_text(text="*Subscribed novels are:\n{}*".format(",".join(user_novels["subscribed_novels"])), parse_mode=telegram.ParseMode.MARKDOWN)

all_novels_menu_markup = ''

def subscribe(update, context):
    novels = novels_collection.find()
    menu_keyboard = []
    for novel in novels:
        menu_keyboard.append(["{}".format(novel["name"])])
    menu_keyboard.append(['Done'])
    global all_novels_menu_markup
    all_novels_menu_markup = telegram.ReplyKeyboardMarkup(menu_keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(text="Please select which novel to subsribe to: \n", 
                 parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=all_novels_menu_markup)

    return CHOOSING

def novel_choice(update, context):
    value = update.message.text
    user_data = context.user_data
    key = str(uuid4())
    user_data[key] = value
    user_subscription(user_data)
    global all_novels_menu_markup
    update.message.reply_text(text="Anymore? \n", 
                 parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=all_novels_menu_markup)

    return CHOOSING

def unsubscribe(update, context):
    user_novels = users_collection.find_one({'chat_id': update.message.chat_id, 'subscribed_novels': {'$exists': True}})
    user_novels_keyboard = []
    user_novels_mark_up = ''
    if user_novels is not None:
        print(user_novels["subscribed_novels"])
        for novel in user_novels["subscribed_novels"]:
            user_novels_keyboard.append([novel])
        user_novels_keyboard.append(['Done'])
    user_novels_mark_up = telegram.ReplyKeyboardMarkup(user_novels_keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(text="Please select novels to unsubscribe: \n", 
                 parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=user_novels_mark_up)

    return CHOOSING

def novel_unsubscribe(update, context):
    print('novel unsubscribe')
    value = update.message.text
    user_data = context.user_data
    key = str(uuid4())
    user_data[key] = value
    user_subscription(user_data)
    print('chat id to remove is :', update.message.chat_id)
    print('novel to remove is :', value)
    users_collection.find_one_and_update({'chat_id': update.message.chat_id}, {'$pull': {'subscribed_novels': value}})
    print(users_collection)
    novel = novels_collection.find_one_and_update({'name': value}, {'$pull': {'subscribers': update.message.chat_id}})
    print(novel)
    user_novels = users_collection.find_one({'chat_id': update.message.chat_id, 'subscribed_novels': {'$exists': True}})
    user_novels_keyboard = []
    user_novels_mark_up = ''
    if user_novels is not None:
        for novel in user_novels["subscribed_novels"]:
            user_novels_keyboard.append([novel])
        user_novels_keyboard.append(['Done'])
    user_novels_mark_up = telegram.ReplyKeyboardMarkup(user_novels_keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(text="Anymore? \n", 
                 parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=user_novels_mark_up)

    return CHOOSING

def done(update, context):
    user_data = context.user_data
    novels = []
    for key, value in user_data.items():
        users_collection.find_one_and_update({'chat_id':update.message.chat_id}, {'$addToSet': {'subscribed_novels': value}}, upsert = True)
        novels_collection.find_one_and_update({'name': value}, {'$addToSet': {'subscribers': update.message.chat_id}}, upsert = True)
    
    update.message.reply_text("Added these novels to your subscription:"
                              "\n{}\n"
                              "Until next time!".format(user_subscription(user_data)))

    user_data.clear()
    return ConversationHandler.END

def unsubscribe_done(update, context):
    user_data = context.user_data
    novels = []
    update.message.reply_text("These novels have been removed from your subscription:"
                              "\n{}\n"
                              "Until next time!".format(user_subscription(user_data)))

    user_data.clear()
    return ConversationHandler.END

def help(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')


def echo(update, context):
    """Echo the user message."""
    if update.message.text == "List All":
        list_all_novels(update, context)
        return
    update.message.reply_text("Unknown command...")


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(TELEGRAM_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("get_all_updates", get_all_updates))
    dp.add_handler(CommandHandler("profile", profile))

    # Add conversation handler with the states CHOOSING, TYPING_CHOICE and TYPING_REPLY
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('subscribe', subscribe)],

        states={
            CHOOSING:       [RegexHandler('^(?!Done).*$',
                                    novel_choice,
                                    pass_user_data=True)
            ]
        },
        fallbacks=[RegexHandler('^Done$', done, pass_user_data=True)]
    )

        # Add conversation handler with the states CHOOSING, TYPING_CHOICE and TYPING_REPLY
    unsubsribe_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('unsubscribe', unsubscribe)],

        states={
            CHOOSING:       [RegexHandler('^(?!Done).*$',
                                    novel_unsubscribe,
                                    pass_user_data=True)
            ]
        },
        fallbacks=[RegexHandler('^Done$', unsubscribe_done, pass_user_data=True)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(unsubsribe_conv_handler)

    # on noncommand i.e message - echo the message on Telegram
    dp.add_handler(MessageHandler(Filters.text, echo))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == "__main__":
    collist = wuxiaworlddb.list_collection_names()
    if "novels" in collist:
        print("The collection exists.")
    else:
        novels = populate_novels()
        x = novels_collection.insert_many(novels)
    update_thread = WuxiaUpdateThread()
    main()
