import logging
import ask_sdk_core.utils as ask_utils
import requests
import logging
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response

load_dotenv()
GENIUS_API_TOKEN = os.getenv('GENIUS_API_TOKEN')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool

        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Welcome! LyricEcho can help you find songs by their lyrics and provide details. Just say 'search' followed by the lyrics or song name you're looking for"
        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask(speak_output)
            .response
        )


class SongInfoIntentHandler(AbstractRequestHandler):

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SongInfoIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "Welcome! LyricEcho can help you search for songs by their lyrics, and I can provide you with facts about the song along with its lyrics. How can I assist you today?"

        return (
            handler_input.response_builder
            .speak(speak_output)
            # .ask("add a reprompt if you want to keep the session open for the user to respond")
            .response
        )


class SearchSongIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SearchSongIntent")(handler_input)

    def handle(self, handler_input):
        lyrics_slot = handler_input.request_envelope.request.intent.slots.get("Lyrics")

        # Retrieve and log the lyrics from the slot
        if lyrics_slot and lyrics_slot.value:
            lyrics = lyrics_slot.value
            logger.info(f"User provided lyrics: {lyrics}")
        else:
            lyrics = None
            logger.info("No lyrics were provided.")

        if lyrics:
            base_url = "https://api.genius.com"
            headers = {'Authorization': f'Bearer {GENIUS_API_TOKEN}'}
            search_url = f"{base_url}/search"
            params = {'q': lyrics}

            try:
                # Send a GET request to search for the lyrics
                response = requests.get(search_url, params=params, headers=headers)
                response.raise_for_status()

                results = response.json().get('response', {}).get('hits', [])
                if results:
                    # Store top 3 results in session attributes
                    session_attr = handler_input.attributes_manager.session_attributes
                    session_attr['search_results'] = [
                        {
                            "title": result['result']['title'],
                            "artist": result['result']['primary_artist']['name'],
                            "url": result['result']['url']
                        }
                        for result in results[:3]
                    ]
                    session_attr['current_index'] = 0  # Start with the first result

                    # Provide the first match to the user
                    first_song = session_attr['search_results'][0]
                    speak_output = (
                        f"I found '{first_song['title']}' by {first_song['artist']}. Would you like to hear another song, get the lyrics, or learn more facts about this song?"

                    )
                else:
                    logger.info("No matching songs found.")
                    speak_output = "I couldn't find any matching songs. Please try another lyric."
            except requests.RequestException as e:
                logger.error(f"Error in API request: {e}")
                speak_output = "Sorry, there was an issue while searching for the song. Please try again later."
        else:
            speak_output = "I couldn't find any lyrics. Please provide some lyrics or a song title to search."

        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask("Would you like to hear more options?")
            .response
        )


class GetSongDetailsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetSongDetailsIntent")(handler_input)

    def handle(self, handler_input):
        # Retrieve the current index and search results from session attributes
        session_attr = handler_input.attributes_manager.session_attributes
        current_index = session_attr.get("current_index", 0)
        search_results = session_attr.get("search_results", [])

        if not search_results:
            speak_output = "I couldn't find any search results. Please search for a song first."
            return handler_input.response_builder.speak(speak_output).response

        # Get the URL of the current song
        song_url = search_results[current_index].get("url")

        if not song_url:
            speak_output = "I'm sorry, I couldn't find the song details. Please search for a song first."
            return handler_input.response_builder.speak(speak_output).response

        try:
            # Fetch the page content for the song
            response = requests.get(song_url)
            response.raise_for_status()

            # Parse content with BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract lyrics
            lyrics_container = soup.find('div', class_="Lyrics__Container-sc-1ynbvzw-1")
            lyrics_text = lyrics_container.get_text(separator="\n") if lyrics_container else "Lyrics not found."

            # Read only a portion of the lyrics (first 3 lines or 200 characters)
            partial_lyrics = "\n".join(lyrics_text.split("\n")[:5]) if lyrics_text else lyrics_text[:200]

            # Store the full lyrics in session attributes for later retrieval
            session_attr['full_lyrics'] = lyrics_text

            # Prepare the partial lyrics response
            speak_output = f"Here's a part of the lyrics:\n{partial_lyrics}\n\nWould you like to continue listening to the full lyrics?"

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during page scraping: {e}")
            speak_output = "I'm sorry, I encountered an error while retrieving the song details. Please try again later."

        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask("Would you like to continue listening to the full lyrics?")
            .set_should_end_session(False)
            .response
        )


class ContinueListeningIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ContinueListeningIntent")(handler_input)

    def handle(self, handler_input):
        # Retrieve full lyrics from session attributes
        session_attr = handler_input.attributes_manager.session_attributes
        full_lyrics = session_attr.get('full_lyrics', None)

        if not full_lyrics:
            speak_output = "I couldn't find the full lyrics. Please search for a song first."
            return handler_input.response_builder.speak(speak_output).response

        # Provide the full lyrics
        speak_output = f"Here are the full lyrics:\n{full_lyrics}. To know facts about the song, simply say 'tell me the facts'?"

        return (
            handler_input.response_builder
            .speak(speak_output)
            .set_should_end_session(False)
            .response
        )


class NoMoreSongsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("NoMoreSongsIntent")(handler_input)

    def handle(self, handler_input):
        logger.info("User chose not to hear more song options.")

        # End the session politely
        speak_output = "It was fun sharing song information with you! If you need anything else, feel free to ask. Have a good one!"

        return (
            handler_input.response_builder
            .speak(speak_output)
            .set_should_end_session(True)
            .response
        )


class GetSongAdditionalInfoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetSongAdditionalInfoIntent")(handler_input)

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes
        current_index = session_attr.get("current_index", 0)
        search_results = session_attr.get("search_results", [])

        if not search_results:
            speak_output = "I couldn't find any search results. Please search for a song first."
            return handler_input.response_builder.speak(speak_output).response

        song_url = search_results[current_index].get("url")

        if not song_url:
            speak_output = "I'm sorry, I couldn't find the song details. Please search for a song first."
            return handler_input.response_builder.speak(speak_output).response

        try:
            response = requests.get(song_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            additional_info = ""
            elements = soup.find_all('div', class_="SongDescription__Content-sc-615rvk-2")
            if elements:
                additional_info = "\nAdditional Information:\n"
                for element in elements:
                    facts = [p.get_text() for p in element.find_all('p')]
                    additional_info += " ".join(f"- {fact}" for fact in facts) + "\n"
            else:
                additional_info = "No Facts found."

            date_posted = soup.find_all('span', class_="LabelWithIcon__Label-hjli77-1")
            release_date = date_posted[1].get_text() if date_posted else "Release date not found."

            speak_output = (
                f"Release Date: {release_date}\n"
                f" Facts: {additional_info}\n"
                "If you'd like information about any other song, to get the lyrics of the song just say 'get the lyrics'!"
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during page scraping: {e}")
            speak_output = "I'm sorry, I encountered an error while retrieving the song additional information. Please try again later."

        return (
            handler_input.response_builder
            .speak(speak_output)
            .set_should_end_session(False)
            .response
        )


class NextSongIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("NextSongIntent")(handler_input)

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes
        current_index = session_attr.get('current_index', 0)
        search_results = session_attr.get('search_results', [])

        if search_results and current_index + 1 < len(search_results):
            # Move to the next song in the list
            session_attr['current_index'] += 1
            next_song = search_results[session_attr['current_index']]
            speak_output = (
                f"Here's another match: '{next_song['title']}' by {next_song['artist']}. "
                "Would you like to hear more options?"
            )
        else:
            speak_output = "There are no more matches. Let me know if you want to search for something else."

        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask("Would you like to hear more options?")
            .response
        )


class HelloWorldIntentHandler(AbstractRequestHandler):
    """Handler for Hello World Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("HelloWorldIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Hello World!"

        return (
            handler_input.response_builder
            .speak(speak_output)
            # .ask("add a reprompt if you want to keep the session open for the user to respond")
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "You can say hello to me! How can I help?"

        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask(speak_output)
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Goodbye!"

        return (
            handler_input.response_builder
            .speak(speak_output)
            .response
        )


class FallbackIntentHandler(AbstractRequestHandler):
    """Single handler for Fallback Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In FallbackIntentHandler")
        speech = "Hmm, I'm not sure. You can say Hello or Help. What would you like to do?"
        reprompt = "I didn't catch that. What can I help you with?"

        return handler_input.response_builder.speak(speech).ask(reprompt).response


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        # Any cleanup logic goes here.

        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """The intent reflector is used for interaction model testing and debugging.
    It will simply repeat the intent the user said. You can create custom handlers
    for your intents by defining them above, then also adding them to the request
    handler chain below.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = "You just triggered " + intent_name + "."

        return (
            handler_input.response_builder
            .speak(speak_output)
            # .ask("add a reprompt if you want to keep the session open for the user to respond")
            .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors. If you receive an error
    stating the request handler chain is not found, you have not implemented a handler for
    the intent being invoked or included it in the skill builder below.
    """

    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speak_output = "Sorry, I had trouble doing what you asked. Please try again."

        return (
            handler_input.response_builder
            .speak(speak_output)
            .ask(speak_output)
            .response
        )


# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.


sb = SkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(HelloWorldIntentHandler())
sb.add_request_handler(GetSongDetailsIntentHandler())
sb.add_request_handler(ContinueListeningIntentHandler())
sb.add_request_handler(GetSongAdditionalInfoIntentHandler())
sb.add_request_handler(SongInfoIntentHandler())
sb.add_request_handler(NoMoreSongsIntentHandler())
sb.add_request_handler(NextSongIntentHandler())
sb.add_request_handler(SearchSongIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(
    IntentReflectorHandler())  # make sure IntentReflectorHandler is last so it doesn't override your custom intent handlers

sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()