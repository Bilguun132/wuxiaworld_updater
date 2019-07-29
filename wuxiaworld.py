

import requests
from bs4 import BeautifulSoup
import json
import pymongo
import threading
import time
import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

client = pymongo.MongoClient("mongodb://localhost:27017/")
wuxiaworlddb = client["wuxiaworldDB"]
novels_collection = wuxiaworlddb["novels"]

BASE_URL = "https://www.wuxiaworld.com"
UPDATES_URL = "https://www.wuxiaworld.com/updates"
UPDATE_INTERVAL = 60


def populate_novels():
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


def check_for_updates():
    while True:
        new_novels = populate_novels()
        for novel in new_novels:
            existing_record = novels_collection.find_one(
                {'name': novel['name']})
            if novel['latestChapter'] == existing_record['latestChapter']:
                print('No need to update subscribers for ', novel['name'])
            else:
                print('New chapter found for {}'.format(
                    novel))
        logging.info('Updating again in %s seconds.', UPDATE_INTERVAL)
        time.sleep(UPDATE_INTERVAL)


"""
TELEGRAM
"""
# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.


def start(update, context):
    """Send a message when the command /start is issued."""
    update.message.reply_text('Hi!')


def help(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')


def echo(update, context):
    """Echo the user message."""
    update.message.reply_text(update.message.text)


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater("TOKEN", use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

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
    check_for_updates()
