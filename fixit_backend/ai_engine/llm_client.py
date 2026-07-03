"""
LLM Client — wraps Google Gemini API.
Single place for all LLM calls in FixIt.
If we switch models later, only this file changes.
"""

import logging
from django.conf import settings
from google.genai import types

logger = logging.getLogger(__name__)

_client=None

def get_client():
     """Lazy-load Gemini client."""
     global _client
     if _client is None:
          from google import genai
          _client = genai.Client(api_key=settings.GEMINI_API_KEY)
          logger.info('Gemini client initialized.')
     return _client

def generate(prompt: str, max_tokens: int = 500) -> str:

   
    try:
      client = get_client()
      response = client.models.generate_content(
            model = 'gemini-2.5-flash',
            contents = prompt,
             config = types.GenerateContentConfig(max_output_tokens=max_tokens),
        )
      text=response.text
      return  text.strip() if text else ''
    except Exception as e:
        logger.error(f'Gemini generate failed: {e}')
        return ''
    
def generate_with_system(system: str, user: str, max_tokens: int = 500) -> str:

    try:
        client = get_client()
        from google.genai import types
        response = client.models.generate_content(
            model = 'gemini-2.5-flash',
            contents = user,
             config   = types.GenerateContentConfig(
                system_instruction = system,
                max_output_tokens  = max_tokens,
                temperature        = 0.3,  # low = more factual, less creative
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f'Gemini generate_with_system failed: {e}')
        return ''


