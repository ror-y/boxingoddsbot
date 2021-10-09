#!/usr/bin/env python3
import os
import re

import jellyfish
import praw
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_NAME = 'boxingoddsbot'
IS_POSTING_TO_REDDIT = False


def main():
    reddit = praw.Reddit(
        client_id=os.getenv('CLIENT_ID'),
        client_secret=os.getenv('CLIENT_SECRET'),
        user_agent=os.getenv('USER_AGENT'),
        username=os.getenv('USERNAME'),
        password=os.getenv('PASSWORD')
    )

    SUBREDDIT_TO_GET_DATA_FROM = reddit.subreddit("Boxing") if IS_POSTING_TO_REDDIT else reddit.subreddit(
        "Boxing")

    API_KEY = os.getenv('API_KEY')

    william_hill_request_url = "http://api.dimedata.net/api/json/odds/v3/60/william-hill-props/boxing/boxing/moneyline?api-key=" + API_KEY
    draft_kings_request_url = "http://api.dimedata.net/api/json/odds/v3/60/draftkings-props/boxing/boxing/moneyline?api-key=" + API_KEY
    bovada_request_url = "http://api.dimedata.net/api/json/odds/bovada/v2/60/boxing/boxing/all?api-key=" + API_KEY

    for submission in SUBREDDIT_TO_GET_DATA_FROM.new(limit=100):
        # print(submission.title)
        if '[FIGHT THREAD]' in submission.title:

            # if IS_POSTING_TO_REDDIT and is_post_already_replied_to(submission.comments):
            #     return

            william_hill_response = requests.get(william_hill_request_url)
            draft_kings_response = requests.get(draft_kings_request_url)
            bovada_response = requests.get(bovada_request_url)

            william_hill_data = william_hill_response.json()
            draft_kings_data = draft_kings_response.json()
            bovada_data = bovada_response.json()

            data = []

            parse_double_events_and_append_to_data(william_hill_data['games'], data)
            parse_double_events_and_append_to_data(draft_kings_data['games'], data)
            parse_single_events_and_append_to_data(bovada_data['games'], data)

            print('DATA', data)

            unique_fights_from_api = get_unique_fight_names_from_api(data)
            if not bool(unique_fights_from_api):
                print('Exiting, no API fights')
                return

            print('unique fights from api:')
            print(unique_fights_from_api)

            fights_to_use_from_selftext = get_fights_to_use_from_selftext(submission, unique_fights_from_api)
            if not bool(fights_to_use_from_selftext):
                print('Exiting, no fights from selftext')
                return

            print('fights to use from selftext:')
            print(fights_to_use_from_selftext)

            result = build_comment(fights_to_use_from_selftext, data)
            if not bool(result):
                print('Exiting, no result')
                return

            result += '  \n'
            result += '  \n'
            result += '*****'
            result += '  \n'
            result += '^^^For ^^^indication ^^^purposes ^^^only. ^^^This ^^^comment ^^^was ^^^auto-generated. ^^^To ^^^give ^^^feedback, ^^^please ^^^leave ^^^a ^^^reply.'

            print(result)

            # USE THIS FOR TESTING:
            # reddit.subreddit("BotsPlayHere").submit(
            #     title="Boxing Moneyline Odds",
            #     selftext=result
            # )

            if IS_POSTING_TO_REDDIT:
                reddit.subreddit("BoxingOdds").submit(
                    title="Boxing Moneyline Odds",
                    selftext=result
                )
                # submission.reply(result)


# For data structures from sources like:
# Bovada
def parse_single_events_and_append_to_data(source, data):
    idx = 0
    while idx < len(source):
        fight = source[str(idx)]
        is_fight_already_included = any(jellyfish.levenshtein_distance(x['description'], fight['description']) < 5 for x in data)
        is_reversed_fight_already_included = any(jellyfish.levenshtein_distance(x['description'], reverse_vs(fight['description'])) < 5 for x in data)

        print(fight['description'])
        if not is_fight_already_included and not is_reversed_fight_already_included:
            data.append(dict(
                description=fight['description'],
                nameA=fight['awayTeam'],
                priceA=fight['gameMoneylineAwayPrice'],
                nameB=fight['homeTeam'],
                priceB=fight['gameMoneylineHomePrice'],
            ))

        idx += 1


# For data structures from sources like:
# William Hill
# DraftKings
def parse_double_events_and_append_to_data(source, data):
    idx = 0
    while idx < (len(source) - 1):
        fight = source[str(idx)]
        print(fight['description'])
        is_fight_already_included = any(x['description'] == fight['description'] for x in data)
        is_reversed_fight_already_included = any(x['description'] == reverse_vs(fight['description']) for x in data)

        if not is_fight_already_included and not is_reversed_fight_already_included:
            data.append(dict(
                description=fight['description'],
                nameA=fight['betName'],
                priceA=fight['betPrice'],
                nameB=source[str(idx + 1)]['betName'],
                priceB=source[str(idx + 1)]['betPrice'],
            ))

        idx += 2



# If bot already commented, we don't want to comment again.
def is_post_already_replied_to(comments):
    commenters = []

    for comment in comments:
        commenters.append(comment.author)

    return BOT_NAME in commenters


# Retrieve all the fights available in the data.
def get_unique_fight_names_from_api(data):
    unique_fights = []
    for i in range(0, len(data)):
        description = data[i]['description']
        if all(x != description and x != reverse_vs(description) for x in unique_fights):
            unique_fights.append(description)

    return unique_fights


# Find all the fights in the fight thread text.
# Then, check against the data for available fights to show odds for.
def get_fights_to_use_from_selftext(submission, unique_fights):
    self_text_extracted_fights = re.findall(".+vs.+", submission.selftext)
    fights_to_use = []
    for i in range(0, len(unique_fights)):
        for j in range(0, len(self_text_extracted_fights)):
            similarity_score = jellyfish.levenshtein_distance(unique_fights[i], self_text_extracted_fights[j])
            similarity_score_reversed_vs = jellyfish.levenshtein_distance(reverse_vs(unique_fights[i]),
                                                                          self_text_extracted_fights[j])

            # print('score:')
            # print(similarity_score)
            # print('score reversed vs:')
            # print(similarity_score_reversed_vs)
            # print('fight:')
            # print(unique_fights[i])
            # print('fight 2:')
            # print(self_text_extracted_fights[j])
            # print('____________________________________')

            threshold = 5
            if (similarity_score < threshold or similarity_score_reversed_vs < threshold) and unique_fights[
                i] not in fights_to_use and reverse_vs(unique_fights[i]) not in fights_to_use:
                fights_to_use.append(unique_fights[i])
                break
    return fights_to_use


# Invert the order of the fighters.
# Turns 'A vs B' into 'B vs A'.
def reverse_vs(fight_name):
    vs_string = ' vs '
    everything_until_vs = fight_name[0:fight_name.find(vs_string)]
    everything_after_vs = fight_name[fight_name.find(vs_string) + 4:]

    return everything_after_vs + vs_string + everything_until_vs


# Build a string of fight and odds information.
def build_comment(fights_to_use, data):
    result = ""
    result += '**Moneyline Odds:**  \n'
    result += '  \n'

    # print('______________')
    # print('FTU')
    # print(fights_to_use)
    # print('D')
    # print(data)
    # print('______________')

    for i in range(0, len(data)):
        if data[i]['description'] in fights_to_use:
            result += data[i]['nameA'] + ': '
            result += '**' + data[i]['priceA'] + '**'
            result += '  \n'
            result += data[i]['nameB'] + ': '
            result += '**' + data[i]['priceB'] + '**'
            result += '  \n'
            result += '  \n'

    return result


if __name__ == "__main__":
    main()
