"""
Tool schema definitions for Gemini function calling.
Each entry describes a function: its name, purpose, and parameters.
"""

from google.genai import types


GEOCODE_TOOL = types.FunctionDeclaration(
    name        = 'geocode_location',
    description = 'Convert a place name or address into latitude/longitude coordinates. Use this when the user mentions a location name like a neighborhood, landmark, or city.',
    parameters  = {
        'type': 'object',
        'properties': {
            'address': {
                'type':        'string',
                'description': 'The place name or address to geocode, e.g. "Kakkanad" or "near Infopark Kochi"',
            },
        },
        'required': ['address'],
    },
)

SEARCH_PROVIDERS_TOOL = types.FunctionDeclaration(
    name        = 'search_providers',
    description = 'Search for available service providers in a category, optionally near a location. Use this whenever the user wants to find someone to do a job.',
    parameters  = {
        'type': 'object',
        'properties': {
            'category_name': {
                'type':        'string',
                'description': 'Service category name, e.g. Electrician, Plumber, AC Repair, Carpenter',
            },
            'lat': {'type': 'number', 'description': 'Customer latitude if known'},
            'lng': {'type': 'number', 'description': 'Customer longitude if known'},
            'booking_type': {
                'type':        'string',
                'enum':        ['instant', 'scheduled'],
                'description': 'instant for right now, scheduled for a future date/time',
            },
        },
        'required': ['category_name'],
    },
)

GET_PROVIDER_DETAIL_TOOL = types.FunctionDeclaration(
    name        = 'get_provider_detail',
    description = 'Get full details about a specific provider service by its service_id. Use this after search_providers when the user wants more info about a specific result.',
    parameters  = {
        'type': 'object',
        'properties': {
            'service_id': {'type': 'integer', 'description': 'The service ID from a previous search result'},
        },
        'required': ['service_id'],
    },
)

CREATE_BOOKING_TOOL = types.FunctionDeclaration(
    name        = 'create_booking',
    description = 'Create an actual booking for the customer. Only call this after the customer has explicitly confirmed they want to book. Requires the user to be logged in.',
    parameters  = {
        'type': 'object',
        'properties': {
            'service_id':        {'type': 'integer', 'description': 'Service ID from search_providers result'},
            'address':           {'type': 'string',  'description': 'Customer service address'},
            'issue_description': {'type': 'string',  'description': 'What the customer needs done, at least 10 characters'},
            'booking_type':      {'type': 'string', 'enum': ['instant', 'scheduled']},
            'scheduled_at':      {'type': 'string',  'description': 'ISO datetime, only if booking_type is scheduled'},
        },
        'required': ['service_id', 'address', 'issue_description'],
    },
)

GET_MY_BOOKINGS_TOOL = types.FunctionDeclaration(
    name        = 'get_my_bookings',
    description = 'List the logged-in customer\'s own bookings. Use this when user asks about their booking history or current bookings.',
    parameters  = {
        'type': 'object',
        'properties': {
            'status_filter': {
                'type':        'string',
                'description': 'Optional status filter: requested, accepted, completed, cancelled etc.',
            },
        },
    },
)

CANCEL_BOOKING_TOOL = types.FunctionDeclaration(
    name        = 'cancel_booking',
    description = 'Cancel an existing booking. Only call after explicit user confirmation.',
    parameters  = {
        'type': 'object',
        'properties': {
            'booking_id': {'type': 'integer', 'description': 'The booking ID to cancel'},
            'reason':     {'type': 'string',  'description': 'Reason for cancellation'},
        },
        'required': ['booking_id', 'reason'],
    },
)

GET_BOOKING_STATUS_TOOL = types.FunctionDeclaration(
    name        = 'get_booking_status',
    description = 'Check the current status of a specific booking the customer owns.',
    parameters  = {
        'type': 'object',
        'properties': {
            'booking_id': {'type': 'integer', 'description': 'The booking ID to check'},
        },
        'required': ['booking_id'],
    },
)

GET_CATEGORY_LIST_TOOL = types.FunctionDeclaration(
    name        = 'get_category_list',
    description = 'List all available service categories on the platform.',
    parameters  = {'type': 'object', 'properties': {}},
)


# Tools available to authenticated customers — full access
AUTHENTICATED_TOOLS = types.Tool(function_declarations=[
    GEOCODE_TOOL,
    SEARCH_PROVIDERS_TOOL,
    GET_PROVIDER_DETAIL_TOOL,
    CREATE_BOOKING_TOOL,
    GET_MY_BOOKINGS_TOOL,
    CANCEL_BOOKING_TOOL,
    GET_BOOKING_STATUS_TOOL,
    GET_CATEGORY_LIST_TOOL,
])

# Tools available to anonymous public visitors — no booking actions
PUBLIC_TOOLS = types.Tool(function_declarations=[
    GEOCODE_TOOL,
    SEARCH_PROVIDERS_TOOL,
    GET_PROVIDER_DETAIL_TOOL,
    GET_CATEGORY_LIST_TOOL,
])