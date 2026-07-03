"""
Chat Service — the main conversation loop.
Handles message → Gemini → tool calls → execution → response.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are FixIt's AI booking assistant for home and automotive services in India.

Your job is to help customers find and book service providers through natural conversation.

Rules:
1. Use the available tools to search providers, geocode locations, and create bookings.
2. Always confirm with the user before calling create_booking — ask "Shall I book this for you?"
3. Never invent provider names, prices, or availability — always use tool results.
4. Be concise and friendly. Keep responses to 2-3 sentences unless listing options.
5. If the user mentions a place name, use geocode_location first to get coordinates.
6. If user asks to cancel something, confirm the booking_id before calling cancel_booking.
7. For anonymous (not logged in) users, you cannot create bookings — politely ask them to sign up or log in.
8. Always be transparent: don't pretend a booking succeeded if the tool returned an error."""


def _get_tool_function(name: str):
    """Map tool name string to actual Python function."""
    from . import tools
    mapping = {
        'geocode_location':     tools.geocode_location,
        'search_providers':     tools.search_providers,
        'get_provider_detail':  tools.get_provider_detail,
        'create_booking':       tools.create_booking,
        'get_my_bookings':      tools.get_my_bookings,
        'cancel_booking':       tools.cancel_booking,
        'get_booking_status':   tools.get_booking_status,
        'get_category_list':    tools.get_category_list,
    }
    return mapping.get(name)


def _history_to_contents(history: list):
    """
    Convert stored ChatSession history entries back into
    Gemini `types.Content` objects, preserving function
    calls/results so multi-turn tool context isn't lost.
    Group contiguous function calls and function responses into single multi-part turns.
    """
    from google.genai import types

    contents = []
    i = 0
    while i < len(history):
        entry = history[i]
        role = entry['role']

        if 'text' in entry:
            contents.append(types.Content(
                role  = role,
                parts = [types.Part(text=entry['text'])],
            ))
            i += 1

        elif 'function_call' in entry:
            parts = []
            while i < len(history) and 'function_call' in history[i]:
                fc = history[i]['function_call']
                parts.append(types.Part(function_call=types.FunctionCall(
                    name = fc['name'],
                    args = fc['args'],
                )))
                i += 1
            contents.append(types.Content(
                role  = 'model',
                parts = parts,
            ))

        elif 'function_response' in entry:
            parts = []
            while i < len(history) and 'function_response' in history[i]:
                fr = history[i]['function_response']
                parts.append(types.Part(function_response=types.FunctionResponse(
                    name     = fr['name'],
                    response = fr['response'],
                )))
                i += 1
            contents.append(types.Content(
                role  = 'tool',
                parts = parts,
            ))
        else:
            i += 1

    return contents


# functions that need `request` as first argument (touch user-specific data)
REQUEST_AWARE_TOOLS = {
    'create_booking', 'get_my_bookings', 'cancel_booking', 'get_booking_status'
}


def process_chat_message(
    session,
    user_message: str,
    request = None,
    is_authenticated: bool = False,
    lat = None,
    lng = None,
) -> str:
    from google import genai
    from google.genai import types
    from .tool_definitions import AUTHENTICATED_TOOLS, PUBLIC_TOOLS

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        tools  = AUTHENTICATED_TOOLS if is_authenticated else PUBLIC_TOOLS

        # this turn's new entries — saved to session at the end, all at once
        new_entries = [{'role': 'user', 'text': user_message}]

        # rebuild full Gemini `contents` from ALL prior history + this new user message
        history = session.get_recent_history(limit=6)
        contents = _history_to_contents(history) + [
            types.Content(role='user', parts=[types.Part(text=user_message)])
        ]

        system_instruction = SYSTEM_PROMPT
        if lat is not None and lng is not None:
            system_instruction += f"\nUser's current coordinates: Latitude {lat}, Longitude {lng}. If they ask for nearby providers, use these coordinates directly instead of calling geocode_location."

        config = types.GenerateContentConfig(
            system_instruction = system_instruction,
            tools              = [tools],
            temperature        = 0.4,
        )

        max_iterations = 5
        final_text     = ''

        for _ in range(max_iterations):
            response = client.models.generate_content(
                model    = 'gemini-2.5-flash',
                contents = contents,
                config   = config,
            )

            candidate = response.candidates[0]
            function_calls = [
                p.function_call for p in candidate.content.parts
                if getattr(p, 'function_call', None)
            ]

            if function_calls:
                contents.append(candidate.content)
                tool_parts = []

                for fc in function_calls:
                    fn_name = fc.name
                    fn_args = dict(fc.args)

                    logger.info(f'Gemini requested tool: {fn_name}({fn_args})')

                    new_entries.append({
                        'role': 'model',
                        'function_call': {'name': fn_name, 'args': fn_args},
                    })

                    func = _get_tool_function(fn_name)
                    if not func:
                        fn_result = {'success': False, 'error': f'Unknown tool: {fn_name}'}
                    else:
                        try:
                            if fn_name in REQUEST_AWARE_TOOLS:
                                fn_result = func(request, **fn_args)
                            else:
                                fn_result = func(**fn_args)
                        except Exception as e:
                            logger.error(f'Tool {fn_name} execution failed: {e}')
                            fn_result = {'success': False, 'error': str(e)}

                    new_entries.append({
                        'role': 'tool',
                        'function_response': {'name': fn_name, 'response': fn_result},
                    })
                    logger.info(f'Sending function_response to Gemini: name={fn_name}, response={fn_result!r}')

                    tool_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name     = fn_name,
                            response = fn_result,
                        )
                    ))

                contents.append(types.Content(
                    role  = 'tool',
                    parts = tool_parts,
                ))
                continue

            else:
                final_text = response.text or ''
                break

        if not final_text:
            final_text = "I'm having trouble processing that. Could you rephrase?"

        new_entries.append({'role': 'model', 'text': final_text})

        # single save for the whole turn — replaces two separate add_message calls
        session.add_turn(new_entries)

        return final_text

    except Exception as e:
        logger.error(f'process_chat_message failed: {e}')
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            fallback = _local_fallback_search(user_message)
        else:
            fallback = "I'm having technical difficulties. Please try browsing our categories directly."
        session.add_turn([{'role': 'model', 'text': fallback}])
        return fallback


def _local_fallback_search(user_message: str) -> str:
    """
    Local search fallback when Gemini API is rate-limited (429).
    Uses keyword matching to query categories and providers from the database.
    """
    from services.models import ServiceCategory, ProviderService
    import re

    # Extract potential category keyword
    msg = user_message.lower()
    categories = ServiceCategory.objects.filter(is_active=True)
    matched_category = None
    for cat in categories:
        pattern = r'\b' + re.escape(cat.name.lower()) + r'\b'
        if re.search(pattern, msg) or cat.name.lower() in msg:
            matched_category = cat
            break

    if not matched_category:
        return "I'm experiencing high traffic right now and couldn't process your request. Please try browsing our service categories directly on the homepage."

    # Find active providers in this category
    services = ProviderService.objects.filter(
        category=matched_category,
        verification_status='verified',
        is_active=True,
        provider__approval_status='approved',
        provider__is_online=True
    ).select_related('provider')[:3]

    if not services.exists():
        return f"I am experiencing high traffic right now. I searched our records for '{matched_category.name}', but there are no online providers available in this category at the moment. Please check back shortly."

    # Format list
    provider_lines = []
    for s in services:
        name = s.provider.full_name
        rating = s.provider.overall_rating or "0.00"
        rate = s.base_charge
        provider_lines.append(f"- **{name}** (Rating: {rating}, Base charge: {rate} INR, Service ID: {s.id})")

    providers_str = "\n".join(provider_lines)
    return f"I'm experiencing high traffic right now, but I found these verified {matched_category.name}s online locally:\n{providers_str}\n\nYou can book any of them by typing: 'book service id [ID]' or using the homepage."