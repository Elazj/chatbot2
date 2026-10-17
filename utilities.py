"""
Generic utility commands carried over from the original voice prototype:
weather, jokes, web search, map lookup, and note-taking.

These are kept separate from the UTG knowledge base (knowledge_base.py)
because they're general-purpose actions, not retrieved facts -- the
distinction matters for your evaluation, since accuracy for these should be
measured as "did it do the right action," not "did it retrieve the right
passage."

In the voice version, search and map lookup opened a browser window on the
computer running the assistant. A chatbot runs on a server and the student
is somewhere else, so those now reply with a link the student can click.
Notes used to be .txt files in a shared folder; they are now stored per
account in the database.
"""

from urllib.parse import quote

import pyjokes
import requests

import db
from config import OPENWEATHER_API_KEY


def get_weather(city: str) -> str:
    if not OPENWEATHER_API_KEY:
        return (
            "Weather lookup isn't configured yet. Set the OPENWEATHER_API_KEY "
            "environment variable to enable it."
        )
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        code = str(data.get("cod"))
        if code == "401":
            # Most common cause: a brand-new key that hasn't activated yet
            # (can take from about 10 minutes up to 2 hours), or a typo.
            return (
                "The weather service didn't accept the API key. If it was just "
                "created, wait a little while for it to activate, then check "
                "that OPENWEATHER_API_KEY is copied correctly."
            )
        if code == "429":
            return "The weather service is busy right now. Please try again in a minute."
        if code != "200":
            return f"Sorry, I couldn't find the weather for {city}."
        weather = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        return f"The weather in {city} is {weather} with a temperature of {temp} degrees Celsius."
    except (requests.RequestException, ValueError, KeyError):
        return "Sorry, I couldn't fetch the weather right now."


def tell_joke() -> str:
    return pyjokes.get_joke()


def web_search(query: str) -> str:
    url = "https://www.google.com/search?q=" + quote(query)
    return f"Here's a search for \"{query}\":\n{url}"


def find_location(place: str) -> str:
    url = "https://www.google.com/maps/place/" + quote(place)
    return f"Here's the location for \"{place}\":\n{url}"


def save_note(user_id: int, content: str) -> str:
    db.add_note(user_id, content)
    return "Done, I've saved that note. Say \"my notes\" any time to see your latest ones."


def list_notes(user_id: int) -> str:
    notes = db.get_notes(user_id)
    if not notes:
        return "You don't have any saved notes yet. Try \"note: bring my ID to registration\"."
    lines = [f"{i}. {n['content']}" for i, n in enumerate(notes, start=1)]
    return "Your latest notes (newest first):\n" + "\n".join(lines)
